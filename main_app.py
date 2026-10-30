import struct
import sys
import os
import random 
import datetime
import time
import csv
import smtplib
import json
import threading
import data_sync 
from email.mime.text import MIMEText

from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import (QWidget, QTableWidgetItem, QHeaderView, QMessageBox, 
                             QDialog, QListWidgetItem, QApplication, 
                             QGraphicsDropShadowEffect, QGraphicsColorizeEffect)
from PyQt5.QtCore import (Qt, QTimer, QMutex, QMutexLocker, QThreadPool, 
                          QThread, pyqtSignal, QEventLoop, QSize, pyqtSlot, 
                          QPropertyAnimation, QRect, QEasingCurve, QObject, QEvent, QMetaObject, Q_ARG)
from PyQt5.QtGui import QColor, QPixmap

# --- MODUL PYMODBUS (SERIAL) ---
from pymodbus.client import ModbusSerialClient


# MONKEY-PATCH PYMODBUS FOR COMPATIBILITY WITH SLAVE/UNIT/DEVICE_ID PARAMS
try:
    from pymodbus.client.base import ModbusClientMixin
    
    def _patch_client_method(original_method):
        import inspect
        sig = inspect.signature(original_method)
        params = sig.parameters
        
        def wrapper(self, *args, **kwargs):
            if 'slave' in kwargs:
                slave_val = kwargs.pop('slave')
                if 'slave' in params:
                    kwargs['slave'] = slave_val
                elif 'unit' in params:
                    kwargs['unit'] = slave_val
                elif 'device_id' in params:
                    kwargs['device_id'] = slave_val
                else:
                    kwargs['slave'] = slave_val
            return original_method(self, *args, **kwargs)
        return wrapper

    for _name in [
        'write_coil', 'write_registers', 'write_register',
        'read_discrete_inputs', 'read_holding_registers', 'read_input_registers'
    ]:
        if hasattr(ModbusClientMixin, _name):
            _orig = getattr(ModbusClientMixin, _name)
            setattr(ModbusClientMixin, _name, _patch_client_method(_orig))
            print(f"[PATCH] Patched ModbusClientMixin.{_name}")
except Exception as _e:
    print(f"[PATCH ERROR] Failed to patch pymodbus client methods: {_e}")

# --- MODULAR IMPORTS ---
from log_manager import LogManager, SensorLogger, EventLogger, MaintenanceLogger, TotalizerLogger
from dialog_handlers import MachineDialog, VFDDialog
from workers import FunctionWorker
from alarm_system import AlarmMonitor
from USR_Library import USRIOController
from smart_shift import SmartShiftWorker
from gauge import SemiCircularGauge
from chart import SensorChart
from DIAC_X_GUI_LOGIN import loginWindow
from numpad import NumpadDialog
import res_fix_rc 


# --- HARDWARE CONFIGURATION ---
import sys
import os
import glob
import time

if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def get_best_serial_port(preferred, exclude=None):
    """
    Returns preferred port if it exists.
    If not found on Linux, scans available /dev/ttyACM* or /dev/ttyUSB* ports
    so communication won't die if OS enumerates under a different number.
    """
    if exclude is None:
        exclude = []
    if os.path.exists(preferred) and preferred not in exclude:
        return preferred
    if sys.platform.startswith('linux'):
        candidates = sorted(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*'))
        for p in candidates:
            if p not in exclude and os.path.exists(p):
                return p
    return preferred

def safe_flush_buffers(client):
    """Flushes dirty bytes from PySerial input & output buffers to prevent CRC corruption."""
    if client is None:
        return
    try:
        ser = getattr(client, 'socket', getattr(client, 'comm', None))
        if ser:
            if hasattr(ser, 'reset_input_buffer'):
                ser.reset_input_buffer()
            if hasattr(ser, 'reset_output_buffer'):
                ser.reset_output_buffer()
            if hasattr(ser, 'flush'):
                ser.flush()
    except Exception:
        pass

def reset_linux_usb_for_port(port_path):
    """
    Performs a software USB power-cycle on Linux via sysfs.
    Mimics unplugging and replugging the Waveshare USB adapter without physical touch.
    """
    if not sys.platform.startswith('linux') or not port_path:
        return False
    try:
        real_name = os.path.basename(port_path)
        sys_device_link = f"/sys/class/tty/{real_name}/device"
        if os.path.exists(sys_device_link):
            curr = os.path.realpath(sys_device_link)
            while curr and curr != '/':
                auth_path = os.path.join(curr, 'authorized')
                if os.path.exists(auth_path):
                    with open(auth_path, 'w') as f:
                        f.write('0\n')
                    time.sleep(0.3)
                    with open(auth_path, 'w') as f:
                        f.write('1\n')
                    print(f"[USB RESET] Successfully power-cycled USB device {port_path} via sysfs")
                    return True
                curr = os.path.dirname(curr)
    except Exception as e:
        print(f"[USB RESET INFO] Software USB cycle skipped ({e})")
    return False

if sys.platform.startswith('win'):
    SERIAL_PORT = 'COM3' 
    SERIAL_PORT_BL = 'COM4' 
else:
    SERIAL_PORT_BL = get_best_serial_port('/dev/ttyACM0') # Jalur Khusus Blower B
    SERIAL_PORT = get_best_serial_port('/dev/ttyACM3', exclude=[SERIAL_PORT_BL])

BAUDRATE = 9600
PARITY = 'N'
STOPBITS = 1
BYTESIZE = 8
MAX_VFD_HZ = 20.0

# IO MAP
IO_MAP = {
    'EMC':           {'slave': 1, 'addr': 0, 'type': 'DI'},
    'EMG':           {'slave': 1, 'addr': 0, 'type': 'DI'},
    'TRIP_TP_01A':   {'slave': 1, 'addr': 1, 'type': 'DI'},
    'TRIP_TP_01B':   {'slave': 1, 'addr': 2, 'type': 'DI'},
    'TRIP_TP_02A':   {'slave': 1, 'addr': 3, 'type': 'DI'},
    'TRIP_TP_02B':   {'slave': 1, 'addr': 4, 'type': 'DI'},
    'TRIP_TP_03':    {'slave': 1, 'addr': 5, 'type': 'DI'},
    'TRIP_TP_04A':   {'slave': 1, 'addr': 6, 'type': 'DI'},
    'TRIP_TP_04B':   {'slave': 1, 'addr': 7, 'type': 'DI'},
    'TRIP_TP_05A':   {'slave': 2, 'addr': 0, 'type': 'DI'},
    'TRIP_TP_05B':   {'slave': 2, 'addr': 1, 'type': 'DI'},
    'TRIP_SM_01':    {'slave': 2, 'addr': 2, 'type': 'DI'},
    'TRIP_DP_01':    {'slave': 2, 'addr': 3, 'type': 'DI'},
    'TRIP_BL_01A':   {'slave': 2, 'addr': 4, 'type': 'DI'},
    'TRIP_BL_01B':   {'slave': 2, 'addr': 5, 'type': 'DI'},
    'LS_101':        {'slave': 2, 'addr': 6, 'type': 'DI'},
    'LS_102':        {'slave': 2, 'addr': 7, 'type': 'DI'},
    'LS_103':        {'slave': 3, 'addr': 0, 'type': 'DI'},
    'LS_104':        {'slave': 3, 'addr': 1, 'type': 'DI'},
    'AV_101_OP':     {'slave': 3, 'addr': 2, 'type': 'DI'},
    'AV_101_CL':     {'slave': 3, 'addr': 3, 'type': 'DI'},
    'AV_102_OP':     {'slave': 3, 'addr': 4, 'type': 'DI'},
    'AV_102_CL':     {'slave': 3, 'addr': 5, 'type': 'DI'},
    # Backward compatibility aliases for DI
    'TRIP_IN_A':     {'slave': 1, 'addr': 1, 'type': 'DI'},
    'TRIP_IN_B':     {'slave': 1, 'addr': 2, 'type': 'DI'},
    'TRIP_TP_03A':   {'slave': 1, 'addr': 6, 'type': 'DI'},
    'TRIP_TP_03B':   {'slave': 1, 'addr': 7, 'type': 'DI'},
    'TRIP_TP_04':    {'slave': 1, 'addr': 5, 'type': 'DI'},
    'LS_MBR_BW':     {'slave': 2, 'addr': 6, 'type': 'DI'},
    'LS_INLET':      {'slave': 2, 'addr': 7, 'type': 'DI'},

    # Digital Outputs (DO)
    'TP_01A':        {'slave': 4, 'addr': 0, 'type': 'DO'},
    'TP_01B':        {'slave': 4, 'addr': 1, 'type': 'DO'},
    'TP_02A':        {'slave': 4, 'addr': 2, 'type': 'DO'},
    'TP_02B':        {'slave': 4, 'addr': 3, 'type': 'DO'},
    'TP_04A':        {'slave': 4, 'addr': 4, 'type': 'DO'},
    'TP_04B':        {'slave': 4, 'addr': 5, 'type': 'DO'},
    'TP_03':         {'slave': 4, 'addr': 6, 'type': 'DO'},
    'TP_05A':        {'slave': 4, 'addr': 7, 'type': 'DO'},
    'TP_05B':        {'slave': 5, 'addr': 0, 'type': 'DO'},
    'BL_01A':        {'slave': 5, 'addr': 1, 'type': 'DO'},
    'BL_01B':        {'slave': 5, 'addr': 2, 'type': 'DO'},
    'SM_01':         {'slave': 5, 'addr': 3, 'type': 'DO'},
    'DP_01':         {'slave': 5, 'addr': 4, 'type': 'DO'},
    'ACT_01':        {'slave': 5, 'addr': 5, 'type': 'DO'},
    'ACT_02':        {'slave': 5, 'addr': 6, 'type': 'DO'},
    'ALARM':         {'slave': 5, 'addr': 7, 'type': 'DO'},
    # DO Aliases
    'TP_IN_A':       {'slave': 4, 'addr': 0, 'type': 'DO'},
    'TP_IN_B':       {'slave': 4, 'addr': 1, 'type': 'DO'},
    'TP_03A':        {'slave': 4, 'addr': 4, 'type': 'DO'},
    'TP_03B':        {'slave': 4, 'addr': 5, 'type': 'DO'},
    'TP_04':         {'slave': 4, 'addr': 6, 'type': 'DO'},

    # Analog Inputs (AI) & RS485 Modbus Sensors
    'FT_101':        {'slave': 6, 'addr': 0, 'type': 'AI'},
    'FT_102':        {'slave': 6, 'addr': 2, 'type': 'AI'},
    'FT_103':        {'slave': 6, 'addr': 4, 'type': 'AI'},
    'PT_101':        {'slave': 6, 'addr': 6, 'type': 'AI'},
    'DO_101':        {'slave': 7, 'addr': 0, 'type': 'AI'},
    'LT_101':        {'slave': 7, 'addr': 2, 'type': 'AI'},

    # Analog Outputs (AO)
    'AO_TP_04A':     {'slave': 8, 'addr': 0, 'type': 'AO'},
    'AO_TP_04B':     {'slave': 8, 'addr': 2, 'type': 'AO'},
    'AO_TP_03':      {'slave': 8, 'addr': 4, 'type': 'AO'},
    'AO_TP_03A':     {'slave': 8, 'addr': 0, 'type': 'AO'},
    'AO_TP_03B':     {'slave': 8, 'addr': 2, 'type': 'AO'},
    'AO_TP_04':      {'slave': 8, 'addr': 4, 'type': 'AO'},
}

class ToastNotification(QtWidgets.QWidget):
    def __init__(self, parent, title, message, alarm_name, controller):
        super().__init__(None) # Menggunakan None agar tidak mengecilkan layout Window Utama (Parent)
        self.parent_widget = parent
        self.controller = controller
        self.alarm_name = alarm_name
        
        # Setup Window: Tanpa Frame, Selalu di Atas, Transparan background
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Layout Utama
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Frame Container (Kotak Notifikasi)
        self.frame = QtWidgets.QFrame()
        # Style ala "To-Do List" Notification: Bersih, Putih, Border Merah di kiri
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-left: 6px solid #ff4444; 
                border-top: 1px solid #dcdcdc;
                border-right: 1px solid #dcdcdc;
                border-bottom: 1px solid #dcdcdc;
                border-radius: 4px;
            }
            QLabel { color: #333333; font-family: "Segoe UI", sans-serif; }
            QPushButton {
                border-radius: 3px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        
        # Efek Bayangan (Shadow)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.frame.setGraphicsEffect(shadow)
        
        frame_layout = QtWidgets.QVBoxLayout(self.frame)
        
        # Judul & Pesan
        lbl_title = QtWidgets.QLabel(f"<b style='font-size:12px;'>{title}</b>")
        lbl_msg = QtWidgets.QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 11px; color: #555;")
        
        frame_layout.addWidget(lbl_title)
        frame_layout.addWidget(lbl_msg)
        
        # Area Tombol (Snooze & Ack)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(5)
        
        self.btn_snooze = QtWidgets.QPushButton("Snooze (Mute)")
        self.btn_snooze.setStyleSheet("background-color: #ffc107; color: black; border: none;")
        self.btn_snooze.setCursor(Qt.PointingHandCursor)
        self.btn_snooze.clicked.connect(self.on_snooze)
        
        self.btn_ack = QtWidgets.QPushButton("Acknowledge (Done)")
        self.btn_ack.setStyleSheet("background-color: #28a745; color: white; border: none;")
        self.btn_ack.setCursor(Qt.PointingHandCursor)
        self.btn_ack.clicked.connect(self.on_acknowledge)
        
        btn_layout.addWidget(self.btn_snooze)
        btn_layout.addWidget(self.btn_ack)
        frame_layout.addLayout(btn_layout)
        
        layout.addWidget(self.frame)
        
        # Animasi Slide-In
        self.animation = QPropertyAnimation(self, b"geometry")
        
    def show_animated(self):
        # Hitung Posisi (Pojok Kanan Bawah Window Induk)
        if not self.parent_widget: return
        from PyQt5.QtCore import QPoint
        parent_geo = self.parent_widget.geometry()
        parent_global_pos = self.parent_widget.mapToGlobal(QPoint(0,0))
        
        width = 320
        height = 140 
        margin_right = 20
        margin_bottom = 20
        
        # Koordinat Akhir
        end_x = parent_global_pos.x() + parent_geo.width() - width - margin_right
        end_y = parent_global_pos.y() + parent_geo.height() - height - margin_bottom
        
        # Koordinat Awal (Di luar layar kanan sedikit)
        start_x = parent_global_pos.x() + parent_geo.width()
        
        self.setGeometry(start_x, end_y, width, height)
        self.show()
        
        # Jalankan Animasi
        self.animation.setDuration(400)
        self.animation.setStartValue(QRect(start_x, end_y, width, height))
        self.animation.setEndValue(QRect(end_x, end_y, width, height))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()

    def on_snooze(self):
        # Snooze: Matikan Buzzer Fisik & Start Timer
        if hasattr(self.controller, 'handle_snooze_timeout'):
            self.controller.handle_snooze_timeout() 
            if self.controller.buzzer_snooze_timer.isActive():
                self.controller.buzzer_snooze_timer.stop()
            
            # Start timer snooze
            self.controller.buzzer_snooze_timer.start(self.controller.SNOOZE_DURATION)
            self.controller._request_buzzer(False) # Matikan suara fisik
            self.controller.update_btn_alarm_display()
            
            # Update tampilan tombol (Opsional, tetap dibiarkan sesuai request)
            self.btn_snooze.setText("Snoozed")
            self.btn_snooze.setEnabled(False)
            self.btn_snooze.setStyleSheet("background-color: #e0e0e0; color: #888;")

        self.close()

    def on_acknowledge(self):
        # Acknowledge: Rekam Done, Matikan Buzzer, Tutup Notif
        if hasattr(self.controller, 'acknowledge_alarm_from_toast'):
            self.controller.acknowledge_alarm_from_toast(self.alarm_name)
        self.close() 
    
    def closeEvent(self, event):
        if self.controller and hasattr(self.controller, 'active_toasts'):
            if self.alarm_name in self.controller.active_toasts:
                if self.controller.active_toasts[self.alarm_name] == self:
                    del self.controller.active_toasts[self.alarm_name]
        event.accept()

# --- CLASS: MACHINE OFF DIALOG (.UI) ---
class MachineOffDialogUI(QDialog):
    def __init__(self, parent=None, component_name="Unknown Machine"):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_Machine_off.ui")
        try:
            uic.loadUi(ui_path, self)
            for lbl in self.findChildren(QtWidgets.QLabel):
                if lbl.objectName() in ["label", "label_2"]: 
                    lbl.setText(f"Anda yakin ingin mematikan {component_name}?")
                    break
            if hasattr(self, 'Machine_Yes'): self.Machine_Yes.clicked.connect(self.accept)
            if hasattr(self, 'Machine_No'): self.Machine_No.clicked.connect(self.reject)
        except FileNotFoundError:
            pass 

class MachineOnDialogUI(QDialog):
    def __init__(self, parent=None, component_name="Unknown Machine"):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_Machine.ui")
        try:
            uic.loadUi(ui_path, self)
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", f"File UI tidak ditemukan: {ui_path}")
            return
        self.setWindowTitle(f"Start: {component_name}")
        for lbl in self.findChildren(QtWidgets.QLabel):
            if lbl.objectName() in ["label", "label_2"]: 
                lbl.setText(f"Anda yakin ingin menyalakan {component_name}?")
                break
        
        if hasattr(self, 'Machine_Yes'): self.Machine_Yes.clicked.connect(self.accept)
        elif hasattr(self, 'btn_yes'): self.btn_yes.clicked.connect(self.accept)
        if hasattr(self, 'Machine_No'): self.Machine_No.clicked.connect(self.reject)
        elif hasattr(self, 'btn_no'): self.btn_no.clicked.connect(self.reject)

# --- CLASS: FAST ESTOP MONITOR ---
class FastEstopMonitor(QThread):
    estop_active_signal = pyqtSignal()   
    estop_cleared_signal = pyqtSignal()  

    def __init__(self, io_controller, mutex):
        super().__init__()
        self.io_controller = io_controller
        self.mutex = mutex
        self.running = True
        self.last_state = -1

    def run(self):
        self.setPriority(QThread.TimeCriticalPriority)
        while self.running:
            try:
                current_val = None
                if self.mutex.tryLock(20): 
                    try:
                        current_val = self.io_controller.digitalInput(0, 1) 
                    finally:
                        self.mutex.unlock()
                
                if current_val is not None:
                    if current_val == 0 and self.last_state != 0:
                        self.estop_active_signal.emit()
                        self.last_state = 0
                    elif current_val == 1 and self.last_state != 1:
                        self.estop_cleared_signal.emit()
                        self.last_state = 1
            except Exception: pass
            self.msleep(150)

    def stop(self):
        self.running = False
        self.wait()


class AutoPilotWorker(QThread):
    request_write_hardware = pyqtSignal(str, bool, float) 
    update_ui_signal = pyqtSignal(str) 
    error_signal = pyqtSignal(str)
    emergency_stop_signal = pyqtSignal(str)

    def __init__(self, main_controller):
        super().__init__()
        self.main = main_controller
        self.running = False
        self.last_sent_states = {} 
        
        # Timer Config
        self.DUR_RUN = 8 * 60     
        self.DUR_RELAX = 2 * 60   
        self.DUR_BACKWASH = 120    
        self.MAX_CYCLES = 4
        self.ACT_DELAY = 40       
        
        self.mbr_internal_timer = 0.0 
        self.sm_internal_timer = 0.0
        self.sm_duration_config = 3600 
        self.sm_duration_minutes = 30.0
        
        self.last_tick_time = 0.0
        self.was_paused = False
        
        # PID & Hz Control
        self.current_hz_tp03 = 20.0 
        self.current_hz_tp04 = 30.0 
        self.FLOW_SETPOINT = 6.0 
        self.FLOW_SETPOINT_BW = 8.0 
        self.tp34_last_check_time = 0.0
        
        # [NEW] Dynamic Blower Setpoint
        self.BLOWER_TARGET_HZ = 45.0 
        
        # Blower Intermittent & Shift Controls
        self.blower_intermittent_timer = 0.0    # Siklus internal 1 jam ON / 15 menit OFF
        self.blower_running_accum_timer = 0.0   # Akumulasi jam running aktif (ON) untuk switching
        self.blower_shift_target = 3600.0       # Target running time (detik) sebelum switch
        self.blower_mode = "SWITCH"             # "SWITCH", "A_ONLY", "B_ONLY"
        self.blower_active_suffix = 'A'         # Blower aktif saat ini ('A' atau 'B')
        self.blower_runtime_total = {'A': 0.0, 'B': 0.0} # Total runtime akumulasi detik per blower
        self.blower_last_log_time = 0.0         # Timestamp untuk interval log runtime
        
        # PT Recovery Variables
        self.pt_alarm_active = False
        self.pt_alarm_timer = 0.0
        self.PT_RECOVERY_DURATION = 10 * 60     

        self.LIMITS = {
            'LT EQ-01_HH': 227.0, 'LT EQ-01_HI': 213.0,
            'LT EQ-01_LO': 142.0, 'LT EQ-01_LL': 100.0,
            'LT AE-01_HH': 255.0, 'LT AE-01_HI': 227.0, 
            'LT AE-01_LO': 213.0, 'LT AE-01_LL': 199.0,
            'LT MBR-01_HH': 255.0, 'LT MBR-01_HI': 227.0, 
            'LT MBR-01_LO': 213.0, 'LT MBR-01_LL': 199.0,
            'PT 101_HH': 0.9, 'PT 101_LL': -0.27
        }
        self.limits_config = {}
        self.SENSOR_ALIASES = {
            'LT EQ-01':  ['LT_101', 'Level EQ', 'LT EQ-01'],
            'LT AE-01':  ['LT_102', 'Level Aeration', 'Level Aerasi', 'LT AE-01'],
            'LT MBR-01': ['LT_103', 'Level MBR', 'LT MBR-01'],
            'PT 101':    ['PT_101', 'Pressure', 'PT 101'],
            'FT 101':    ['FT_101', 'Flow Inlet'],
            'FT 102':    ['FT_102', 'Flow MBR'],
            'FT 103':    ['FT_103', 'Flow BW']
        }

        self.latch_state = {
            'TP_IN': False, 'TP_01': False, 'TP_02': False
        }

    # [NEW] Method agar GUI bisa mengubah Blower Speed di mode Auto
    def set_blower_setpoint(self, hz):
        self.BLOWER_TARGET_HZ = float(hz)
        print(f"[AUTO] Blower Setpoint updated to {self.BLOWER_TARGET_HZ} Hz")

    def load_configs(self):
        # --- PART 1: LOAD JSON (Shift) - Tidak Berubah ---
        json_path = os.path.join(os.path.dirname(__file__), "data_shift_settings.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    self.MAX_CYCLES = int(data.get("spin_siklus_tp03", 5))
                    print(f"[AUTO CONFIG] Cycles: {self.MAX_CYCLES}")
                    
                    val_str = str(data.get("combo_sm", "1 Jam")).lower()
                    import re
                    digits = re.findall(r'\d+', val_str)
                    number = int(digits[0]) if digits else 1
                    if "jam" in val_str or "hour" in val_str: self.sm_duration_config = number * 3600
                    elif "menit" in val_str or "minute" in val_str: self.sm_duration_config = number * 60
                    else: self.sm_duration_config = number
                    if self.sm_duration_config < 10: self.sm_duration_config = 10

                    # Load Blower Shift Config
                    val_bl = str(data.get("combo_bl01", "1 jam")).strip()
                    val_bl_lower = val_bl.lower()
                    if "only" in val_bl_lower:
                        if "01a" in val_bl_lower or "a only" in val_bl_lower:
                            self.blower_mode = "A_ONLY"
                            self.blower_active_suffix = 'A'
                        elif "01b" in val_bl_lower or "b only" in val_bl_lower:
                            self.blower_mode = "B_ONLY"
                            self.blower_active_suffix = 'B'
                        else:
                            self.blower_mode = "A_ONLY"
                            self.blower_active_suffix = 'A'
                        self.blower_shift_target = 0.0
                    else:
                        self.blower_mode = "SWITCH"
                        digits_bl = re.findall(r'\d+', val_bl_lower)
                        num_bl = int(digits_bl[0]) if digits_bl else 1
                        if "detik" in val_bl_lower or "second" in val_bl_lower:
                            self.blower_shift_target = float(num_bl)
                        elif "menit" in val_bl_lower or "minute" in val_bl_lower:
                            self.blower_shift_target = float(num_bl * 60)
                        else:
                            self.blower_shift_target = float(num_bl * 3600)
                        if self.blower_shift_target < 10.0:
                            self.blower_shift_target = 10.0
                    print(f"[AUTO CONFIG] Blower Mode: {self.blower_mode}, Target: {self.blower_shift_target}s ({val_bl}), Active: {self.blower_active_suffix}")

                    if hasattr(self.main, 'shift_worker') and 'BL_01' in self.main.shift_worker.groups:
                        self.main.shift_worker.groups['BL_01']['Active'] = self.blower_active_suffix
                        self.main.shift_worker.groups['BL_01']['RawSetting'] = val_bl
            except Exception as e: 
                print(f"[AUTO CONFIG ERR] {e}")

        # --- PART 2: LOAD CSV (Alarm) - NORMALIZED VERSION ---
        csv_path = os.path.join(os.path.dirname(__file__), "data_alarm_settings.csv")
        self.limits_config = {} # Reset memori
        
        # A. AUTO-GENERATE (Jika File Hilang)
        if not os.path.exists(csv_path):
            print(f"[AUTO] CSV Missing. Creating default at: {csv_path}")
            try:
                with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['alarmName', 'alarmType', 'instrumentName', 'alarmTripCondition', 'alarmTripOperator', 'alarmTripValue', 'alarmMessage'])
                    for key, val in self.LIMITS.items():
                        if '_' in key:
                            parts = key.rsplit('_', 1)
                            name = parts[0]
                            l_type = parts[1]
                            # Default CSV content
                            row = [f"{name} {l_type}", "Warning", name, f"{name.replace(' ', '_')}_{l_type}", ">", str(val), f"{l_type} Detected"]
                            writer.writerow(row)
            except Exception: pass

        # B. LOAD DATA (Dengan Normalisasi: HAPUS SPASI & UPPERCASE)
        if os.path.exists(csv_path):
            try:
                with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    # Bersihkan header dari spasi tersembunyi
                    if reader.fieldnames:
                        reader.fieldnames = [n.strip() for n in reader.fieldnames]

                    count = 0
                    loaded_keys = []
                    
                    for row in reader:
                        # 1. Ambil Nama Instrumen
                        raw_name = row.get('instrumentName', '').strip()
                        if not raw_name and row.get('alarmName'): # Fallback pintar
                            parts = row['alarmName'].split()
                            if len(parts) >= 2: raw_name = " ".join(parts[:-1])

                        # 2. Ambil Tipe & Nilai
                        alarm_name = row.get('alarmName', '').upper().strip()
                        val_str = row.get('alarmTripValue', '0')
                        
                        try:
                            val_float = float(val_str)
                        except ValueError:
                            continue

                        if 'FT' in raw_name or 'FT' in alarm_name:
                            if 'HH' in alarm_name:
                                if '102' in raw_name or '102' in alarm_name:
                                    self.FLOW_SETPOINT = val_float
                                elif '103' in raw_name or '103' in alarm_name:
                                    self.FLOW_SETPOINT_BW = val_float

                        limit_type = None
                        if 'LL' in alarm_name: limit_type = 'LL'
                        elif 'LO' in alarm_name: limit_type = 'LO'
                        elif 'HH' in alarm_name: limit_type = 'HH'
                        elif 'HI' in alarm_name: limit_type = 'HI'
                        
                        if raw_name and limit_type:
                            try:
                                normalized_key = raw_name.replace(" ", "").replace("-", "").replace("_", "").upper()
                                
                                if normalized_key not in self.limits_config: 
                                    self.limits_config[normalized_key] = {}
                                
                                self.limits_config[normalized_key][limit_type] = float(val_str)
                                count += 1
                                if normalized_key not in loaded_keys: loaded_keys.append(normalized_key)
                            except ValueError: pass

                    print(f"[AUTO] CSV LOADED SUCCESS: {count} rules.")
                    print(f"[DEBUG] Keys in Memory: {loaded_keys}") # Cek ini di terminal!
                    
            except Exception as e:
                print(f"[AUTO] Load Error: {e}") 

    def run(self):
        self.running = True
        self.load_configs()
        self.last_sent_states = {} 
        self.last_tick_time = time.time()
        
        self.latch_state = {'TP_IN': False, 'TP_01': False, 'TP_02': False}
        
        print("[AUTO] Worker Started.")
        self.msleep(1000)

        while self.running:
            # SAFETY CHECK
            if getattr(self.main, 'estop_is_locked', False) or \
               getattr(self.main, 'physical_estop_active', False):
                
                if not self.was_paused:
                    print("[AUTO] PAUSED by SAFETY ESTOP.")
                    self.stop_mbr_sequence_outputs() 
                    self.stop_aeration_group()
                    self.stop_eq_group()
                    self.was_paused = True
                
                self.msleep(500)
                continue
            
            if self.was_paused: self.was_paused = False

            try:
                current_time = time.time()
                delta = current_time - self.last_tick_time
                self.last_tick_time = current_time
                
                # 1. Safety Monitors (Alarm Only)
                self.check_pressure_safety(delta)
                is_full_auto = (self.main.system_mode == "AUTO")
                reqs = getattr(self.main, 'manual_requests', {})

                run_mbr = is_full_auto or reqs.get('MBR_SYS', False)
                run_ae  = is_full_auto or reqs.get('TP_02', False)
                run_eq  = is_full_auto or reqs.get('EQ_SYS', False)

                if getattr(self.main, 'ceb_is_active', False):
                    run_mbr = False
                
                if getattr(self, 'pt_alarm_active', False):
                    # Matikan semua sequence pompa
                    run_mbr = False
                    run_ae = False
                    run_eq = False
                    # Paksa blower menyala selama masa recovery
                    req_blower = True 
                else:
                    req_blower = run_mbr or run_ae

                # --- [TAMBAHAN BARU: CEB SOAKING BLOWER OFF] ---
                if getattr(self.main, 'ceb_blower_force_off', False):
                    req_blower = False
                
                # --- CONTROL LOGIC ---
                if run_eq: 
                    self.logic_equalization(delta)
                elif self.main.system_mode == "AUTO":
                    self.stop_eq_group()

                if run_ae: 
                    self.logic_aeration(delta)
                elif self.main.system_mode == "AUTO":
                    self.stop_aeration_group()

                # Eksekusi MBR
                if run_mbr: 
                    self.logic_mbr_system(delta)
                elif self.main.system_mode == "AUTO": 
                    if not getattr(self.main, 'ceb_is_active', False):
                        self.stop_mbr_sequence_outputs()

                # --- BLOWER CONTROL (VFD LIVE: INTERMITTENT & RUNTIME SWITCHING) ---
                trips = getattr(self.main, 'active_hardware_trips', set())
                trip_a = ('BL_01A' in trips) or ('TRIP_BL_01A' in trips)
                trip_b = ('BL_01B' in trips) or ('TRIP_BL_01B' in trips)

                # 1. Tentukan target blower aktif & proteksi failover trip
                if self.blower_mode == "A_ONLY":
                    target_bl = 'B' if (trip_a and not trip_b) else 'A'
                elif self.blower_mode == "B_ONLY":
                    target_bl = 'A' if (trip_b and not trip_a) else 'B'
                else: # Mode SWITCH
                    target_bl = self.blower_active_suffix
                    # Failover jika blower aktif sedang trip
                    if target_bl == 'A' and trip_a and not trip_b:
                        print("[BLOWER FAILOVER] Blower A Trip! Auto switch ke Blower B.")
                        self.blower_active_suffix = 'B'
                        target_bl = 'B'
                        self.blower_running_accum_timer = 0.0
                        self.blower_intermittent_timer = 0.0
                    elif target_bl == 'B' and trip_b and not trip_a:
                        print("[BLOWER FAILOVER] Blower B Trip! Auto switch ke Blower A.")
                        self.blower_active_suffix = 'A'
                        target_bl = 'A'
                        self.blower_running_accum_timer = 0.0
                        self.blower_intermittent_timer = 0.0

                # 2. Safety jika kedua blower trip
                if trip_a and trip_b and req_blower:
                    self.write_dual_pump('BL_01', 'A', False, is_vfd=True, freq=0.0)
                    self.write_dual_pump('BL_01', 'B', False, is_vfd=True, freq=0.0)
                    req_blower = False

                # 3. Kontrol Operasi Blower
                if req_blower:
                    cycle_time = 4500.0 # 3600s ON + 900s Cooling OFF
                    pos_in_cycle = self.blower_intermittent_timer % cycle_time

                    # A. Cek apakah akumulasi running ON aktif sudah mencapai target shift switching
                    if self.blower_mode == "SWITCH" and self.blower_shift_target > 0 and self.blower_running_accum_timer >= self.blower_shift_target:
                        # Matikan blower aktif saat ini
                        self.write_dual_pump('BL_01', target_bl, False, is_vfd=True, freq=0.0)
                        self.msleep(500)

                        # Tentukan blower berikutnya
                        next_bl = 'B' if target_bl == 'A' else 'A'
                        next_trip = trip_b if next_bl == 'B' else trip_a

                        tot_a_str = f"{self.blower_runtime_total['A']/60.0:.1f}m ({self.blower_runtime_total['A']:.0f}s)"
                        tot_b_str = f"{self.blower_runtime_total['B']/60.0:.1f}m ({self.blower_runtime_total['B']:.0f}s)"

                        if not next_trip:
                            print("================================================================================")
                            print(f"[BLOWER SWITCH] Blower 01{target_bl} mencapai target shift ({self.blower_running_accum_timer:.1f}s / {self.blower_shift_target:.1f}s)!")
                            print(f" -> SWITCHING: Blower 01{target_bl} -> Blower 01{next_bl}")
                            print(f" -> Total Runtime Akumulasi: Blower A = {tot_a_str} | Blower B = {tot_b_str}")
                            print("================================================================================")
                            self.blower_active_suffix = next_bl
                            target_bl = next_bl
                        else:
                            print(f"[BLOWER SWITCH FAILOVER] Target BL_01{next_bl} sedang Trip! Blower 01{target_bl} tetap aktif.")

                        # Reset akumulasi running time & intermittent timer untuk blower berikutnya
                        self.blower_running_accum_timer = 0.0
                        self.blower_intermittent_timer = 0.0
                        pos_in_cycle = 0.0

                        if hasattr(self.main, 'shift_worker') and 'BL_01' in self.main.shift_worker.groups:
                            self.main.shift_worker.groups['BL_01']['Active'] = self.blower_active_suffix

                    # B. Jalankan fase Intermittent (ON vs Cooling OFF)
                    if pos_in_cycle < 3600.0:
                        # Fase ON
                        self.write_dual_pump('BL_01', target_bl, True, is_vfd=True, freq=self.BLOWER_TARGET_HZ)

                        # Akumulasi durasi running nyata dan intermittent timer
                        self.blower_running_accum_timer += delta
                        self.blower_runtime_total[target_bl] += delta
                        self.blower_intermittent_timer += delta

                        # Periodic logging runtime blower ke console (tiap 5-10 detik)
                        now_ts = time.time()
                        log_interval = 5.0 if self.blower_shift_target <= 60.0 else 10.0
                        if (now_ts - self.blower_last_log_time) >= log_interval:
                            self.blower_last_log_time = now_ts
                            sisa_switch = max(0.0, self.blower_shift_target - self.blower_running_accum_timer)
                            pct = (self.blower_running_accum_timer / self.blower_shift_target * 100.0) if self.blower_shift_target > 0 else 0.0
                            tot_a_str = f"{self.blower_runtime_total['A']/60.0:.1f}m ({self.blower_runtime_total['A']:.0f}s)"
                            tot_b_str = f"{self.blower_runtime_total['B']/60.0:.1f}m ({self.blower_runtime_total['B']:.0f}s)"
                            sisa_str = f"{sisa_switch:.1f}s ({sisa_switch/60.0:.2f}m)"

                            if self.blower_mode == "SWITCH":
                                print(f"[BLOWER RUNTIME] Active: BL_01{target_bl} [ON] | Shift: {self.blower_running_accum_timer:.1f}s / {self.blower_shift_target:.1f}s ({pct:.1f}%) | Sisa Menuju Switch: {sisa_str} | Total A: {tot_a_str}, Total B: {tot_b_str}")
                            else:
                                print(f"[BLOWER RUNTIME] Mode: {self.blower_mode} | Active: BL_01{target_bl} [ON] | Total A: {tot_a_str}, Total B: {tot_b_str}")
                    else:
                        # Fase OFF (15 Menit Istirahat/Cooling untuk siklus running > 1 jam)
                        self.write_dual_pump('BL_01', target_bl, False, is_vfd=True, freq=0.0)
                        self.blower_intermittent_timer += delta

                        now_ts = time.time()
                        if (now_ts - self.blower_last_log_time) >= 15.0:
                            self.blower_last_log_time = now_ts
                            sisa_cooling = 4500.0 - pos_in_cycle
                            sisa_switch = max(0.0, self.blower_shift_target - self.blower_running_accum_timer)
                            print(f"[BLOWER COOLING] Active: BL_01{target_bl} [OFF-Cooling] | Sisa Istirahat: {sisa_cooling:.0f}s ({sisa_cooling/60.0:.1f}m) | Shift Timer: {self.blower_running_accum_timer:.1f}s / {self.blower_shift_target:.1f}s (Sisa Switch: {sisa_switch:.1f}s)")
                else:
                    self.blower_intermittent_timer = 0.0
                    if self.main.system_mode == "AUTO":
                        self.write_dual_pump('BL_01', target_bl, False, is_vfd=True, freq=0.0)

            except Exception as e:
                self.error_signal.emit(f"Worker Error: {e}")
            
            self.msleep(500) 

    # --- LOGIC AERASI (TP-02 FEEDING MBR) ---
    def logic_aeration(self, delta):
        suffix_tp02 = self.main.get_active_shift_suffix('TP_02')
        
        # Baca Sensor
        val_ae  = self.main.sensor_data_cache.get('SCALED_LT_102', 0.0) # Sumber
        val_mbr = self.main.sensor_data_cache.get('SCALED_LT_103', 0.0) # Tujuan
        
        # Baca Limit CSV
        limit_mbr_hh = self.get_limit('LT MBR-01', 'HH', default=255.0)
        limit_mbr_hi = self.get_limit('LT MBR-01', 'HI', default=227.0)
        limit_ae_hi  = self.get_limit('LT AE-01', 'HI', default=210.0)
        limit_ae_lo  = self.get_limit('LT AE-01', 'LO', default=199.0)
        
        # 1. MANUAL OVERRIDE
        if self.main.system_mode == "MANUAL":
            req_manual = getattr(self.main, 'manual_requests', {}).get('TP_02', False)
            if req_manual:
                self.write_dual_pump_safe('TP_02', suffix_tp02, True)
            else:
                self.stop_aeration_group()
            return

        # 2. AUTO LOGIC: HYSTERESIS PENGISIAN MBR
        # A. Cek Level Tujuan (MBR)
        if val_mbr >= limit_mbr_hh:
            self.latch_state['TP_02'] = False 
        elif val_mbr <= limit_mbr_hi:
            self.latch_state['TP_02'] = True 

        # 3. EKSEKUSI
        if val_ae <= limit_ae_lo:
            self.stop_aeration_group()
        elif self.latch_state['TP_02']:
            if val_ae >= limit_ae_hi:
                self.write_dual_pump_safe('TP_02', suffix_tp02, True) 
        else:
            self.stop_aeration_group()

    # --- LOGIC EQ (ANOXIC PROGRAM: TP-01 INLET & TP-02 EQ TRANSFER) ---
    def logic_equalization(self, delta):
        suffix_inlet = self.main.get_active_shift_suffix('TP_IN')
        suffix_tp01  = self.main.get_active_shift_suffix('TP_01')
        
        # Baca Sensor STP 50
        ls_101 = self.main.sensor_data_cache.get('LS_101', self.main.sensor_data_cache.get('LS_INLET', 1))
        ls_102 = self.main.sensor_data_cache.get('LS_102', 1)
        lt_101 = self.main.sensor_data_cache.get('SCALED_LT_101', 1.85) # MBR Level (m)
        
        limit_mbr_hh = self.get_limit('LT_101', 'HH', default=2.0)

        # 1. MANUAL OVERRIDE
        if self.main.system_mode == "MANUAL":
            req_inlet = getattr(self.main, 'manual_requests', {}).get('TP_IN', False)
            req_tp01  = getattr(self.main, 'manual_requests', {}).get('TP_01', False)
            req_sm    = getattr(self.main, 'manual_requests', {}).get('SM_01', False)
            self.write_dual_pump('TP_IN', suffix_inlet, req_inlet)
            self.write_dual_pump('TP_01', suffix_tp01, req_tp01)
            self.smart_write('SM_01', req_sm)
            return

        # 2. AUTO LOGIC (ANOXIC PROGRAM SEQUENCES 1-5)
        # Sequence 1 & 2: Inlet Transfer Pump (TP-01A/B)
        # Seq 1 (Inlet Start): LS-101 >= H (1) and LS-102 < H (0)
        # Seq 2 (Inlet Stop): LS-101 <= L (0) or LS-102 >= H (1)
        if ls_101 == 1 and ls_102 == 0:
            self.latch_state['TP_IN'] = True
        elif ls_101 == 0 or ls_102 == 1:
            self.latch_state['TP_IN'] = False

        # Sequence 4 & 5: Equalizing Transfer Pump (TP-02A/B)
        # Seq 4 (EQ Start): LS-102 >= H (1) and LT-101 < HH (2.0 m)
        # Seq 5 (EQ Stop): LS-102 <= L (0) or LT-101 >= HH (2.0 m)
        if ls_102 == 1 and lt_101 < limit_mbr_hh:
            self.latch_state['TP_01'] = True
        elif ls_102 == 0 or lt_101 >= limit_mbr_hh:
            self.latch_state['TP_01'] = False

        # Sequence 3: Submersible Mixer (SM-01 60 min ON / 5 min OFF cycling)
        self.execute_sm_sequence(delta, True)

        # Execution
        self.write_dual_pump_safe('TP_IN', suffix_inlet, self.latch_state.get('TP_IN', False))
        self.write_dual_pump_safe('TP_01', suffix_tp01, self.latch_state.get('TP_01', False))

    def logic_mbr_system(self, delta):
        if getattr(self.main, 'ceb_is_active', False): return

        suffix_mbr = self.main.get_active_shift_suffix('TP_03')
        val_mbr_level = self.main.sensor_data_cache.get('SCALED_LT_101', 1.85)

        limit_hi = self.get_limit('LT_101', 'HI', default=1.85)
        limit_lo = self.get_limit('LT_101', 'LO', default=1.70)
        limit_ll = self.get_limit('LT_101', 'LL', default=1.60)
        ls_103   = self.main.sensor_data_cache.get('LS_103', self.main.sensor_data_cache.get('LS_MBR_BW', 1)) 
        
        # 1. MANUAL OVERRIDE (Fully Manual, Bypass all interlocks)
        if self.main.system_mode == "MANUAL":
            req_mbr_sys = getattr(self.main, 'manual_requests', {}).get('MBR_SYS', False)
            if req_mbr_sys:
                self.mbr_internal_timer += delta
                self.run_mbr_state_machine(suffix_mbr, 1, delta)
            else:
                self.stop_mbr_sequence_outputs()
            return

        self.mbr_internal_timer += delta 

        # 2. AUTO INTERLOCK CHECKS (Step 7 and Step 8)
        # Step 8 (RAS Pump stop): When LT-101 <= LL (1.6m)
        if val_mbr_level <= limit_ll:
            self.latch_state['MBR_SYS'] = False
            self.stop_mbr_sequence_outputs()
            suffix_ras = self.main.get_active_shift_suffix('TP_02')
            self.write_dual_pump('TP_02', suffix_ras, False)
            return

        # Step 7 (Cycle MBR Pause): When LT-101 <= L (1.7m)
        if val_mbr_level <= limit_lo:
            self.latch_state['MBR_SYS'] = False
            self.stop_mbr_sequence_outputs()
            suffix_ras = self.main.get_active_shift_suffix('TP_02')
            self.write_dual_pump('TP_02', suffix_ras, True)
            return

        # Normal Resume / Latch: When LT-101 >= HI (1.85m)
        if val_mbr_level >= limit_hi:
            self.latch_state['MBR_SYS'] = True

        if self.latch_state.get('MBR_SYS', False):
            # Normal Steps 1-6 cycling
            self.run_mbr_state_machine(suffix_mbr, ls_103, delta)
        else:
            self.stop_mbr_sequence_outputs()
            suffix_ras = self.main.get_active_shift_suffix('TP_02')
            self.write_dual_pump('TP_02', suffix_ras, True)

    # --- HELPER FUNCTIONS ---
    def check_pressure_safety(self, delta):
        # Reset timer jika dipindah ke Manual
        if self.main.system_mode == "MANUAL": 
            self.pt_alarm_active = False
            self.pt_alarm_timer = 0.0
            return 
            
        pt_val = self.main.sensor_data_cache.get('SCALED_PT_101', 0.0)
        limit_suction = self.get_limit('PT_101', 'LL', default=-0.12)
        limit_pressure = self.get_limit('PT_101', 'HH', default=0.36)
        
        if getattr(self.main, 'estop_is_locked', False): return
        
        # Cek apakah nilai PT dalam zona bahaya
        is_bad = (pt_val < limit_suction) or (pt_val >= limit_pressure)
        
        if is_bad:
            if not self.pt_alarm_active:
                reason = f"PT Danger ({pt_val:.2f} Bar)"
                print(f"[AUTO SAFETY] {reason} -> Entering 10-Min Recovery Mode (Pumps OFF, Blower ON)")
                self.pt_alarm_active = True
                self.pt_alarm_timer = 0.0
                self.error_signal.emit(f"PT Recovery Mode Active: {pt_val:.2f} Bar")
            else:
                self.pt_alarm_timer += delta 
                
        else:
            if self.pt_alarm_active:
                self.pt_alarm_timer += delta
                if self.pt_alarm_timer >= self.PT_RECOVERY_DURATION:
                    print(f"[AUTO SAFETY] PT Recovery Complete (10 Mins passed & PT Safe). Resuming AUTO.")
                    self.pt_alarm_active = False
                    self.pt_alarm_timer = 0.0
                    self.error_signal.emit("PT Recovery Complete. Resuming Normal AUTO.")

    def calculate_new_hz(self, current_hz, current_flow, target_flow):
        WAIT_TIME = 5.0
        STEP_CHANGE = 1.0
        DEADBAND = 0.2
        MIN_HZ = 0.0
        MAX_HZ = 50.0

        now = time.time()
        if (now - self.tp34_last_check_time) < WAIT_TIME:
            return current_hz
        self.tp34_last_check_time = now
        new_hz = current_hz
        if current_flow > target_flow:
            new_hz -= STEP_CHANGE
        elif current_flow < (target_flow - DEADBAND):
            new_hz += STEP_CHANGE
        new_hz = max(MIN_HZ, min(MAX_HZ, new_hz))
        return new_hz
    
    def calculate_tp04_stabilized(self, current_hz, current_flow, target_flow): 
        WAIT_TIME = 5.0
        STEP_CHANGE = 1.0
        DEADBAND = 0.2
        MIN_HZ = 0.0
        MAX_HZ = 50.0

        now = time.time()
        if (now - self.tp34_last_check_time) < WAIT_TIME:
            return current_hz
        self.tp34_last_check_time = now
        new_hz = current_hz
        if current_flow > target_flow:
            new_hz -= STEP_CHANGE
        elif current_flow < (target_flow - DEADBAND):
            new_hz += STEP_CHANGE
        new_hz = max(MIN_HZ, min(MAX_HZ, new_hz))
        return new_hz

    def run_mbr_state_machine(self, suffix, ls_mbr_bw_status, delta):
        # 1. INISIALISASI VARIABEL SAFETY DELAY
        if not hasattr(self, 'mbr_current_phase'): self.mbr_current_phase = ""
        if not hasattr(self, 'valve_delay_timer'): self.valve_delay_timer = 0.0
        
        self.mbr_internal_timer += delta
        t_service = getattr(self, 'DUR_RUN', 480.0)       # 480s Service (Step 1, 3, 5)
        t_slack   = getattr(self, 'DUR_RELAX', 60.0)      # 60s Slack (Step 2, 4)
        t_bw      = getattr(self, 'DUR_BACKWASH', 120.0)  # 120s Backwash (Step 6)
        
        # Siklus 6 Langkah MBR STP 50:
        # Step 1: Service 1  [0 .. t_service]
        # Step 2: Slack 1    [t_service .. t_service + t_slack]
        # Step 3: Service 2  [.. + t_service]
        # Step 4: Slack 2    [.. + t_slack]
        # Step 5: Service 3  [.. + t_service]
        # Step 6: Backwash   [.. + t_bw]
        p1 = t_service
        p2 = p1 + t_slack
        p3 = p2 + t_service
        p4 = p3 + t_slack
        p5 = p4 + t_service
        total_cycle_time = p5 + t_bw # 1680 s (28 menit)

        current_pos = self.mbr_internal_timer % total_cycle_time

        # Deteksi Step Aktif (1 - 6)
        if current_pos < p1:
            step_num = 1
            current_logical_phase = "SERVICE_1"
        elif current_pos < p2:
            step_num = 2
            current_logical_phase = "SLACK_1"
        elif current_pos < p3:
            step_num = 3
            current_logical_phase = "SERVICE_2"
        elif current_pos < p4:
            step_num = 4
            current_logical_phase = "SLACK_2"
        elif current_pos < p5:
            step_num = 5
            current_logical_phase = "SERVICE_3"
        else:
            step_num = 6
            current_logical_phase = "BACKWASH"

        if self.mbr_current_phase != current_logical_phase:
            self.valve_delay_timer = 0.0
            self.mbr_current_phase = current_logical_phase

        self.valve_delay_timer += delta
        VALVE_OPEN_DELAY = 10.0 # Delay pembukaan motorized valve AV-101/AV-102

        # Selalu pastikan MBR RAS Sludge Return Pump (TP-05A/B) ON selama Step 1-6
        suffix_ras = self.main.get_active_shift_suffix('TP_02')
        self.write_dual_pump('TP_02', suffix_ras, True)

        if step_num in [1, 3, 5]:
            # === SERVICE PHASE (TP-04 Permeate ON, AV-101 Open) ===
            phase_status = f"MBR STEP {step_num} (SERVICE)"
            self.smart_write('ACT_02', False)
            self.smart_write('TP_04', False)
            act01_state = True

            if self.main.system_mode == "MANUAL":
                perm_state = True
            elif self.valve_delay_timer < VALVE_OPEN_DELAY:
                perm_state = False
                phase_status += f" - OPENING AV-101 ({self.valve_delay_timer:.1f}s)"
            else:
                perm_state = True
                phase_status += " - PUMPING PERMEATE"

            if perm_state:
                self.current_hz_tp03 = self.calculate_new_hz(
                    self.current_hz_tp03, 
                    self.main.sensor_data_cache.get('SCALED_FT_102', 0.0), 
                    getattr(self, 'FLOW_SETPOINT', 2.5)
                )

            self.write_dual_pump('TP_03', suffix, perm_state, is_vfd=True, freq=self.current_hz_tp03)
            self.smart_write('ACT_01', act01_state)

        elif step_num in [2, 4]:
            # === SLACK PHASE (Permeate OFF, BW OFF, Blower ON, RAS ON) ===
            phase_status = f"MBR STEP {step_num} (SLACK)"
            self.write_dual_pump('TP_03', suffix, False, is_vfd=True, freq=0)
            self.smart_write('TP_04', False)
            self.smart_write('ACT_01', False)
            self.smart_write('ACT_02', False)

        else:
            # === STEP 6: BACKWASH (TP-03 BW Pump ON, AV-102 Open) ===
            phase_status = "MBR STEP 6 (BACKWASH)"
            self.write_dual_pump('TP_03', suffix, False, is_vfd=True, freq=0)
            self.smart_write('ACT_01', False)
            act02_state = True

            if self.main.system_mode == "MANUAL":
                bw_pump_state = True
            elif ls_mbr_bw_status != 1:
                bw_pump_state = False
                phase_status += " [BLOCKED BY LS-103 DRY]"
            elif self.valve_delay_timer < VALVE_OPEN_DELAY:
                bw_pump_state = False
                phase_status += f" - OPENING AV-102 ({self.valve_delay_timer:.1f}s)"
            else:
                bw_pump_state = True
                phase_status += " - BACKWASH RUNNING"

            self.smart_write('ACT_02', act02_state)
            self.smart_write('TP_04', bw_pump_state, freq=getattr(self, 'current_hz_tp04', 30.0))

        if int(self.mbr_internal_timer * 10) % 20 == 0:
            print(f"   -> Status: {phase_status}")

    def set_sm_duration_config(self, minutes):
        self.sm_duration_minutes = float(minutes)
        print(f"[AUTO] SM Duty Cycle: {self.sm_duration_minutes}m ON / 5m OFF")
    
    def execute_sm_sequence(self, delta, run_requested):
        if not run_requested:
            self.smart_write('SM_01', False)
            return 
        
        self.sm_internal_timer += delta
        cycle_sm = 3900.0 # 65 min (60 min ON, 5 min OFF cycling)
        on_dur = getattr(self, 'sm_duration_minutes', 60.0) * 60.0
        pos_in_sm = self.sm_internal_timer % cycle_sm
        should_be_on = pos_in_sm < on_dur
        self.smart_write('SM_01', should_be_on)

    def stop_mbr_sequence_outputs(self):
        self.smart_write('TP_03A', False, freq=0)
        self.smart_write('TP_03B', False, freq=0)
        self.smart_write('TP_04', False, freq=0)
        self.smart_write('ACT_01', False)
        self.smart_write('ACT_02', False)
        self.mbr_current_phase = ""  
        self.valve_delay_timer = 0.0

    def stop_aeration_group(self):
        self.smart_write('TP_02A', False)
        self.smart_write('TP_02B', False)

    def stop_eq_group(self):
        self.smart_write('TP_IN_A', False)
        self.smart_write('TP_IN_B', False)
        self.smart_write('TP_01A', False)
        self.smart_write('TP_01B', False)
        self.smart_write('SM_01', False)
        self.smart_write('SM_02', False)

    def _clear_group_cache(self, keys):
        for k in keys:
            if k in self.last_sent_states: del self.last_sent_states[k]

    def get_limit(self, sensor_name, limit_type, default=None):
        """
        Mencari limit dengan normalisasi yang sama persis dengan saat loading.
        """
        # 1. Buat Daftar Nama (Nama Asli + Alias)
        candidates = [sensor_name]
        if sensor_name in self.SENSOR_ALIASES:
            candidates.extend(self.SENSOR_ALIASES[sensor_name])
            
        # 2. Cari di Config (Iterasi semua kemungkinan nama)
        for name in candidates:
            # NORMALISASI: Samakan format dengan saat Load (Hapus spasi, strip -, strip _, upper)
            search_key = name.replace(" ", "").replace("-", "").replace("_", "").upper()
            
            if search_key in self.limits_config:
                if limit_type in self.limits_config[search_key]:
                    val = self.limits_config[search_key][limit_type]
                    # UNCOMMENT BARIS INI JIKA INGIN LIHAT BUKTI DI TERMINAL:
                    print(f"[USE CSV] {sensor_name} ({search_key}) [{limit_type}] -> {val}")
                    return val

        # 3. Fallback (Jika CSV gagal)
        print(f"[WARN] Using DEFAULT for {sensor_name} [{limit_type}] -> {default}")
        if default is not None: 
            return default
            
        return 0.0

    def smart_write(self, key, state, freq=0):
        final_freq = float(freq) if state else 0.0
        if key in self.last_sent_states:
            last_state, last_freq = self.last_sent_states[key]
            if last_state == state and abs(last_freq - final_freq) < 0.1:
                return
        self.last_sent_states[key] = (state, final_freq)
        self.request_write_hardware.emit(key, state, final_freq)

    def write_dual_pump(self, group, suffix, state, is_vfd=False, freq=0.0):
        key_a = f"{group}A" if group != 'TP_IN' else 'TP_IN_A'
        key_b = f"{group}B" if group != 'TP_IN' else 'TP_IN_B'
        final_freq = freq if (state and is_vfd) else 0.0
        if suffix == 'A':
            self.smart_write(key_a, state, freq=final_freq)
            self.smart_write(key_b, False, freq=0)
        else:
            self.smart_write(key_a, False, freq=0)
            self.smart_write(key_b, state, freq=final_freq)

    def write_dual_pump_safe(self, group, suffix, state):
        key_a = f"{group}A" if group != 'TP_IN' else 'TP_IN_A'
        key_b = f"{group}B" if group != 'TP_IN' else 'TP_IN_B'
        
        # If in MANUAL mode, bypass all trips and write directly
        if self.main.system_mode == "MANUAL":
            self.write_dual_pump(group, suffix, state, is_vfd=False)
            return

        trips = self.main.active_hardware_trips
        trip_a = key_a in trips
        trip_b = key_b in trips
        if trip_a and trip_b and state:
            self.trigger_emergency(f"TRIP: Both pumps {group} Failed!")
            return
        target_suffix = suffix
        if suffix == 'A' and trip_a: target_suffix = 'B'
        if suffix == 'B' and trip_b: target_suffix = 'A'
        self.write_dual_pump(group, target_suffix, state, is_vfd=False)

    def trigger_emergency(self, reason):
        self.main.handle_soft_emergency(reason)
        self.msleep(1000)

    def stop(self):
        self.running = False
        self.wait()

class SensorPollWorker(QThread):
    data_updated = pyqtSignal(dict)  # Signal to send data to GUI

    def __init__(self, io_controller, main_mutex, client_bl, mutex_bl):
        super().__init__()
        self.io_controller = io_controller
        self.mutex = main_mutex
        
        self.client_bl = client_bl
        self.mutex_bl = mutex_bl
        
        self.running = True

    def check_and_reconnect(self, client_attr_name, port_name, default_port):
        """
        Fungsi untuk mengecek dan melakukan auto-reconnect jika koneksi terputus.
        Sangat penting untuk kestabilan koneksi Serial USB Waveshare di Linux (ttyACM) & Windows (COM).
        Jika port serial disconnect di level OS / kabel dicabut-pasang, socket lama di-reset secara tuntas.
        """
        client = getattr(self.io_controller, 'conn', None) if client_attr_name == 'main' else self.client_bl
        if client is None:
            return
            
        try:
            is_open = False
            try:
                is_open = client.is_socket_open()
            except Exception:
                is_open = False

            if not is_open:
                print(f"[MODBUS WARNING] {port_name} disconnected! Attempting to reconnect...")
                safe_flush_buffers(client)
                try:
                    client.close()
                except Exception:
                    pass
                self.msleep(300)  # Beri waktu hardware reset (300ms)
                
                # Deteksi jika nama port serial berubah di Linux
                exclude = [getattr(self.client_bl, 'port', None)] if client_attr_name == 'main' else [getattr(getattr(self.io_controller, 'conn', None), 'port', None)]
                best_port = get_best_serial_port(getattr(client, 'port', default_port), exclude=exclude)
                if best_port and hasattr(client, 'port'):
                    client.port = best_port

                # Coba koneksi ulang
                reconnected = False
                try:
                    reconnected = client.connect()
                except Exception as ce:
                    print(f"[MODBUS RETRY] {port_name} connect exception: {ce}")
                    reconnected = False

                if reconnected:
                    safe_flush_buffers(client)
                    print(f"[MODBUS SUCCESS] {port_name} reconnected successfully on {getattr(client, 'port', default_port)}.")
                else:
                    print(f"[MODBUS ERROR] {port_name} failed to reconnect.")
        except Exception as e:
            print(f"[MODBUS ERROR] Reconnect logic for {port_name} failed: {e}")

    def run(self):
        # Normal priority allows GUI and E-Stop (TimeCritical) to preempt this
        self.setPriority(QThread.NormalPriority) 
        
        # Mencoba mengambil referensi main_client (pymodbus) dari io_controller
        main_client = getattr(self.io_controller, 'conn', getattr(self.io_controller, 'client', getattr(self.io_controller, '_client', None)))

        consecutive_main_failures = 0
        consecutive_bl_failures = 0

        while self.running:
            new_data = {}
            
            # --- 1. JALANKAN LOGIKA AUTO-RECONNECT ---
            if main_client:
                self.check_and_reconnect('main', "Main Modbus (USR)", SERIAL_PORT)
            if self.client_bl:
                self.check_and_reconnect('bl', "Blower Modbus (VFD)", SERIAL_PORT_BL)

            main_cycle_success = False
            bl_cycle_success = False

            # --- 2. BACA DIGITAL INPUT (DI) DENGAN BULK READ ---
            # Menggunakan Bulk Read untuk Slave 1 dan Slave 2 (hanya 2 query bukannya 15 query!)
            if self.mutex.tryLock(120):
                try:
                    bulk_s1 = None
                    bulk_s2 = None
                    if main_client:
                        # Coba baca 8 discrete input Slave 1 (addr 0..7)
                        try:
                            r1 = main_client.read_discrete_inputs(address=0, count=8, slave=1)
                            if not r1.isError() and hasattr(r1, 'bits') and len(r1.bits) >= 8:
                                bulk_s1 = r1.bits
                        except Exception:
                            bulk_s1 = None

                        # Coba baca 8 discrete input Slave 2 (addr 0..7)
                        try:
                            r2 = main_client.read_discrete_inputs(address=0, count=8, slave=2)
                            if not r2.isError() and hasattr(r2, 'bits') and len(r2.bits) >= 8:
                                bulk_s2 = r2.bits
                        except Exception:
                            bulk_s2 = None

                    # Petakan ke new_data
                    for key, cfg in IO_MAP.items():
                        if cfg['type'] == 'DI' and key != 'EMC':
                            s = cfg['slave']
                            addr = cfg['addr']
                            val = None
                            if s == 1 and bulk_s1 is not None and addr < len(bulk_s1):
                                val = 1 if bulk_s1[addr] else 0
                            elif s == 2 and bulk_s2 is not None and addr < len(bulk_s2):
                                val = 1 if bulk_s2[addr] else 0
                            else:
                                # Fallback jika modul tidak merespons bulk read
                                val = self.io_controller.digitalInput(addr, s)

                            if val is not None: 
                                new_data[key] = val
                                new_data[f"STATUS_{key}"] = "OK"
                                main_cycle_success = True
                            else:
                                new_data[f"STATUS_{key}"] = "ERR"
                except Exception as e: 
                    print(f"[SENSOR READ ERROR] Failed scanning DIs: {e}")
                    safe_flush_buffers(main_client)
                finally: 
                    self.mutex.unlock()
            
            # YIELD: Jeda 50ms untuk memberi ruang perangkat lain
            self.msleep(50)

            # --- 3. BACA VFD BLOWER A (SLAVE 2) ---
            # Menggunakan client_bl dan mutex_bl
            if self.client_bl:
                is_open = False
                try: is_open = self.client_bl.is_socket_open()
                except Exception: is_open = False

                if is_open:
                    if self.mutex_bl.tryLock(50):
                        try:
                            # Baca Slave 2
                            rr = self.client_bl.read_holding_registers(0x1003, 2, slave=2)
                            if not rr.isError():
                                new_data['VFD_A_VOLT'] = float(rr.registers[0]) 
                                new_data['VFD_A_AMP']  = float(rr.registers[1]) 
                                new_data['STATUS_VFD_A'] = "OK"
                                bl_cycle_success = True
                            else:
                                new_data['STATUS_VFD_A'] = "ERR"
                                safe_flush_buffers(self.client_bl)
                                print(f"[BLOWER ERROR] VFD A (Slave 2) returned Modbus Error")
                        except Exception as e: 
                            new_data['STATUS_VFD_A'] = "ERR"
                            safe_flush_buffers(self.client_bl)
                            print(f"[BLOWER EXCEPTION] VFD A: {e}")
                        finally:
                            self.mutex_bl.unlock()
                else:
                    new_data['STATUS_VFD_A'] = "ERR"

            self.msleep(50)

            # --- 4. BACA VFD BLOWER B (SLAVE 3) ---
            if self.client_bl:
                is_open = False
                try: is_open = self.client_bl.is_socket_open()
                except Exception: is_open = False

                if is_open:
                    if self.mutex_bl.tryLock(50):
                        try:
                            # Baca Slave 3
                            rr = self.client_bl.read_holding_registers(0x1003, 2, slave=3)
                            if not rr.isError():
                                new_data['VFD_B_VOLT'] = float(rr.registers[0])
                                new_data['VFD_B_AMP']  = float(rr.registers[1]) / 100.0
                                new_data['STATUS_VFD_B'] = "OK"
                                bl_cycle_success = True
                            else:
                                new_data['STATUS_VFD_B'] = "ERR"
                                safe_flush_buffers(self.client_bl)
                                print(f"[BLOWER ERROR] VFD B (Slave 3) returned Modbus Error")
                        except Exception as e: 
                            new_data['STATUS_VFD_B'] = "ERR"
                            safe_flush_buffers(self.client_bl)
                            print(f"[BLOWER EXCEPTION] VFD B: {e}")
                        finally:
                            self.mutex_bl.unlock()
                else:
                    new_data['STATUS_VFD_B'] = "ERR"

            self.msleep(50)

            # --- 5. BACA ANALOG SENSORS (AI) ---
            # We read one by one and release lock in between
            analogs = ['LT_101', 'LT_102', 'LT_103', 'FT_101', 'FT_102', 'FT_103', 'PT_101']
            
            for key in analogs:
                if not self.running: break
                
                # Try lock for short duration (50ms)
                if self.mutex.tryLock(50): 
                    try:
                        val = self._safe_read_ai(key)
                        if val is not None:
                            new_data[key] = val
                            new_data[f"STATUS_{key}"] = "OK"
                            main_cycle_success = True
                        else:
                            new_data[key] = 0.0
                            new_data[f"STATUS_{key}"] = "ERR"
                            safe_flush_buffers(main_client)
                    except Exception as e: 
                        new_data[key] = 0.0
                        new_data[f"STATUS_{key}"] = "ERR"
                        safe_flush_buffers(main_client)
                        print(f"[SENSOR READ ERROR] Failed reading AI {key}: {e}")
                    finally: 
                        self.mutex.unlock()
                
                self.msleep(50) 

            # --- WATCHDOG RECONNECT LOGIC ---
            if main_client:
                if not main_cycle_success:
                    consecutive_main_failures += 1
                    if consecutive_main_failures >= 3:
                        print(f"[WATCHDOG] Main Modbus Offline ({consecutive_main_failures} failures). Force reconnecting...")
                        for key in IO_MAP:
                            if IO_MAP[key]['slave'] != 2 and IO_MAP[key]['slave'] != 3:
                                new_data[f"STATUS_{key}"] = "ERR"
                        try:
                            safe_flush_buffers(main_client)
                            main_client.close()

                            # Jika macet berulang >= 5 kali, lakukan Software USB power-cycle di Linux
                            if consecutive_main_failures >= 5:
                                reset_linux_usb_for_port(getattr(main_client, 'port', SERIAL_PORT))
                                self.msleep(500)

                            # Cek apakah port serial berubah di Linux
                            active_port = get_best_serial_port(getattr(main_client, 'port', SERIAL_PORT), exclude=[SERIAL_PORT_BL])
                            if active_port and active_port != getattr(main_client, 'port', None):
                                print(f"[WATCHDOG] Switching Main Modbus port: {main_client.port} -> {active_port}")
                                main_client.port = active_port

                            self.msleep(300)
                            if main_client.connect():
                                safe_flush_buffers(main_client)
                                print(f"[WATCHDOG] Main Modbus reconnected successfully on {main_client.port}")
                        except Exception as e:
                            print(f"[WATCHDOG ERROR] Main Modbus close/connect failed: {e}")
                else:
                    consecutive_main_failures = 0

            if self.client_bl:
                if not bl_cycle_success:
                    consecutive_bl_failures += 1
                    if consecutive_bl_failures >= 3:
                        print(f"[WATCHDOG] Blower Modbus Offline ({consecutive_bl_failures} failures). Force reconnecting...")
                        new_data['STATUS_VFD_A'] = "ERR"
                        new_data['STATUS_VFD_B'] = "ERR"
                        try:
                            safe_flush_buffers(self.client_bl)
                            self.client_bl.close()

                            if consecutive_bl_failures >= 5:
                                reset_linux_usb_for_port(getattr(self.client_bl, 'port', SERIAL_PORT_BL))
                                self.msleep(500)

                            active_bl_port = get_best_serial_port(getattr(self.client_bl, 'port', SERIAL_PORT_BL), exclude=[getattr(main_client, 'port', SERIAL_PORT)])
                            if active_bl_port and active_bl_port != getattr(self.client_bl, 'port', None):
                                print(f"[WATCHDOG] Switching Blower Modbus port: {self.client_bl.port} -> {active_bl_port}")
                                self.client_bl.port = active_bl_port

                            self.msleep(300)
                            if self.client_bl.connect():
                                safe_flush_buffers(self.client_bl)
                                print(f"[WATCHDOG] Blower Modbus reconnected successfully on {self.client_bl.port}")
                        except Exception as e:
                            print(f"[WATCHDOG ERROR] Blower Modbus close/connect failed: {e}")
                else:
                    consecutive_bl_failures = 0

            # --- 6. KIRIM UPDATE KE GUI ---
            if new_data:
                self.data_updated.emit(new_data)

            # Rest before next full scan cycle
            self.msleep(500)

    def _safe_read_ai(self, key):
        cfg = IO_MAP.get(key)
        if not cfg: return None
        
        try:
            val = self.io_controller.analogInput(cfg['addr'], cfg['slave'], use_holding=False)
            if val is not None: return val 
        except Exception as e: 
            print(f"[SAFE READ AI ERROR] Input Register {key}: {e}")
            
        try:
            val = self.io_controller.analogInput(cfg['addr'], cfg['slave'], use_holding=True)
            if val is not None: return val
        except Exception as e: 
            print(f"[SAFE READ AI ERROR] Holding Register {key}: {e}")
            
        return None

    def stop(self):
        self.running = False
        self.wait()

class TouchInputFilter(QObject):
    def __init__(self, parent_controller):
        super().__init__(parent_controller)
        self.controller = parent_controller

    def eventFilter(self, obj, event):
        # Deteksi klik pada LineEdit atau SpinBox
        if event.type() == QEvent.MouseButtonPress and not obj.isReadOnly():
            if isinstance(obj, (QtWidgets.QLineEdit, QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                # Buka Numpad
                self.controller.open_numpad(target_widget=obj)
                return True 
        return False

class MainSystemController(QWidget):
    ui_update_signal = pyqtSignal(str, bool)
    
    def __init__(self, user_role="guest", username="Guest"):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.current_user = username
        self.current_role = user_role
        print(f"[SYSTEM] Logged in as: {self.current_user} (Role: {self.current_role})")
        
        # 1. LOAD UI
        ui_name = "STP50.ui" if os.path.exists(os.path.join(os.path.dirname(__file__), "STP50.ui")) else "STP-FF.ui"
        self.ui_path = os.path.join(os.path.dirname(__file__), ui_name)
        try:
            uic.loadUi(self.ui_path, self)
            self.ui_update_signal.connect(self.process_ui_update)
            if hasattr(self, 'lbl_pid_bg'):
                pid_img_path = os.path.join(os.path.dirname(__file__), "Assets", "pid_merdeka_stp50.png")
                if os.path.exists(pid_img_path):
                    self.lbl_pid_bg.setPixmap(QPixmap(pid_img_path))
                    self.lbl_pid_bg.setScaledContents(True)
                    print("✅ P&ID Background Image Loaded Successfully!")
            self.init_instrument_page()
            self.setup_data_table()
        except FileNotFoundError:
            print("ERR: File UI tidak ditemukan!")
            sys.exit(1)

        self.setWindowTitle("DIAC-X Controller")
        self.load_external_stylesheet()
        
        # 2. GLOBAL STATES
        self.is_auto = False
        self.system_mode = "MANUAL" 
        self.estop_active = False   
        self.physical_estop_active = False 
        self.estop_is_locked = False
        self.ceb_is_active = False
        self.soft_emergency_active = False
        self.saved_blower_hz = 45.0
        
        self.active_hardware_trips = set()
        self.critical_alarms_active = set()
        self.system_state = {} 
        self.vfd_frequencies = {
            'BL_01A': 0.0, 'BL_01B': 0.0,
            'TP_03A': 0.0, 'TP_03B': 0.0,
            'TP_04': 0.0
        }
        self.last_ls_state = -1 
        self.last_log_pos = 0
        self.last_log_mtime = 0
        self.load_runtimes()
        self.init_runtime_table()
        self.setup_totalizer_table() 
        self.load_totalizer_history_to_table()
        self.last_runtime_save = time.time()

        self.manual_requests = {
            'TP_02': False,    # Aeration
            'TP_IN': False,    # Inlet
            'TP_01': False,    # EQ Transfer
            'SM': False,       # Mixer
            'MBR_SYS': False   # MBR Cycle (TP-03, TP-04, Backwash)
        }

        self.sensor_data_cache = {
            'LS_INLET': 0, 
            'LT_101': 4.0, 
            'LT_102': 4.0, 
            'LT_103': 4.0, 
            'FT_101': 4.0, 'FT_102': 4.0, 'FT_103': 4.0, # Default Flow 0
            'PT_101': 4.0  # Default Pressure 0
        }

        self.smart_active_flags = {
        'TP_02': False,     # Untuk Aerasi
        'EQ_GROUP': False,  # Untuk Inlet, TP-01, SM
        'MBR_GROUP': False  # Untuk TP-03, TP-04, Siklus
        }

        # Constants
        self.AREA_FT101 = 0.5   
        self.AREA_FT102 = 1.2   
        self.AREA_FT103 = 0.8   
        self.load_flow_settings()

        # 3. INIT HARDWARE
        self.threadpool = QThreadPool()
        self.modbus_mutex = QMutex()
        self.mutex_bl = QMutex()
        
        self.modbus_client = ModbusSerialClient(
            port=SERIAL_PORT, baudrate=BAUDRATE, parity=PARITY, 
            stopbits=STOPBITS, bytesize=BYTESIZE, timeout=0.2, retries=1
        )
        
        # Client Blower
        self.client_bl = ModbusSerialClient(
            port=SERIAL_PORT_BL, baudrate=BAUDRATE, parity=PARITY, 
            stopbits=STOPBITS, bytesize=BYTESIZE, timeout=0.2
        )

        try:
            if self.modbus_client.connect(): 
                print(f"✅ Connected to Modbus: {SERIAL_PORT}")
            else:
                print(f"❌ Failed to connect to Modbus: {SERIAL_PORT} (Hardware missing or port invalid)")
        except Exception as e:
            print(f"⚠️ Modbus connection failed: {e}")

        try:
            if self.client_bl.connect():   
                print(f"✅ Connected to Blower Line: {SERIAL_PORT_BL}")
            else:
                print(f"❌ Failed to connect to Blower Line: {SERIAL_PORT_BL} (Hardware missing or port invalid)")
        except Exception as e:
            print(f"⚠️ Blower line connection failed: {e}")

        self.io_controller = USRIOController(self.modbus_client)

        # 4. LOGGERS
        self.logger = LogManager(os.path.join(os.path.dirname(__file__), "datalog_activity"))
        self.sensor_keys = [
            "LT_EQ_01", "LT_AE_01", "LT_MBR_01", 
            "FT_101_Rate", "FT_102_Rate", "FT_103_Rate", "PT_101_Pressure", 
            "BL_A_Volt", "BL_A_Amp", "BL_B_Volt", "BL_B_Amp",
            "FT_101_TOTAL", "FT_102_TOTAL", "FT_103_TOTAL"
        ]
        self.sensor_logger = SensorLogger(os.path.join(os.path.dirname(__file__), "datalog_sensors"), self.sensor_keys)

        # 5. UI INITIALIZATION
        if hasattr(self, 'tableWidget'):
            self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch) 
        if hasattr(self, 'openedSideBar'): self.openedSideBar.setVisible(True)
        if hasattr(self, 'closedSideBar'): self.closedSideBar.setVisible(False)

        # Align STP 50 PFD sensor badges (keep UI file geometry)
        for name in ['flow_FT101', 'flow_FT102', 'flow_FT103', 'flow_PT101', 'flow_LT101', 'flow_DO101', 'txt_LS_101', 'txt_LS_102', 'txt_LS_103']:
            lbl = getattr(self, name, None)
            if lbl:
                lbl.setAlignment(Qt.AlignCenter)

        # Pipe Config (Authentic FFI Pipe Labels)
        self.pipe_mapping = {
            'TP_IN_A': ['label_43', 'label_4', 'label_50', 'label_5', 'label_136'],
            'TP_IN_B': ['label_42', 'label_137', 'label_4', 'label_50', 'label_5', 'label_136'],
            'TP_01A':  ['label_37', 'label_8', 'label_10', 'label_9', 'label_12', 'label_20'],
            'TP_01B':  ['label_36', 'label_9', 'label_12', 'label_20'],
            'TP_02A':  ['label_34', 'label_27', 'label_35', 'label_21', 'label_22', 'label_23', 'label_24', 'label_25'],
            'TP_02B':  ['label_33', 'label_21', 'label_22', 'label_23', 'label_24', 'label_25'],
            'TP_03A':  ['label_28', 'label_74', 'label_146', 'label_38', 'label_40', 'label_148', 'label_73', 'label_149', 'label_29', 'label_26', 'label_30', 'label_46'],
            'TP_03B':  ['label_28', 'label_74', 'label_146', 'label_38', 'label_39', 'label_41', 'label_40', 'label_148', 'label_73', 'label_149', 'label_29', 'label_26', 'label_30', 'label_46'],
            'TP_04':   ['label_154', 'label_11', 'label_103', 'label_153', 'label_152'],
            'DP_01':   ['label_32', 'label_173', 'label_92', 'label_174']
        }
        self.init_pipe_manager()
        self.init_control_buttons()
        self.init_main_navigation()
        self.init_maintenance_buttons()
        self.init_alarm_page_logic()
        self.update_mode_ui()

        # Alarm & Buzzer
        self.active_alarm_widgets = {}
        self.active_toasts = {}
        self.init_alarm_monitor()
        self.alarm_monitor.alarm_triggered_signal.connect(self.handle_alarm_triggered)
        self.alarm_monitor.alarm_resolved_signal.connect(self.handle_alarm_resolved)    
        self.alarm_monitor.auto_maintenance_signal.connect(self.handle_auto_maintenance)
        self.alarm_monitor.alarm_value_update_signal.connect(self.handle_alarm_value_update)
        
        self.buzzer_snooze_timer = QTimer(self)
        self.buzzer_snooze_timer.setSingleShot(True)
        self.buzzer_snooze_timer.timeout.connect(self.handle_snooze_timeout)
        self.SNOOZE_DURATION = 10 * 60 * 1000 
        self.manual_alarm_active = False
        if hasattr(self, 'btn_alarm'): self.btn_alarm.clicked.connect(self.on_btn_alarm_click)

        # [RESTORED] TIMER EVENT LOG & SENSOR DATA
        self.timer_event_log = QTimer(self)
        self.timer_event_log.timeout.connect(self.refresh_event_log_ui)
        self.timer_event_log.start(2000) 

        # [RESTORED] TIMER SENSOR (LOGIC MAIN_APP.PY)
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.process_sensor_data)
        self.data_timer.start(1000)

        if hasattr(self, 'logList'):
            self.logList.itemClicked.connect(self.on_maintenance_list_clicked)
        if hasattr(self, 'pushButton'):
            try: self.pushButton.clicked.disconnect() 
            except: pass
            self.pushButton.clicked.connect(self.action_toggle_status)
        if hasattr(self, 'pushButton_2'):
            self.pushButton_2.clicked.connect(self.save_maintenance_description)
        
        # Workers
        self.estop_monitor = FastEstopMonitor(self.io_controller, self.modbus_mutex)
        self.estop_monitor.estop_active_signal.connect(self.handle_estop_active)
        self.estop_monitor.estop_cleared_signal.connect(self.handle_estop_cleared)
        self.estop_monitor.start() 

        self.sensor_worker = SensorPollWorker(
            self.io_controller, 
            self.modbus_mutex,   # Mutex USR Main
            self.client_bl, 
            self.mutex_bl    
        )
        self.sensor_worker.data_updated.connect(self.update_sensor_cache)
        self.sensor_worker.start()

        self.dashboard_components = [
            getattr(self, 'btn_TP_IN_A', None), getattr(self, 'btn_TP_IN_B', None),
            getattr(self, 'btn_TP_01A', None),  getattr(self, 'btn_TP_01B', None),
            getattr(self, 'btn_TP_02A', None),  getattr(self, 'btn_TP_02B', None),
            getattr(self, 'btn_TP_03A', None),  getattr(self, 'btn_TP_03B', None),
            getattr(self, 'btn_TP_04', None),
            getattr(self, 'btn_BL_01A', None),  getattr(self, 'btn_BL_01B', None),
            getattr(self, 'btn_SM_01', None),   getattr(self, 'btn_SM_02', None),
            getattr(self, 'btn_DP_01', None),
            getattr(self, 'btn_AV101', None),   getattr(self, 'btn_AV102', None),
        ]
        self.dashboard_components = [btn for btn in self.dashboard_components if btn is not None]

        print("Sistem Ready...")

        self.shift_worker = SmartShiftWorker(self)
        self.shift_worker.lock_component.connect(self.handle_component_lock)
        self.shift_worker.unlock_component.connect(self.handle_component_unlock)
        self.shift_worker.critical_failure_detected.connect(self.handle_critical_failure)
        self.shift_worker.start()

        self.auto_worker = AutoPilotWorker(self)
        self.auto_worker.update_ui_signal.connect(self.handle_auto_signals)
        self.auto_worker.request_write_hardware.connect(self.handle_auto_worker_command)
        self.auto_worker.error_signal.connect(lambda msg: print(f"[AUTO ERR] {msg}"))
        self.auto_worker.start()
        self.auto_worker.setPriority(QThread.TimeCriticalPriority)
        self.auto_worker.emergency_stop_signal.connect(self.handle_soft_emergency)

        # [REMOVED] SensorWorker (KARENA MAIN_APP.PY TIDAK PAKAI INI)
        
        self.refresh_event_log_ui()
        
        self.sensor_config = {
            'label_Inletwater_2': {'max': 1.0, 'type': 'discrete'},
            'label_EQ1water_2':   {'max': 1.0, 'type': 'discrete'},
            'label_AE1water2':    {'max': 230.0, 'type': 'linear'},
            'label_mbrwater2':    {'max': 2.5, 'type': 'linear'},
            'label_tankwater2':   {'max': 1.0, 'type': 'discrete'},
        }
        self.tank_geometry = {} 
        self.init_tank_geometry()

        self.equipment_map = {
            'TP_01A':   {'do': 'TP_01A',   'di_trip': 'TRIP_TP_01A'},
            'TP_01B':   {'do': 'TP_01B',   'di_trip': 'TRIP_TP_01B'},
            'TP_02A':   {'do': 'TP_02A',   'di_trip': 'TRIP_TP_02A'},
            'TP_02B':   {'do': 'TP_02B',   'di_trip': 'TRIP_TP_02B'},
            'TP_04A':   {'do': 'TP_04A',   'di_trip': 'TRIP_TP_04A'},
            'TP_04B':   {'do': 'TP_04B',   'di_trip': 'TRIP_TP_04B'},
            'TP_03':    {'do': 'TP_03',    'di_trip': 'TRIP_TP_03'},
            'TP_05A':   {'do': 'TP_05A',   'di_trip': 'TRIP_TP_05A'},
            'TP_05B':   {'do': 'TP_05B',   'di_trip': 'TRIP_TP_05B'},
            'BL_01A':   {'do': 'BL_01A',   'di_trip': 'TRIP_BL_01A'},
            'BL_01B':   {'do': 'BL_01B',   'di_trip': 'TRIP_BL_01B'},
            'SM_01':    {'do': 'SM_01',    'di_trip': 'TRIP_SM_01'},
            'DP_01':    {'do': 'DP_01',    'di_trip': 'TRIP_DP_01'},
            # Aliases for compatibility
            'TP_IN_A':  {'do': 'TP_01A',   'di_trip': 'TRIP_TP_01A'},
            'TP_IN_B':  {'do': 'TP_01B',   'di_trip': 'TRIP_TP_01B'},
            'TP_03A':   {'do': 'TP_04A',   'di_trip': 'TRIP_TP_04A'},
            'TP_03B':   {'do': 'TP_04B',   'di_trip': 'TRIP_TP_04B'},
            'TP_04':    {'do': 'TP_03',    'di_trip': 'TRIP_TP_03'},
            'SM_02':    {'do': 'SM_01',    'di_trip': 'TRIP_SM_01'},
        }
        
        QTimer.singleShot(500, self.initial_system_sync)
        QTimer.singleShot(1000, self.restore_last_state)
        print("Sistem Ready...")

    @pyqtSlot(str, bool, float)
    def handle_auto_worker_command(self, key, state, freq):
        self.run_in_background(self.direct_write_hardware, key, state, freq)

    def load_flow_settings(self):
        """Load Luas Penampang Pipa dari JSON"""
        json_path = os.path.join(os.path.dirname(__file__), "data_flow_settings.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                    self.AREA_FT101 = float(data.get("area_ft101", 1.0))
                    self.AREA_FT102 = float(data.get("area_ft102", 1.0))
                    self.AREA_FT103 = float(data.get("area_ft103", 1.0))
            except Exception as e:
                print(f"Error loading flow settings: {e}")

    # --- [NEW] TOTALIZER MANAGEMENT ---
    def load_totalizers(self):
        """Load nilai totalizer terakhir dari JSON agar tidak reset 0 saat restart"""
        # Default nilai 0.0
        self.totalizers = {
            'FT_101': 0.0, 'FT_102': 0.0, 'FT_103': 0.0
        }
        self.last_totalizer_time = time.time()
        
        path = "data_totalizers.json"
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    saved = json.load(f)
                    # Update hanya key yang cocok agar aman
                    for k, v in saved.items():
                        if k in self.totalizers:
                            self.totalizers[k] = float(v)
                print(f"[SYSTEM] Totalizers Loaded: {self.totalizers}")
            except Exception as e: 
                print(f"[SYSTEM] Error loading totalizers: {e}")

    def save_totalizers(self):
        """Simpan nilai totalizer ke file"""
        if not hasattr(self, 'totalizers'): return
        try:
            with open("data_totalizers.json", "w") as f:
                json.dump(self.totalizers, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"[SYSTEM] Failed to save totalizers: {e}")
    
    # --- [FITUR BARU] RUNTIME HOUR METER ---
    def load_runtimes(self):
        """Load jam kerja (dalam detik) dari JSON"""
        self.runtime_counters = {} 
        path = "data_runtime.json"
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    raw_data = json.load(f)
                for tag, val in raw_data.items():
                    if isinstance(val, dict):
                        self.runtime_counters[tag] = float(val.get("runtime_seconds", 0.0))
                    else:
                        self.runtime_counters[tag] = float(val) 
                print(f"[SYSTEM] Runtime Data Loaded ({len(self.runtime_counters)} items).") 
            except Exception as e:
                print(f"[SYSTEM] Error loading runtimes: {e}")

    def save_runtimes(self): 
        try:
            data_to_save = {} 
            if hasattr(self, 'equipment_map'):
                for tag, config in self.equipment_map.items(): 
                    total_sec = self.runtime_counters.get(tag, 0.0) 
                    is_running = self.system_state.get(config['do'], False) 
                    is_tripped = (self.sensor_data_cache.get(config['di_trip'], 0) == 1) 
                    data_to_save[tag] = {
                        "runtime_seconds": total_sec,
                        "last_status_running": is_running, # Menyimpan status DO
                        "last_status_trip": is_tripped     # Menyimpan status DI
                    }
            else:
                data_to_save = self.runtime_counters 
            with open("data_runtime.json", "w") as f:
                json.dump(data_to_save, f, indent=4)
                f.flush()
                os.fsync(f.fileno()) 
        except Exception as e:
            print(f"[SYSTEM] Failed to save runtimes: {e}")
            
    def init_runtime_table(self):
        """Setup tampilan tabel Runtime (Hanya dipanggil sekali saat init)"""
        if not hasattr(self, 'tableWidget_runtime'): return

        # 1. Setup Header (3 Kolom: Tag, Runtime, Status)
        headers = ["Equipment Tag", "Total Runtime (HH:MM:SS)", "Status"]
        self.tableWidget_runtime.setColumnCount(len(headers))
        self.tableWidget_runtime.setHorizontalHeaderLabels(headers)
        
        # 2. Styling
        header = self.tableWidget_runtime.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Tag melebar
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Runtime melebar
        header.setSectionResizeMode(2, QHeaderView.Fixed)   # Status fixed
        self.tableWidget_runtime.setColumnWidth(2, 100)
        
        self.tableWidget_runtime.verticalHeader().setVisible(False)
        self.tableWidget_runtime.setAlternatingRowColors(True)
        self.tableWidget_runtime.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # 3. Pre-fill Rows (Agar tidak perlu remove/add row tiap detik)
        # Kita scan semua DO dari IO_MAP
        self.runtime_row_map = {} # Cache untuk menyimpan index baris: {'TP_01A': 0, 'TP_01B': 1...}
        
        row_idx = 0
        sorted_keys = sorted(IO_MAP.keys()) # Sort abjad agar rapi
        
        for key in sorted_keys:
            if IO_MAP[key]['type'] == 'DO' and key != 'ALARM':
                self.tableWidget_runtime.insertRow(row_idx)
                
                # Col 0: Tag Name
                self.tableWidget_runtime.setItem(row_idx, 0, QTableWidgetItem(key))
                
                # Col 1: Runtime Placeholder
                self.tableWidget_runtime.setItem(row_idx, 1, QTableWidgetItem("00:00:00"))
                
                # Col 2: Status Placeholder
                status_item = QTableWidgetItem("STOPPED")
                status_item.setTextAlignment(Qt.AlignCenter)
                self.tableWidget_runtime.setItem(row_idx, 2, status_item)
                
                # Simpan mapping baris
                self.runtime_row_map[key] = row_idx
                row_idx += 1

    def update_runtime_table_ui(self):
        """Update isi tabel (Text & Warna) secara real-time"""
        if not hasattr(self, 'tableWidget_runtime') or not hasattr(self, 'runtime_row_map'): return
        
        for key, row_idx in self.runtime_row_map.items():
            # 1. Ambil Data Detik
            total_seconds = int(self.runtime_counters.get(key, 0.0))
            
            # 2. Format ke HH:MM:SS
            m, s = divmod(total_seconds, 60)
            h, m = divmod(m, 60)
            time_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            # 3. Cek Status Nyala/Mati
            is_on = self.system_state.get(key, False)
            status_text = "RUNNING" if is_on else "STOPPED"
            
            # 4. Update UI Widget
            # Kolom Runtime
            item_time = self.tableWidget_runtime.item(row_idx, 1)
            if item_time: item_time.setText(time_str)
            
            # Kolom Status (Dengan Warna)
            item_status = self.tableWidget_runtime.item(row_idx, 2)
            if item_status:
                item_status.setText(status_text)
                if is_on:
                    item_status.setForeground(QColor("green"))
                    item_status.setFont(item_status.font()) # Reset font bold if needed
                else:
                    item_status.setForeground(QColor("gray"))

    # --- FUNGSI PENGHUBUNG LOGIC ---
    def update_shift_worker_status(self):
        """Logic penentu: ShiftWorker jalan jika AUTO atau ada Request Manual Aktif"""
        # Cek apakah ada request manual yang sedang ON
        reqs = getattr(self, 'manual_requests', {})
        any_smart_active = any(reqs.values())
        
        # ShiftWorker jalan jika AUTO atau ada Smart Manual aktif
        should_run = (self.system_mode == "AUTO") or any_smart_active
        
        if hasattr(self, 'shift_worker'):
            self.shift_worker.set_auto_status(should_run)

    def initial_system_sync(self):
        print("[INIT] Syncing with Hardware State...")
        
        # 1. Baca Sensor Input (Logic Lama)
        self.read_hardware_sensors()
        
        # 2. LOGIC BARU: Baca Status Output (DO & AO) dari Modbus
        with QMutexLocker(self.modbus_mutex):
            try:
                for key, cfg in IO_MAP.items():
                    # Cek Digital Output (Pompa/Valve)
                    if cfg['type'] == 'DO':
                        # Baca Coil Status
                        rr = self.modbus_client.read_coils(cfg['addr'], 1, slave=cfg['slave'])
                        if not rr.isError():
                            is_on = rr.bits[0]
                            self.system_state[key] = is_on # Update memori app
                            self.ui_update_signal.emit(key, is_on) # Update tombol GUI

                    # Cek Analog Output (VFD Hz)
                    elif cfg['type'] == 'AO':
                        # Baca Holding Register
                        rr = self.modbus_client.read_holding_registers(cfg['addr'], 2, slave=cfg['slave'])
                        if not rr.isError():
                            # Decode Float
                            raw_regs = rr.registers
                            packed = struct.pack('>HH', raw_regs[0], raw_regs[1])
                            val_float = struct.unpack('>f', packed)[0]
                            
                            # Konversi 4000-20000 ke 0-50Hz
                            hz = 0.0
                            if val_float > 4000:
                                hz = ((val_float - 4000.0) / 16000.0) * 50.0
                            
                            # Update Gauge UI
                            ui_key = key.replace("AO_", "")
                            QMetaObject.invokeMethod(self, "update_vfd_gauge", 
                                                          Qt.QueuedConnection,
                                                          Q_ARG(str, ui_key),
                                                          Q_ARG(float, hz))
            except Exception as e:
                print(f"[INIT SYNC ERR] {e}")

        # 3. Restore Logic State (Auto/Smart Manual)
        QTimer.singleShot(1000, self.restore_last_state)

    def handle_soft_emergency(self, reason=""):
        print(f"[SOFT EMERGENCY] {reason}")

        self.estop_is_locked = False
        self.physical_estop_active = False

        self.system_mode = "MANUAL"
        
        # [FIX] BERSIHKAN REQUEST
        if hasattr(self, 'manual_requests'):
            for key in self.manual_requests:
                self.manual_requests[key] = False
        self.update_shift_worker_status()

        if hasattr(self, 'shift_worker'):
            self.shift_worker.set_auto_status(False)
        self.update_mode_ui()

        self.emergency_kill_all(keep_alarm=True)
        self.soft_emergency_active = True
        self.refresh_global_alarm_state()
        self.set_dashboard_grayscale(False)

    # --- [NEW] FUNGSI HANDLE ACKNOWLEDGE DARI TOAST ---
    def acknowledge_alarm_from_toast(self, alarm_name):
        """
        Dipanggil saat tombol 'Acknowledge' di toast ditekan.
        Treatment: 
        1. Matikan Buzzer
        2. Rekam ke Maintenance Log sebagai 'Done' oleh User saat ini
        3. (Opsional) Hapus dari set active alarm agar sistem tenang
        """
        print(f"[ACK] Alarm {alarm_name} acknowledged by {self.current_user}")
        
        # 1. Rekam ke Maintenance Log (Treatment Selesai)
        MaintenanceLogger.log_action(
            item=alarm_name, 
            action=f"Alarm Acknowledged via Pop-up. Problem Checked.", 
            user=self.current_user, 
            status="Done"
        )
        self.refresh_maintenance_list() # Update UI Log
        
        # 2. Matikan Buzzer & Reset Emergency State
        if alarm_name in self.critical_alarms_active:
            self.critical_alarms_active.discard(alarm_name)
            
        # Jika tidak ada alarm lain, matikan Soft Emergency & Buzzer
        if not self.critical_alarms_active and not self.active_hardware_trips:
            self.soft_emergency_active = False
            self._request_buzzer(False)
            if self.buzzer_snooze_timer.isActive():
                self.buzzer_snooze_timer.stop()
        
        # Update tampilan tombol alarm dashboard
        self.refresh_global_alarm_state()
        
        # Catat event bahwa alarm di-ack
        EventLogger.log_event("ALARM_ACKNOWLEDGED", alarm_name, f"Ack by {self.current_user}", value=0, user=self.current_user)

    def _worker_soft_kill(self):
        with QMutexLocker(self.modbus_mutex):
            for key, cfg in IO_MAP.items():
                if cfg['type'] == 'DO' and key != 'ALARM':
                    try:
                        self.modbus_client.write_coil(
                            address=cfg['addr'],
                            value=False,
                            slave=cfg['slave']
                        )
                        self.ui_update_signal.emit(key, False)
                    except:
                        pass

    def check_hardware_trips(self):
        """
        Mengecek status Trip dari DI (Digital Input) USR.
        Jika TRIP active (1): Lock Component & Alarm.
        Jika TRIP reset (0): Unlock Component & Resolve.
        """
        # 1. Ambil semua key DI trip dari cache
        trip_keys = [k for k in self.sensor_data_cache.keys() if "TRIP" in k]
        
        for key in trip_keys:
            val = self.sensor_data_cache.get(key, 0)
            is_tripped = (val == 1) 
            target_equip = key.replace("TRIP_", "")
            alarm_name = f"HARDWARE {key}" 
            
            if is_tripped:
                # --- KONDISI TRIP (ACTIVE) ---
                if alarm_name not in self.active_hardware_trips:
                    self.active_hardware_trips.add(alarm_name)
                    
                    # A. ACTION: LOCK EQUIPMENT (Langsung panggil fungsi)
                    if hasattr(self, 'handle_component_lock'):
                        self.handle_component_lock(target_equip)
                    
                    # B. NOTIFICATION: Toast & Log
                    now_str = datetime.datetime.now().strftime("%H:%M:%S")
                    alarm_data = {
                        "alarmName": alarm_name,
                        "alarmType": "Critical",
                        "message": f"Equipment Trip: {target_equip}",
                        "value": val,
                        "timestamp": now_str
                    }
                    self.handle_alarm_triggered(alarm_data)

            else:
                # --- KONDISI NORMAL (RESET) ---
                if alarm_name in self.active_hardware_trips:
                    self.active_hardware_trips.remove(alarm_name)
                    
                    # A. ACTION: UNLOCK EQUIPMENT (Langsung panggil fungsi)
                    if hasattr(self, 'handle_component_unlock'):
                        self.handle_component_unlock(target_equip)
                    
                    # B. NOTIFICATION: Resolve
                    resolve_data = {"alarmName": alarm_name, "value": val}
                    self.handle_alarm_resolved(resolve_data)

    def get_ui_button(self, key):
        mapping = {
            'TP_IN_A': getattr(self, 'btn_TP_Inlet', None) or getattr(self, 'btn_TP_Inlet_A', None) or getattr(self, 'btn_TP_IN_A', None),
            'TP_IN_B': getattr(self, 'btn_TP_Inlet_B', None) or getattr(self, 'btn_TP_IN_B', None),
            'TP_01A': getattr(self, 'btn_TP_01A', None),
            'TP_01B': getattr(self, 'btn_TP_01B', None),
            'TP_02A': getattr(self, 'btn_TP_02A', None),
            'TP_02B': getattr(self, 'btn_TP_02B', None),
            'TP_03A': getattr(self, 'btn_TP_03A', None),
            'TP_03B': getattr(self, 'btn_TP_03B', None),
            'TP_04':  getattr(self, 'btn_TP_04', None),
            'BL_01A': getattr(self, 'btn_BL_01A', None),
            'BL_01B': getattr(self, 'btn_BL_01B', None),
            'SM_01':  getattr(self, 'btn_SM_01', None),
            'SM_02':  getattr(self, 'btn_SM_02', None),
            'DP_01':  getattr(self, 'btn_DP_01', None),
            'ACT_01': getattr(self, 'btn_AV101', None), 
            'ACT_02': getattr(self, 'btn_AV102', None),
        }
        return mapping.get(key)

    def refresh_component_visual(self, key):
        btn = self.get_ui_button(key)
        if not btn: return

        is_tripped = key in self.active_hardware_trips
        is_global_estop = getattr(self, 'physical_estop_active', False) 
        is_running = self.system_state.get(key, False)
        
        is_dry_locked = False
        if key in ['TP_IN_A', 'TP_IN_B']:
            if self.sensor_data_cache.get('LS_INLET', 1) == 0:
                is_dry_locked = True

        # Bypass all safety locks on buttons in Manual Mode
        if self.system_mode == "MANUAL":
            is_tripped = False
            is_dry_locked = False

        if is_tripped:
            effect = QGraphicsColorizeEffect(btn)
            effect.setColor(QColor(255, 0, 0)) 
            effect.setStrength(1.0)
            btn.setGraphicsEffect(effect)
            btn.setStyleSheet("background-color: transparent; border: none;")
            btn.setEnabled(False)
            self.update_connected_pipes(key, False)
            return

        if is_global_estop:
            effect = QGraphicsColorizeEffect(btn)
            effect.setColor(QColor(40, 40, 40)) 
            effect.setStrength(1.0)
            btn.setGraphicsEffect(effect)
            btn.setStyleSheet("background-color: transparent; border: none;")
            btn.setEnabled(False)
            self.update_connected_pipes(key, False)
            return

        if is_dry_locked:
            effect = QGraphicsColorizeEffect(btn)
            effect.setColor(QColor(120, 120, 120)) 
            effect.setStrength(1.0)
            btn.setGraphicsEffect(effect)
            btn.setEnabled(False)
            self.update_connected_pipes(key, False)
            return

        btn.setEnabled(True)
        btn.setGraphicsEffect(None) 
        glow = QGraphicsDropShadowEffect(btn)
        glow.setXOffset(0); glow.setYOffset(0)

        if is_running:
            glow.setBlurRadius(50)
            glow.setColor(QColor(0, 255, 0, 255))
            btn.setGraphicsEffect(glow)
            self.update_connected_pipes(key, True)
        else:
            glow.setBlurRadius(40)
            glow.setColor(QColor(255, 0, 0, 255)) 
            btn.setGraphicsEffect(glow)
            self.update_connected_pipes(key, False)

    def update_connected_pipes(self, key_source, state):
        if key_source not in self.pipe_mapping: return
        affected_pipes = self.pipe_mapping[key_source]
        final_state = state
        if not final_state:
            for pipe_name in affected_pipes:
                for owner_key, pipes_owned in self.pipe_mapping.items():
                    if pipe_name in pipes_owned and owner_key != key_source:
                         if self.system_state.get(owner_key, False):
                             final_state = True
        for pipe_name in affected_pipes:
            widget = getattr(self, pipe_name, None)
            if widget: self.force_pipe_color(widget, final_state)

    def init_pipe_manager(self):
        self.pipe_original_styles = {}
        for key, pipe_names in self.pipe_mapping.items():
            for pipe_name in pipe_names:
                widget = getattr(self, pipe_name, None)
                if widget:
                    w_name = widget.objectName()
                    if w_name not in self.pipe_original_styles:
                        self.pipe_original_styles[w_name] = widget.styleSheet()

    def force_pipe_color(self, widget, is_active):
        if not widget: return
        w_name = widget.objectName()
        is_image = isinstance(widget, QtWidgets.QLabel) and widget.pixmap() and not widget.pixmap().isNull()

        if is_active:
            widget.setGraphicsEffect(None) 
            if is_image:
                widget.setStyleSheet("background-color: transparent; border: none;")
            else:
                widget.setStyleSheet(self.pipe_original_styles.get(w_name, ""))
        else:
            if is_image:
                effect = QGraphicsColorizeEffect(widget)
                effect.setColor(QColor(50, 70, 90)) 
                effect.setStrength(0.4) 
                widget.setGraphicsEffect(effect)
            else:
                widget.setGraphicsEffect(None)
                widget.setStyleSheet(self.pipe_original_styles.get(w_name, ""))

    @pyqtSlot(str, bool)
    def process_ui_update(self, key, state):
        self.system_state[key] = state
        self.refresh_component_visual(key)

    @pyqtSlot()
    def handle_estop_active(self):
        if getattr(self, 'estop_is_locked', False): return 
        
        print("!!! ESTOP TRIGGERED: IMMEDIATE KILL !!!")
        
        # 1. Kunci System Variable SEGERA
        self.estop_is_locked = True 
        self.physical_estop_active = True 
        self.system_mode = "MANUAL" # Force Manual
        
        # 2. Matikan Worker Auto (Supaya tidak spam command lagi)
        if hasattr(self, 'shift_worker'): self.shift_worker.set_auto_status(False)
        # Note: AutoPilotWorker loop akan mengecek 'estop_is_locked' di awal loop dan berhenti.
        
        # 3. GUI Feedback Instan (Sebelum proses hardware)
        self.update_mode_ui()
        for btn, _, _, _ in self.buttons_config:
            if btn: btn.setEnabled(False) 
        if hasattr(self, 'btn_auto'): self.btn_auto.setEnabled(False)
        if hasattr(self, 'btn_manual'): self.btn_manual.setEnabled(False)
        self.set_dashboard_grayscale(True)
        QApplication.processEvents() # Paksa refresh UI agar user lihat perubahan
        
        # 4. HARDWARE KILL (Prioritas Tinggi)
        self.emergency_kill_all()

    @pyqtSlot()
    def handle_estop_cleared(self):
        if not getattr(self, 'estop_is_locked', False): return
        
        # [PERBAIKAN] Reset kedua variabel
        self.estop_is_locked = False
        self.physical_estop_active = False

        print(">>> HANDLING ESTOP: UNLOCKING SYSTEM <<<")
        
        # Enable kembali tombol
        for btn, _, _, _ in self.buttons_config:
            if btn: btn.setEnabled(True)
        if hasattr(self, 'btn_auto'): self.btn_auto.setEnabled(True)
        if hasattr(self, 'btn_manual'): self.btn_manual.setEnabled(True)
        
        # Kembalikan warna Dashboard
        self.set_dashboard_grayscale(False)
        
        # Refresh visual akhir agar kembali hijau/merah sesuai status mesin
        for key in IO_MAP.keys():
            self.refresh_component_visual(key)

    def handle_emergency_stop(self):
        print("!!! EMERGENCY STOP TRIGGERED (GUI) !!!")
        
        # 1. Reset Lock Fisik (karena ini Soft Stop)
        self.estop_is_locked = False
        self.physical_estop_active = False
        
        # 2. Set Mode Manual & Soft Emergency
        self.system_mode = "MANUAL"
        self.soft_emergency_active = True

        # [FIX] BERSIHKAN REQUEST MANUAL HANTU
        if hasattr(self, 'manual_requests'):
            for key in self.manual_requests:
                self.manual_requests[key] = False
        self.update_shift_worker_status()

        # 3. Stop Shift Worker
        if hasattr(self, 'shift_worker'): 
            self.shift_worker.set_auto_status(False)
            
        self.update_mode_ui()
        
        # 4. Matikan mesin (Keep Alarm ON)
        self.emergency_kill_all(keep_alarm=True)
        
        # 5. Nyalakan Buzzer & Refresh UI
        self.refresh_global_alarm_state()
        self.set_dashboard_grayscale(False)

    @pyqtSlot(str)
    def handle_component_lock(self, key):
        if key not in self.active_hardware_trips:
            self.active_hardware_trips.add(key)
            if self.buzzer_snooze_timer.isActive(): self.buzzer_snooze_timer.stop()
        self.direct_write_hardware(key, False) 
        self.refresh_global_alarm_state()
        self.refresh_component_visual(key)

    @pyqtSlot(str)
    def handle_component_unlock(self, key):
        # if key in ['SM_01', 'SM_02']:
        #     return
        
        if key in self.active_hardware_trips:
            self.active_hardware_trips.discard(key)
        
        # === PERUBAHAN DI SINI ===
        # Buzzer hanya boleh mati jika:
        # - tidak ada hardware trip
        # - tidak ada critical alarm
        # - TIDAK dalam kondisi soft emergency
        if (
            len(self.active_hardware_trips) == 0 and
            len(self.critical_alarms_active) == 0 and
            not getattr(self, 'soft_emergency_active', False)
        ):
            print(f"[SYSTEM] All Trips/Alarms Cleared. Killing Buzzer.")
            
            # Paksa matikan buzzer
            self.direct_write_hardware('ALARM', False)
            
            # Reset toggle manual agar buzzer tidak nyala sendiri
            self.manual_alarm_active = False 
            
            # Stop timer snooze jika ada
            if self.buzzer_snooze_timer.isActive():
                self.buzzer_snooze_timer.stop()
        else:
            # Masih ada emergency (critical ATAU soft) → buzzer tetap aktif
            self.refresh_global_alarm_state()
            
        self.refresh_component_visual(key)

    # Hapus dekorator @pyqtSlot agar fleksibel menerima bool atau str
    def handle_critical_failure(self, is_fail):
        if is_fail:
            # Jika is_fail berupa string pesan error, tampilkan. Jika True, tampilkan default.
            reason = is_fail if isinstance(is_fail, str) else "Critical failure detected"
            self.handle_soft_emergency(reason)

    def is_tripped(self, component_key):
        """Mengembalikan True jika komponen sedang dalam kondisi TRIP Hardware"""
        return component_key in self.active_hardware_trips

    def read_hardware_sensors(self):
        """[RESTORED FROM MAIN_APP.PY] Membaca sensor dengan proteksi tryLock."""
        new_data = {}
        if not self.modbus_mutex.tryLock(100):
            return self.sensor_data_cache 
        
        try:
            for key, cfg in IO_MAP.items():
                if key == 'EMC': continue 
                if cfg['type'] == 'DI':
                    val = self.io_controller.digitalInput(cfg['addr'], cfg['slave'])
                    if val is not None: new_data[key] = val

            analogs = ['LT_101', 'LT_102', 'LT_103', 'FT_101', 'FT_102', 'FT_103', 'PT_101', 'DO_101']
            for tag in analogs:
                val = self._safe_read_ai(tag)
                new_data[tag] = val
            
            self.sensor_data_cache.update(new_data)
        except Exception as e:
            pass
        finally:
            self.modbus_mutex.unlock()
        return self.sensor_data_cache

    def _safe_read_ai(self, key):
        cfg = IO_MAP.get(key)
        if not cfg: return 0.0
        try:
            val = self.io_controller.analogInput(cfg['addr'], cfg['slave'], use_holding=False)
            if val is not None: return val 
        except Exception: pass
        # try:
        #     val = self.io_controller.analogInput(cfg['addr'], cfg['slave'], use_holding=True)
        #     if val is not None: return val
        # except Exception: pass
        return 0.0

    @pyqtSlot(dict)
    def update_sensor_cache(self, new_data):
        """
        Slot to receive data from background thread.
        This updates the cache safely without freezing UI.
        """
        self.sensor_data_cache.update(new_data)
        self.check_hardware_trips()

        # Trigger UI refresh for digital buttons immediately if needed
        # (Optional: you can also wait for the 1s timer)
        for key, val in new_data.items():
            if key in IO_MAP and IO_MAP[key]['type'] == 'DI':
                # Only update simple On/Off status if changed
                pass 

    # --- HELPER SCALING 4-20mA (BARU) ---
    def get_scaling_limit_hh(self, sensor_name_csv):
        """Membaca nilai Config HH dari CSV untuk batas atas scaling"""
        default_hh = 10.4 # Default flow
        if "PT" in sensor_name_csv: default_hh = 5.0 # Default pressure
        
        csv_path = os.path.join(os.path.dirname(__file__), "data_alarm_settings.csv")
        if os.path.exists(csv_path):
            try:
                with open(csv_path, mode='r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Cari yang instrumentName sama dan alarmName mengandung HH
                        if row.get('instrumentName') == sensor_name_csv and 'HH' in row.get('alarmName'):
                            return float(row.get('alarmTripValue', default_hh))
            except: pass
        return default_hh

    def scale_4_20ma(self, raw_val, out_min, out_max):
        """
        Konversi Linear 4-20mA ke Engineering Unit.
        """
        in_min, in_max = 4.0, 20.0

        if raw_val > 21.0:
            return 0.0
        
        # Deadband Bawah: Jika < 3.8mA (Putus/Mati), anggap 4.0 (Nol)
        # Ini PENTING supaya saat sensor mati (0 mA), nilai tidak menjadi Minus.
        if raw_val < 3.8: raw_val = 4.0 

        # Rumus: Y = ((X - Xmin) / (Xmax - Xmin)) * (Ymax - Ymin) + Ymin
        return ((raw_val - in_min) / (in_max - in_min)) * (out_max - out_min) + out_min

    def process_sensor_data(self):
        """
        [FINAL UPDATE] Totalizer Persistent & CSV Logging
        """
        # 1. Init Totalizer (Lazy Load)
        if not hasattr(self, 'totalizers'): self.load_totalizers()
        
        # [FIX] RESET HARIAN (Check Tanggal)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        if not hasattr(self, 'last_totalizer_date'):
            self.last_totalizer_date = today_str 
            
        if self.last_totalizer_date != today_str:
            print(f"[SYSTEM] New Day ({today_str}). Resetting Totalizers.")
            TotalizerLogger.log_daily(
                self.last_totalizer_date, 
                self.totalizers.get('FT_101', 0.0),
                self.totalizers.get('FT_102', 0.0),
                self.totalizers.get('FT_103', 0.0)
            )
            
            self.totalizers = {'FT_101': 0.0, 'FT_102': 0.0, 'FT_103': 0.0}
            self.last_totalizer_date = today_str
            self.save_totalizers()
            self.load_totalizer_history_to_table()

        # 2. Ambil Raw Data 
        sensors = self.sensor_data_cache 
        current_time = time.time()
        last_time = getattr(self, 'last_totalizer_time', current_time - 1.0)
        dt = current_time - last_time
        if dt > 5.0 or dt < 0: dt = 1.0 
        self.last_totalizer_time = current_time

        has_change = False
        
        for key, cfg in IO_MAP.items():
            if cfg['type'] == 'DO':
                # Cek apakah mesin nyala (dari feedback system_state)
                is_on = self.system_state.get(key, False)
                
                if is_on:
                    # Tambah durasi
                    current_val = self.runtime_counters.get(key, 0.0)
                    self.runtime_counters[key] = current_val + dt
                    has_change = True
        
        # Auto-Save JSON tiap 10 detik
        if (current_time - getattr(self, 'last_runtime_save', 0)) > 10.0 and has_change:
            self.save_runtimes()
            self.last_runtime_save = current_time 
        self.update_runtime_table_ui()

        # 4. Extract Raw Values
        raw_ma_lt101 = sensors.get('LT_101', 1.85)
        raw_ma_do101 = sensors.get('DO_101', 3.5)
        raw_ma_ft101 = sensors.get('FT_101', 4.0)
        raw_ma_ft102 = sensors.get('FT_102', 4.0)
        raw_ma_ft103 = sensors.get('FT_103', 4.0)
        raw_ma_pt101 = sensors.get('PT_101', 4.0)

        vfd_a_volt = sensors.get('VFD_A_VOLT', 0.0)
        vfd_a_amp  = sensors.get('VFD_A_AMP', 0.0)
        vfd_b_volt = sensors.get('VFD_B_VOLT', 0.0)
        vfd_b_amp  = sensors.get('VFD_B_AMP', 0.0)

        # 5. Config Max Scale & Linear/Direct Conversion
        max_ft101 = 25.0
        max_ft102 = 10.0
        max_ft103 = 15.0

        # Sensor Scaling (Supports both direct simulation EU and 4-20mA hardware module)
        if 3.8 < raw_ma_lt101 <= 21.0:
            val_lt101 = self.scale_4_20ma(raw_ma_lt101, 0.0, 2.5)
        else:
            val_lt101 = float(raw_ma_lt101)

        if 3.8 < raw_ma_do101 <= 21.0:
            val_do101 = self.scale_4_20ma(raw_ma_do101, 0.0, 20.0)
        else:
            val_do101 = float(raw_ma_do101)

        if 3.8 < raw_ma_ft101 <= 21.0:
            val_flow_inlet = self.scale_4_20ma(raw_ma_ft101, 0.0, max_ft101)
        else:
            val_flow_inlet = float(raw_ma_ft101)

        if 3.8 < raw_ma_ft102 <= 21.0:
            val_flow_mbr = self.scale_4_20ma(raw_ma_ft102, 0.0, max_ft102)
        else:
            val_flow_mbr = float(raw_ma_ft102)

        if 3.8 < raw_ma_ft103 <= 21.0:
            val_flow_bw = self.scale_4_20ma(raw_ma_ft103, 0.0, max_ft103)
        else:
            val_flow_bw = float(raw_ma_ft103)

        if 3.8 < raw_ma_pt101 <= 21.0:
            val_pressure = self.scale_4_20ma(raw_ma_pt101, -1.0, 1.0)
        else:
            val_pressure = float(raw_ma_pt101)

        val_eq = val_lt101
        val_ae = 180.0
        val_mbr = val_lt101

        # 7. Simpan Nilai Scaled ke Cache
        self.sensor_data_cache['SCALED_LT_101'] = val_lt101
        self.sensor_data_cache['SCALED_DO_101'] = val_do101
        self.sensor_data_cache['SCALED_FT_101'] = val_flow_inlet
        self.sensor_data_cache['SCALED_FT_102'] = val_flow_mbr
        self.sensor_data_cache['SCALED_FT_103'] = val_flow_bw
        self.sensor_data_cache['SCALED_PT_101'] = val_pressure
        self.sensor_data_cache['SCALED_LT_102'] = 180.0
        self.sensor_data_cache['SCALED_LT_103'] = val_lt101

        # 8. Hitung Totalizer (Flow Accumulation)
        if val_flow_inlet > 0.05: self.totalizers['FT_101'] += val_flow_inlet * (dt / 3600.0)
        if val_flow_mbr > 0.05:   self.totalizers['FT_102'] += val_flow_mbr   * (dt / 3600.0)
        if val_flow_bw > 0.05:    self.totalizers['FT_103'] += val_flow_bw    * (dt / 3600.0)

        # Auto-Save Totalizer JSON setiap 10 detik
        if not hasattr(self, 'last_json_save'): self.last_json_save = time.time()
        if (current_time - self.last_json_save) > 10.0:
            self.save_totalizers()
            self.last_json_save = current_time

        # 9. Update UI Dashboard (Teks Flow Rate, Pressure, Level, DO)
        status_ft101 = sensors.get('STATUS_FT_101', 'OK')
        status_ft102 = sensors.get('STATUS_FT_102', 'OK')
        status_ft103 = sensors.get('STATUS_FT_103', 'OK')
        status_pt101 = sensors.get('STATUS_PT_101', 'OK')
        status_lt101 = sensors.get('STATUS_LT_101', 'OK')
        status_do101 = sensors.get('STATUS_DO_101', 'OK')

        flow_style_ok = "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 11px; border: 1px solid #34495e; border-radius: 4px;"
        flow_style_err = "background-color: #2c3e50; color: red; font-weight: bold; font-size: 9px; border: 1px solid red; border-radius: 4px;"

        if hasattr(self, 'flow_FT101'):
            self.flow_FT101.setText(f"{val_flow_inlet:.2f} m³/h" if status_ft101 == 'OK' else status_ft101)
            self.flow_FT101.setStyleSheet(flow_style_ok if status_ft101 == 'OK' else flow_style_err)

        if hasattr(self, 'flow_FT102'):
            self.flow_FT102.setText(f"{val_flow_mbr:.2f} m³/h" if status_ft102 == 'OK' else status_ft102)
            self.flow_FT102.setStyleSheet(flow_style_ok if status_ft102 == 'OK' else flow_style_err)

        if hasattr(self, 'flow_FT103'):
            self.flow_FT103.setText(f"{val_flow_bw:.2f} m³/h" if status_ft103 == 'OK' else status_ft103)
            self.flow_FT103.setStyleSheet(flow_style_ok if status_ft103 == 'OK' else flow_style_err)

        if hasattr(self, 'flow_PT101'):
            self.flow_PT101.setText(f"{val_pressure:.2f} bar" if status_pt101 == 'OK' else status_pt101)
            self.flow_PT101.setStyleSheet(flow_style_ok if status_pt101 == 'OK' else flow_style_err)

        if hasattr(self, 'flow_LT101'):
            self.flow_LT101.setText(f"{val_lt101:.2f} m" if status_lt101 == 'OK' else status_lt101)
            self.flow_LT101.setStyleSheet(flow_style_ok if status_lt101 == 'OK' else flow_style_err)

        if hasattr(self, 'flow_DO101'):
            self.flow_DO101.setText(f"{val_do101:.2f} mg/L" if status_do101 == 'OK' else status_do101)
            self.flow_DO101.setStyleSheet(flow_style_ok if status_do101 == 'OK' else flow_style_err)

        # Update Level Switches PFD Badges
        ls101_val = sensors.get('LS_101', sensors.get('LS_INLET', 1))
        ls102_val = sensors.get('LS_102', 1)
        ls103_val = sensors.get('LS_103', sensors.get('LS_MBR_BW', 1))

        if hasattr(self, 'txt_LS_101'):
            self.txt_LS_101.setText("HIGH" if ls101_val == 1 else "LOW")
            self.txt_LS_101.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 9px;" if ls101_val == 1 else "color: #e67e22; font-weight: bold; font-size: 9px;")

        if hasattr(self, 'txt_LS_102'):
            self.txt_LS_102.setText("HIGH" if ls102_val == 1 else "LOW")
            self.txt_LS_102.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 9px;" if ls102_val == 1 else "color: #e67e22; font-weight: bold; font-size: 9px;")

        if hasattr(self, 'txt_LS_103'):
            self.txt_LS_103.setText("HIGH" if ls103_val == 1 else "LOW")
            self.txt_LS_103.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 9px;" if ls103_val == 1 else "color: #e67e22; font-weight: bold; font-size: 9px;")

        # Update PFD Schematic Instrument Badges
        if hasattr(self, 'label_77'):
            state_str = "HIGH" if ls101_val == 1 else "LOW"
            color = "#00aa00" if ls101_val == 1 else "#d97706"
            self.label_77.setText(f"LS-101\n{state_str}")
            self.label_77.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10px; background-color: rgba(255,255,255,200); border: 1px solid #aaa; border-radius: 3px;")

        if hasattr(self, 'label_83'):
            state_str = "NORMAL" if ls102_val == 1 else "LOW"
            color = "#00aa00" if ls102_val == 1 else "#d97706"
            self.label_83.setText(f"LS-102\n{state_str}")
            self.label_83.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10px; background-color: rgba(255,255,255,200); border: 1px solid #aaa; border-radius: 3px;")

        if hasattr(self, 'label_84'):
            self.label_84.setText(f"DO-101\n{val_do101:.2f} mg/L")
            self.label_84.setStyleSheet("color: #0066cc; font-weight: bold; font-size: 10px; background-color: rgba(255,255,255,200); border: 1px solid #aaa; border-radius: 3px;")

        if hasattr(self, 'label_85'):
            self.label_85.setText(f"LT-101\n{val_lt101:.2f} m")
            self.label_85.setStyleSheet("color: #0066cc; font-weight: bold; font-size: 10px; background-color: rgba(255,255,255,200); border: 1px solid #aaa; border-radius: 3px;")

        if hasattr(self, 'label_76'):
            state_str = "HIGH" if ls103_val == 1 else "LOW"
            color = "#00aa00" if ls103_val == 1 else "#d97706"
            self.label_76.setText(f"LS-103\n{state_str}")
            self.label_76.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10px; background-color: rgba(255,255,255,200); border: 1px solid #aaa; border-radius: 3px;")

        # Update Animasi Permukaan Air Tangki
        self.animate_tank('label_Inletwater_2', 1 if ls101_val == 1 else 0)
        self.animate_tank('label_EQ1water_2', 1 if ls102_val == 1 else 0)
        self.animate_tank('label_AE1water2', 180.0)
        self.animate_tank('label_mbrwater2', val_lt101)
        self.animate_tank('label_tankwater2', 1 if ls103_val == 1 else 0)

        # 10. Update Instrument Widgets (Chart & Indikator Angka)
        current_values = {
            'LT_101': val_lt101, 'DO_101': val_do101,
            'FT_101': val_flow_inlet, 'FT_102': val_flow_mbr, 'FT_103': val_flow_bw,
            'PT_101': val_pressure
        }
        
        if hasattr(self, 'instrument_widgets'):
            for key, val in current_values.items():
                if key in self.instrument_widgets:
                    widget = self.instrument_widgets[key]
                    status_key = f"STATUS_{key}"
                    status = sensors.get(status_key, "OK")
                    if "FT" in key:
                        current_total = self.totalizers.get(key, 0.0)
                        widget.update_values(val, total=current_total, status=status)
                    else:
                        widget.update_values(val, status=status)

        # 11. Logic Visual Tombol Inlet (Dry Protection)
        self._update_inlet_buttons_visual(ls101_val)

        # --- [LOGGING DATA KE CSV] ---
        # Data yang akan disimpan ke CSV harian
        processed_data = [
            round(val_eq, 2), 
            round(val_ae, 2), 
            round(val_mbr, 2),
            round(val_flow_inlet, 2), 
            round(val_flow_mbr, 2), 
            round(val_flow_bw, 2),
            round(val_pressure, 3),
            round(vfd_a_volt, 1),
            round(vfd_a_amp, 2),
            round(vfd_b_volt, 1),
            round(vfd_b_amp, 2),
            round(self.totalizers['FT_101'], 2),
            round(self.totalizers['FT_102'], 2),
            round(self.totalizers['FT_103'], 2)
        ]
        
        # Simpan ke CSV
        self.sensor_logger.log_data(processed_data)
        
        ui_data = [
            round(val_eq, 2), 
            round(val_ae, 2), 
            round(val_mbr, 2),
            round(val_flow_inlet, 2), 
            round(val_flow_mbr, 2), 
            round(val_flow_bw, 2),
            round(val_pressure, 3)
        ]

        # Update Tabel UI (Baris paling atas)
        if hasattr(self, 'tableWidget'):
            self.tableWidget.insertRow(0)
            self.tableWidget.setItem(0, 0, QTableWidgetItem(datetime.datetime.now().strftime("%H:%M:%S")))
            for i, val in enumerate(ui_data): 
                self.tableWidget.setItem(0, i+1, QTableWidgetItem(str(val)))
            if self.tableWidget.rowCount() > 200: self.tableWidget.removeRow(200)

        # 12. Update Animasi Tangki
        self.animate_tank('label_EQ1water_2', val_eq)   
        self.animate_tank('label_AE1water2', val_ae)    
        self.animate_tank('label_mbrwater2', val_mbr)    
        self.animate_tank('label_AE2water2', val_mbr)    
        self.animate_tank('label_Inletwater_2', sensors.get('LS_INLET', 0)) 
        self.animate_tank('label_tankwater2', sensors.get('LS_MBR_BW', 0))

        # 13. Update Alarm Monitor
        if hasattr(self, 'alarm_monitor'):
            # Data alarm monitor juga bisa diberi totalizer jika perlu, tapi biasanya rate saja cukup
            self.alarm_monitor.update_data(current_values)

    def _update_inlet_buttons_visual(self, ls_val):
        """Helper untuk visual tombol inlet (disable jika kering)"""
        if getattr(self, 'physical_estop_active', False): return
        
        inlet_btns = []
        if hasattr(self, 'btn_TP_Inlet_A'): inlet_btns.append(('TP_IN_A', self.btn_TP_Inlet_A))
        elif hasattr(self, 'btn_TP_Inlet'): inlet_btns.append(('TP_IN_A', self.btn_TP_Inlet))
        if hasattr(self, 'btn_TP_Inlet_B'): inlet_btns.append(('TP_IN_B', self.btn_TP_Inlet_B))

        # In MANUAL mode, bypass dry-run disable visual
        if self.system_mode == "MANUAL":
            for key, btn in inlet_btns:
                if btn:
                    btn.setEnabled(True)
                    btn.setGraphicsEffect(None)
                    btn.setToolTip("")
                    self.refresh_component_visual(key)
            return

        if ls_val == 0:
            for _, btn in inlet_btns:
                if btn and btn.isEnabled():
                    effect = QGraphicsColorizeEffect(btn)
                    effect.setColor(Qt.gray)
                    btn.setGraphicsEffect(effect)
                    btn.setEnabled(False) 
                    btn.setToolTip("DISABLED: LS INLET LOW / DRY")
                    btn.setStyleSheet("QPushButton { background-color: transparent; border: none; }")
        else:
            for key, btn in inlet_btns:
                if btn and not btn.isEnabled() and (key not in self.active_hardware_trips):
                    btn.setEnabled(True)
                    btn.setGraphicsEffect(None)
                    btn.setToolTip("")
                    state_last = self.system_state.get(key, False)
                    self.refresh_component_visual(key)

    def animate_tank(self, widget_name, current_value):
        # 1. Validasi Widget
        if not hasattr(self, widget_name): return
        widget = getattr(self, widget_name)
        
        # 2. Ambil Config & Geometri Awal
        sens_cfg = self.sensor_config.get(widget_name)
        geo_data = self.tank_geometry.get(widget_name)
        if not sens_cfg or not geo_data: return

        # Handle kasus khusus AE2 (meminjam config MBR)
        if widget_name == 'label_AE2water2':
            mbr_cfg = self.sensor_config.get('label_mbrwater2')
            if mbr_cfg: sens_cfg['max'] = mbr_cfg['max']

        # 3. Hitung Target Tinggi (Masking Putih)
        max_h = geo_data['max_h']
        target_height = max_h # Default: Menutup penuh (Kosong)

        if sens_cfg['type'] == 'discrete': 
            if current_value == 1:
                target_height = 0
            else:
                target_height = max_h
        else: 
            if current_value > sens_cfg['max']: sens_cfg['max'] = float(current_value) 
            ratio_kosong = 1.0 - (current_value / (sens_cfg['max'] or 1.0))
            target_height = int(ratio_kosong * max_h)

        # 4. EKSEKUSI ANIMASI (Agar bergerak halus)
        # Cek apakah animasi sudah ada, jika tidak buat baru
        if not hasattr(widget, "tank_anim"):
            widget.tank_anim = QPropertyAnimation(widget, b"geometry")
            widget.tank_anim.setDuration(1000) # Durasi gerak 1 detik (1000 ms)
            widget.tank_anim.setEasingCurve(QEasingCurve.InOutQuad) # Gerakan halus (Pelan-Cepat-Pelan)

        # Stop animasi lama jika sedang berjalan (supaya tidak tabrakan)
        if widget.tank_anim.state() == QPropertyAnimation.Running:
            widget.tank_anim.stop()

        # Set Posisi Awal (Posisi saat ini)
        current_geo = widget.geometry()
        widget.tank_anim.setStartValue(current_geo)
        # Set Posisi Akhir
        # X, Y, dan Width TETAP. Hanya Height yang berubah.
        new_geo = QRect(geo_data['x'], geo_data['top_y'], geo_data['width'], target_height)
        widget.tank_anim.setEndValue(new_geo)
        # Mulai Animasi
        widget.tank_anim.start()

    def emergency_kill_all(self, keep_alarm=False):
        self.run_in_background(self._worker_kill_safe, keep_alarm)

    def _worker_kill_safe(self, keep_alarm=False):
        """
        Mematikan semua DO (kecuali Alarm jika keep_alarm=True)
        DAN mereset semua AO (VFD) ke 0 Hz (4000.0 raw).
        """
        import struct 
        from PyQt5.QtCore import QMetaObject, Q_ARG, Qt 

        with QMutexLocker(self.modbus_mutex):
            # --- 1. MATIKAN DIGITAL OUTPUT (DO) ---
            for key, cfg in IO_MAP.items():
                if cfg['type'] == 'DO':
                    # Skip ALARM jika keep_alarm=True (agar buzzer tetap bunyi)
                    if keep_alarm and key == 'ALARM':
                        continue
                        
                    try:
                        self.modbus_client.write_coil(cfg['addr'], False, cfg['slave'])
                        self.ui_update_signal.emit(key, False)
                    except Exception as e:
                        print(f"[KILL] Gagal matikan DO {key}: {e}")

            # --- 2. RESET ANALOG OUTPUT (AO/VFD) KE 0 HZ ---
            # Kita set ke 4000.0 (4mA = 0Hz)
            target_val = 4000.0 
            
            # Persiapkan payload Float 32-bit
            try:
                packed_bytes = struct.pack('>f', target_val)
                regs = struct.unpack('>HH', packed_bytes)
                payload = list(regs) # [HighWord, LowWord]
            except:
                payload = [0, 0]

            # Cari semua item AO dan tulis 0Hz
            for key, cfg in IO_MAP.items():
                if cfg['type'] == 'AO':
                    try:
                        self.modbus_client.write_registers(
                            address=cfg['addr'], 
                            values=payload, 
                            slave=cfg['slave']
                        )
                        
                        # Reset Jarum Gauge VFD di UI ke 0
                        # Nama key AO di IO_MAP biasanya AO_TP_03A, tapi Gauge ID biasanya TP_03A
                        # Kita coba bersihkan prefix 'AO_' jika ada untuk update UI
                        ui_key = key.replace("AO_", "")
                        QMetaObject.invokeMethod(self, "update_vfd_gauge", 
                                                      Qt.QueuedConnection,
                                                      Q_ARG(str, ui_key),
                                                      Q_ARG(float, 0.0))
                                                      
                        print(f"[KILL] VFD {key} diset ke 0Hz")
                    except Exception as e:
                        print(f"[KILL] Gagal reset AO {key}: {e}")
            
            # [TAMBAHAN] Reset VFD Blower (Slave 2 & 3)
            # Karena VFD Blower tidak masuk loop IO_MAP 'AO', kita reset manual
            try:
                with QMutexLocker(self.mutex_bl):
                    # Reset Blower A (Slave 2)
                    self.client_bl.write_register(0x1000, 0, slave=2)
                    # Reset Blower B (Slave 3)
                    self.client_bl.write_register(0x1000, 0, slave=3)
                    print("[KILL] Blower VFDs Reset to 0")
            except: pass

    def _kill_all_outputs(self):
        for name, cfg in IO_MAP.items():
            if cfg['type'] == 'DO':
                self.io_controller.digitalOutput(cfg['addr'], 0, cfg['slave'])
                self.ui_update_signal.emit(name, False)
    
    def _calculate_vfd_data(self, freq, state, device_type="DEFAULT"):
        """
        Sub-fungsi khusus untuk menghitung nilai register VFD.
        Memudahkan penggantian rumus scaling tanpa merusak logic koneksi.
        """
        if not state:
            return 0  # Jika mati, kirim 0

        # Batasi frekuensi 0-50Hz (Safety)
        safe_freq = max(0.0, min(50.0, float(freq)))

        # --- TIPE 1: USR I/O (4-20mA Analog Output) ---
        if device_type == "USR_AO":
            return 4000.0 + (safe_freq / 50.0) * 16000.0

        # --- TIPE 2: INVERTER MODBUS MURNI (Blower Baru) ---
        elif device_type == "MODBUS_BL":
            MAX_HZ_CONFIG = 50.0 # Pastikan parameter F0.04 di inverter diset 50.00Hz
            percentage = safe_freq / MAX_HZ_CONFIG
            raw_value = int(percentage * 10000)
            return raw_value
        
        return 0

    def direct_write_hardware(self, key, state, freq=0):
        import struct 
        from PyQt5.QtCore import QMetaObject, Q_ARG, Qt

        # 1. Safety Check (ESTOP)
        if getattr(self, 'estop_is_locked', False) and state == True and key != 'ALARM':
            return

        if key not in IO_MAP: return
        cfg = IO_MAP[key]

        if key in self.vfd_frequencies:
            self.vfd_frequencies[key] = float(freq) if state else 0.0
        
        # --- BLOK 1: DIGITAL OUTPUT UTAMA (USR) ---
        # Semua alat (termasuk Blower) tetap butuh sinyal On/Off ke USR
        try:
            with QMutexLocker(self.modbus_mutex):
                if cfg['type'] == 'DO':
                    self.modbus_client.write_coil(cfg['addr'], state, slave=cfg['slave'])
                    self.ui_update_signal.emit(key, state)
        except Exception as e:
            print(f"[USR DO ERROR] {key}: {e}")

        # --- BLOK 2: VFD VIA USR (Logic Lama / Existing) ---
        # Cek apakah device ini punya pasangan Analog Output di IO_MAP (misal AO_TP_03A)
        ao_key = f"AO_{key}"
        if ao_key in IO_MAP:
            try:
                ao_cfg = IO_MAP[ao_key]
                with QMutexLocker(self.modbus_mutex):
                    # Panggil Sub-Fungsi Scaling Tipe USR
                    target_val = self._calculate_vfd_data(freq, state, device_type="USR_AO")
                    
                    # Packing Float (Standar Modbus USR)
                    packed = struct.pack('>f', target_val)
                    payload = list(struct.unpack('>HH', packed))
                    
                    self.modbus_client.write_registers(ao_cfg['addr'], payload, slave=ao_cfg['slave'])
                    
                    # Update UI Gauge
                    final_hz = freq if state else 0.0
                    QMetaObject.invokeMethod(self, "update_vfd_gauge", Qt.QueuedConnection, Q_ARG(str, key), Q_ARG(float, final_hz))
            except Exception as e:
                print(f"[USR AO ERROR] {key}: {e}")

        # --- BLOK 3: VFD INDEPENDEN (Blower Baru) ---
        # Cek apakah device ini punya konfigurasi port khusus di IO_MAP
        if 'vfd_port' in cfg:
            target_client = None
            target_mutex = None
            
            # [UBAH] Ambil Slave ID dari Config
            target_slave = cfg.get('vfd_slave', 1) 

            if cfg['vfd_port'] == 'BL': # Port Gabungan
                target_client = self.client_bl
                target_mutex = self.mutex_bl
            
            if target_client:
                try:
                    with QMutexLocker(target_mutex):
                        target_val = self._calculate_vfd_data(freq, state, device_type="MODBUS_BL")
                        
                        # [UBAH] Gunakan parameter slave=target_slave
                        rr = target_client.write_register(cfg['vfd_addr'], int(target_val), slave=target_slave)
                        
                        if rr.isError(): raise Exception(f"Modbus Error: {rr}")
                            
                        print(f"[BLOWER VFD] {key} (Slave {target_slave}): {freq}Hz -> Val {target_val}")
                        
                        # Update UI Gauge
                        final_hz = freq if state else 0.0
                        QMetaObject.invokeMethod(self, "update_vfd_gauge", Qt.QueuedConnection, Q_ARG(str, key), Q_ARG(float, final_hz))

                except Exception as e:
                    print(f"[BLOWER VFD ERROR] {key}: {e}")
                    # Safety Kill Relay jika VFD Gagal (Tetap Sama)
                    if state == True:
                        try:
                            with QMutexLocker(self.modbus_mutex):
                                self.modbus_client.write_coil(cfg['addr'], False, slave=cfg['slave'])
                                self.ui_update_signal.emit(key, False)
                        except: pass

    def _worker_write_hardware(self, reg_key, state, freq=0):
        self.direct_write_hardware(reg_key, state, freq)
        
    @pyqtSlot(str, float)
    def update_vfd_gauge(self, key, hz_value):
        if hasattr(self, 'instrument_widgets') and key in self.instrument_widgets:
            if hasattr(self.instrument_widgets[key], 'set_value'):
                self.instrument_widgets[key].set_value(float(hz_value))

    def set_auto_mode(self):
        if getattr(self, 'physical_estop_active', False):
             QMessageBox.warning(self, "LOCKED", "Sistem terkunci (Physical E-Stop/Trip).")
             return
        self.system_mode = "AUTO"
        
        # Bersihkan cache status auto agar semua output hardware disinkronkan kembali
        if hasattr(self, 'auto_worker'):
            self.auto_worker.last_sent_states = {}
            
        #if hasattr(self, 'shift_worker'): self.shift_worker.set_auto_status(True)
        self.update_shift_worker_status()
        self.update_mode_ui()

    def set_manual_mode(self):
        print("[MODE] Switching to MANUAL - OVERRIDE AUTO")
        self.system_mode = "MANUAL"
        
        # Stop Shift Worker Logic
        if hasattr(self, 'shift_worker'): 
            for key in self.manual_requests:
                self.manual_requests[key] = False
           # self.shift_worker.set_auto_status(False)

        self.update_shift_worker_status() 
        self.update_mode_ui()
        
        # Penting: Matikan semua mesin saat switch dari Auto ke Manual
        # Gunakan run_in_background agar main thread tidak freeze
        self.emergency_kill_all() 
        
        # Update UI Dashboard
        self.set_dashboard_grayscale(False)

    def stop_all_machines(self):
        print("!!! SAFETY SHUTDOWN TRIGGERED !!!")
        # Matikan semua KECUALI ALARM
        self.emergency_kill_all(keep_alarm=True)
        
        if hasattr(self, 'critical_alarms_active'):
            self.critical_alarms_active.clear()
        
        self.update_btn_alarm_display()

    def update_mode_ui(self):
        base_style = "min-width: 80px; min-height: 80px; max-width: 80px; max-height: 80px; border-radius: 43px; border: 3px solid black; font-weight: bold; font-size: 14px; color: white;"
        if self.system_mode == "AUTO":
            if hasattr(self, 'btn_auto'): self.btn_auto.setStyleSheet(base_style + "background-color: green;")
            if hasattr(self, 'btn_manual'): self.btn_manual.setStyleSheet(base_style + "background-color: #bfbfbf; color: #505050;")
        else:
            if hasattr(self, 'btn_auto'): self.btn_auto.setStyleSheet(base_style + "background-color: #bfbfbf; color: #505050;")
            if hasattr(self, 'btn_manual'): self.btn_manual.setStyleSheet(base_style + "background-color: blue;")

    def refresh_global_alarm_state(self):
        trip_active = len(self.active_hardware_trips) > 0
        alarm_active = len(self.critical_alarms_active) > 0
        soft_stop_active = getattr(self, 'soft_emergency_active', False) # Cek flag ini juga

        # Jika ada Trip Hardware ATAU Alarm Kritis ATAU Soft Stop (GUI Stop)
        is_emergency = trip_active or alarm_active or soft_stop_active
        
        is_snoozed = self.buzzer_snooze_timer.isActive()

        if is_emergency:
            # Nyalakan Buzzer (kecuali di-snooze)
            self.direct_write_hardware('ALARM', not is_snoozed)
        else:
            # Jika aman, ikuti tombol manual alarm
            self.direct_write_hardware('ALARM', self.manual_alarm_active)
            self.buzzer_snooze_timer.stop()
            
        self.update_btn_alarm_display()

    def on_btn_alarm_click(self):
        has_trips = len(self.active_hardware_trips) > 0
        has_critical = len(self.critical_alarms_active) > 0
        is_soft_stop = getattr(self, 'soft_emergency_active', False)
        
        system_emergency = has_trips or has_critical or is_soft_stop
        
        if system_emergency: 
            if is_soft_stop and not has_trips and not has_critical:
                print("[ALARM] Resetting Soft Emergency via Button.")
                self.soft_emergency_active = False
                self._request_buzzer(False)
                if self.buzzer_snooze_timer.isActive():
                    self.buzzer_snooze_timer.stop()
                
                self.update_btn_alarm_display()
                return
            
            # Jika sedang trip/critical, tombol ini berfungsi sebagai SNOOZE / ACKNOWLEDGE
            if self.buzzer_snooze_timer.isActive():
                # UNSNOOZE
                self.buzzer_snooze_timer.stop()
                self._request_buzzer(True)
            else:
                # SNOOZE
                self._request_buzzer(False)
                self.buzzer_snooze_timer.start(self.SNOOZE_DURATION)
                
        else:
            # Manual Toggle biasa
            self.manual_alarm_active = not self.manual_alarm_active
            self._request_buzzer(self.manual_alarm_active)
            
        self.update_btn_alarm_display()

    def _request_buzzer(self, state):
        self.run_in_background(self.direct_write_hardware, 'ALARM', state)

    def update_btn_alarm_display(self):
        if not hasattr(self, 'btn_alarm'): return
        base_style = "min-width: 80px; min-height: 80px; border-radius: 43px; border: 3px solid #333; font-weight: bold; color: white;"
        is_snoozed = self.buzzer_snooze_timer.isActive()
        is_danger = (len(self.active_hardware_trips) > 0) or \
                    (len(self.critical_alarms_active) > 0) or \
                    getattr(self, 'soft_emergency_active', False) or \
                    getattr(self, 'physical_estop_active', False)
        if is_snoozed and is_danger:
            self.btn_alarm.setStyleSheet(base_style + "background-color: #FFD700; color: black;")
            self.btn_alarm.setText("SNOOZED")
        elif is_danger or self.manual_alarm_active:
            self.btn_alarm.setStyleSheet(base_style + "background-color: #FF0000;")
            self.btn_alarm.setText("ALARM\nACTIVE")
        else:
            self.btn_alarm.setStyleSheet(base_style + "background-color: #808080;")
            self.btn_alarm.setText("ALARM\nOFF")

    def handle_auto_maintenance(self, alarm_name, message):
        print(f"[AUTO-MAINTENANCE] Triggered for {alarm_name}")
        MaintenanceLogger.log_action(item=alarm_name, action=f"Auto-generated: {message}", user="SYSTEM", status="Pending")        
        self.refresh_maintenance_list()

    def handle_alarm_value_update(self, data):
        alarm_name = data['alarmName']
        new_val = data['value']
        msg = data['message']
        if alarm_name in self.active_alarm_widgets:
            _, lbl_info = self.active_alarm_widgets[alarm_name]
            lbl_info.setText(f"<b>{alarm_name}</b><br>{msg} (Val: {new_val:.2f})")

    def handle_alarm_triggered(self, alarm):
        alarm_name = alarm.get("alarmName", "")
        alarm_type = alarm.get("alarmType", "Warning")
        message = alarm.get("message", "")

        is_new_alarm = (alarm_name not in self.active_alarm_widgets)
        if not is_new_alarm and self.buzzer_snooze_timer.isActive():
            return

        # [Logic Penghapusan Warning jika Critical muncul - Tetap Sama]
        if "Critical" in alarm_type or "LL" in alarm_name or "HH" in alarm_name:
            target_warning = ""
            if "LL" in alarm_name: target_warning = alarm_name.replace("LL", "LO")
            elif "HH" in alarm_name: target_warning = alarm_name.replace("HH", "HI")
            
            if target_warning and target_warning in self.active_alarm_widgets:
                self.remove_alarm_card(target_warning)
                if target_warning in self.critical_alarms_active: 
                    self.critical_alarms_active.discard(target_warning)
        
        # --- FILTER ALARM & BUZZER ---
        should_buzz = False
        if "TRIP" in alarm_name or "HH" in alarm_name or "LL" in alarm_name:
            should_buzz = True

        # --- EKSEKUSI ALARM ---
        
        # 1. Update Status Emergency Global
        if should_buzz:
            if is_new_alarm and self.buzzer_snooze_timer.isActive():
                self.buzzer_snooze_timer.stop()
                print(f"[ALARM] New Critical Alarm {alarm_name}. Snooze Cancelled.")

            self.soft_emergency_active = True
            if alarm_name not in self.critical_alarms_active:
                self.critical_alarms_active.add(alarm_name)
            if not self.buzzer_snooze_timer.isActive():
                self.refresh_global_alarm_state()

        # 2. Tampilkan Toast (Hanya jika alarm baru)
        if is_new_alarm:
            toast_title = f"ALARM: {alarm_name}"
            if should_buzz: toast_title = f"CRITICAL: {alarm_name}"
            
            toast = ToastNotification(self, toast_title, message, alarm_name, self)
            toast.show_animated()
            self.active_toasts[alarm_name] = toast

            # 3. Log & Email
            EventLogger.log_event("ALARM_TRIGGERED", alarm_name, message, value=alarm.get('value', 0), user="SYSTEM")
            if alarm_type == "Critical" or should_buzz:
                email_to = alarm.get("emailTo")
                if email_to: 
                    self.run_in_background(MainSystemController.send_email_alert, email_to, f"ALARM {alarm_name}", message)

        self.add_alarm_card(alarm) 
        self.refresh_event_log_ui()
        self.update_btn_alarm_display()
    
    def handle_alarm_resolved(self, alarm_data):
        alarm_name = alarm_data.get("alarmName")
        if alarm_name in self.critical_alarms_active:
            self.critical_alarms_active.discard(alarm_name)

        if alarm_name in self.active_alarm_widgets:
            widget_tuple = self.active_alarm_widgets.pop(alarm_name)
            card_widget = widget_tuple[0]
            layout = self.activeAlarms_contents.layout()
            if layout:
                layout.removeWidget(card_widget)
            
            card_widget.setParent(None)
            card_widget.deleteLater()
            val = alarm_data.get("value", "-")
            EventLogger.log_event("System", "Resolved", f"{alarm_name} back to normal", value=val, user="SYSTEM")

        if alarm_name in self.active_toasts:
            try:
                self.active_toasts[alarm_name].close()
                del self.active_toasts[alarm_name]
            except: pass

        if len(self.critical_alarms_active) == 0 and len(self.active_hardware_trips) == 0:
            print("[SYSTEM] All Alarms Resolved. Resetting Emergency State.")
            self.soft_emergency_active = False 
            self.manual_alarm_active = False 
            if self.buzzer_snooze_timer.isActive():
                self.buzzer_snooze_timer.stop()
                
            self.direct_write_hardware('ALARM', False)
        self.refresh_global_alarm_state()
    
    def handle_snooze_timeout(self):
        self.refresh_global_alarm_state()
        self.update_btn_alarm_display()

    def open_control_dialog(self, button, name, DialogClass, reg_key):
        # 1. CEK SAFETY
        if getattr(self, 'estop_is_locked', False):
            QMessageBox.critical(self, "LOCKED", "Sistem Emergency (Physical Estop).")
            return
        
        if issubclass(DialogClass, VFDDialog) and "BL_" in reg_key: 
            current_hz = self.saved_blower_hz 
            dlg = DialogClass(self, component_name=name)
            self._apply_contrast_style(dlg)
            self.apply_touch_logic(dlg)
            
            if hasattr(dlg, 'set_frequency'): dlg.set_frequency(current_hz)
            
            if dlg.exec_() == QDialog.Accepted:
                new_freq = dlg.get_frequency() # Pastikan method ini ada di VFDDialog
                
                if new_freq > 0:
                    # User ingin START / Ganti Speed
                    self.saved_blower_hz = float(new_freq)
                    self.run_in_background(self.direct_write_hardware, reg_key, True, new_freq)
                    
                    if self.system_mode == "AUTO" and hasattr(self, 'auto_worker'):
                        self.auto_worker.set_blower_setpoint(new_freq)
                    if self.system_mode == "MANUAL":
                        pass
                    self.save_last_state()
                else:
                    self.run_in_background(self.direct_write_hardware, reg_key, False, 0)
            return

        # 3. MAPPING SMART MANUAL (LOGIC LAMA)
        smart_map = {
            'TP_03A': 'MBR_SYS', 'TP_03B': 'MBR_SYS', 'TP_04': 'MBR_SYS', 
            'TP_02A': 'TP_02',   'TP_02B': 'TP_02',
            'TP_01A': 'EQ_SYS',  'TP_01B': 'EQ_SYS', 'SM_01': 'EQ_SYS',  'SM_02': 'EQ_SYS', 'TP_IN_A': 'EQ_SYS', 'TP_IN_B': 'EQ_SYS' 
        }

        # Di mode MANUAL murni, bypass semua smart group agar pompa menyala/mati secara mandiri.
        if self.system_mode == "MANUAL":
            target_req_key = None
        else:
            target_req_key = smart_map.get(reg_key)

        # 4. BLOKIR GRUP LAIN JIKA FULL AUTO
        if self.system_mode == "AUTO":
            QMessageBox.warning(self, "Mode Auto", "Sistem sedang FULL AUTO.\nMatikan tombol AUTO global untuk kontrol manual parsial.")
            return

        # 5. EKSEKUSI SMART MANUAL GRUP
        if target_req_key:
            current_state = self.manual_requests.get(target_req_key, False)
            if current_state:
                # User ingin STOP Group
                msg = f"Matikan SIKLUS Manual untuk Grup {target_req_key}?"
                if QMessageBox.question(self, "Stop Siklus", msg) == QMessageBox.Yes:
                    self.manual_requests[target_req_key] = False
                    self.record_activity("Operator", "Manual Stop", f"Disabled Group {target_req_key}")
            else:
                # User ingin START Group
                dialog = MachineOnDialogUI(self, component_name=f"Smart Group: {name}")
                if dialog.exec_() == QDialog.Accepted:
                    self.manual_requests[target_req_key] = True
                    self.record_activity("Operator", "Manual Start", f"Enabled Group {target_req_key}")

            self.update_shift_worker_status()
            self.save_last_state()
            
        # 6. KOMPONEN MANUAL BIASA (Dosing, Valve, dll)
        else:
            is_on = self.system_state.get(reg_key, False)
            
            # Khusus VFD Non-Blower (misal Pompa MBR Manual Control jika Smart Group mati)
            if issubclass(DialogClass, VFDDialog):
                 curr_f = self.vfd_frequencies.get(reg_key, 0.0)
                 dlg = DialogClass(self, component_name=name, current_freq=curr_f)
                 if dlg.exec_() == QDialog.Accepted:
                     freq = dlg.get_frequency()
                     state = (freq > 0)
                     self.run_in_background(self.direct_write_hardware, reg_key, state, freq)
            
            # On/Off Biasa
            else:
                if is_on:
                    dlg = MachineOffDialogUI(self, component_name=name)
                    if dlg.exec_() == QDialog.Accepted:
                        self.run_in_background(self.direct_write_hardware, reg_key, False)
                        self.record_activity(self.current_user, "Manual Stop", f"Stopped {name} ({reg_key})")
                else:
                    dlg = DialogClass(self, component_name=name)
                    if dlg.exec_() == QDialog.Accepted:
                        self.run_in_background(self.direct_write_hardware, reg_key, True)
                        self.record_activity(self.current_user, "Manual Start", f"Started {name} ({reg_key})")
    
    # --- FITUR NUMPAD HELPER ---
    def open_numpad(self, target_widget=None, title="Input Value"):
        """
        Membuka Numpad Dialog.
        Jika target_widget diberikan (QLineEdit/QDoubleSpinBox/QLabel),
        nilai awal diambil dari widget tersebut, dan hasil return diset kembali ke widget.
        """
        # 1. Ambil nilai awal
        initial_val = ""
        if target_widget:
            if isinstance(target_widget, (QtWidgets.QLineEdit, QtWidgets.QLabel)):
                initial_val = target_widget.text()
            elif isinstance(target_widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                initial_val = str(target_widget.value())
            elif isinstance(target_widget, QtWidgets.QPushButton):
                initial_val = target_widget.text().replace(" Hz", "").replace(" A", "") # Bersihkan unit

        # 2. Buka Dialog
        dlg = NumpadDialog(self, initial_value=initial_val, title=title)
        
        # Posisikan di tengah layar aplikasi
        dlg.move(self.geometry().center() - dlg.rect().center())
        
        if dlg.exec_() == QDialog.Accepted:
            new_val = dlg.get_value()
            
            # 3. Kembalikan nilai ke widget target (jika ada)
            if target_widget:
                if isinstance(target_widget, QtWidgets.QLineEdit):
                    target_widget.setText(str(new_val))
                elif isinstance(target_widget, QtWidgets.QLabel):
                    target_widget.setText(str(new_val))
                elif isinstance(target_widget, QtWidgets.QDoubleSpinBox):
                    target_widget.setValue(float(new_val))
                elif isinstance(target_widget, QtWidgets.QSpinBox):
                    target_widget.setValue(int(new_val))
                elif isinstance(target_widget, QtWidgets.QPushButton):
                    # Berguna jika tombol itu sendiri menampilkan angka
                    target_widget.setText(f"{new_val}")
            
            return new_val
        
        return None
                
    def apply_touch_logic(self, dialog):
        """
        Mencari semua input (LineEdit, SpinBox) dalam dialog
        dan memasang event filter agar saat diklik muncul Numpad.
        """
        # Pastikan filter dibuat (simpan di self agar tidak kena garbage collect)
        self.touch_filter = TouchInputFilter(self)
        
        # Cari widget input
        inputs = dialog.findChildren((QtWidgets.QLineEdit, QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox))
        
        for widget in inputs:
            # Hapus focus policy keyboard fisik (opsional, agar keyboard OS tidak muncul)
            # widget.setAttribute(Qt.WA_InputMethodEnabled, False) 
            
            # Pasang filter
            widget.installEventFilter(self.touch_filter)
            print(f"[NUMPAD] Attached to {widget.objectName()}")

    def run_in_background(self, func, *args, **kwargs):
        self.threadpool.start(FunctionWorker(func, *args, **kwargs))

    def record_activity(self, user, action, details):
        self.logger.add_log(user, action, details)
        
    @staticmethod
    def send_email_alert(recipient, subject, body):
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587
        SENDER_EMAIL = "email_anda@gmail.com"
        SENDER_PASSWORD = "app_password_anda" 
        if not recipient: return
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = SENDER_EMAIL
            msg['To'] = recipient
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        except Exception: pass

    def init_control_buttons(self):
        self.component_status = {}
        self.buttons_config = [
            (getattr(self, 'btn_TP_IN_A', None), "Inlet Transfer Pump A (TP-01A)", MachineOnDialogUI, "TP_01A"),
            (getattr(self, 'btn_TP_IN_B', None), "Inlet Transfer Pump B (TP-01B)", MachineOnDialogUI, "TP_01B"),
            (getattr(self, 'btn_TP_01A', None),  "EQ Transfer Pump A (TP-02A)",    MachineOnDialogUI, "TP_02A"),
            (getattr(self, 'btn_TP_01B', None),  "EQ Transfer Pump B (TP-02B)",    MachineOnDialogUI, "TP_02B"),
            (getattr(self, 'btn_TP_02A', None),  "MBR RAS Sludge Pump A (TP-05A)", MachineOnDialogUI, "TP_05A"),
            (getattr(self, 'btn_TP_02B', None),  "MBR RAS Sludge Pump B (TP-05B)", MachineOnDialogUI, "TP_05B"),
            (getattr(self, 'btn_DP_01', None),   "Chlorine Dosing Pump (DP-01)",   MachineOnDialogUI, "DP_01"),
            (getattr(self, 'btn_BL_01A', None),  "MBR Blower 01A (BL-01A)",        MachineOnDialogUI, "BL_01A"),
            (getattr(self, 'btn_BL_01B', None),  "MBR Blower 01B (BL-01B)",        MachineOnDialogUI, "BL_01B"),
            (getattr(self, 'btn_TP_03A', None),  "MBR Permeate Pump A (TP-04A)",   VFDDialog,         "TP_04A"),
            (getattr(self, 'btn_TP_03B', None),  "MBR Permeate Pump B (TP-04B)",   VFDDialog,         "TP_04B"),
            (getattr(self, 'btn_TP_04', None),   "MBR Backwash Pump (TP-03)",      VFDDialog,         "TP_03"),
            (getattr(self, 'btn_AV101', None),   "Auto Valve 101 (AV-101)",        MachineOnDialogUI, "ACT_01"),
            (getattr(self, 'btn_AV102', None),   "Auto Valve 102 (AV-102)",        MachineOnDialogUI, "ACT_02"),
        ]
        for btn, name, DialogClass, reg_key in self.buttons_config:
            if btn is None: continue
            self.component_status[btn] = False
            btn.clicked.connect(lambda checked, b=btn, n=name, cls=DialogClass, k=reg_key: self.open_control_dialog(b, n, cls, k))

        if hasattr(self, 'btn_SM_01'):
            self.btn_SM_01.clicked.connect(lambda: self.open_sm_config_handler("SM_01"))
        if hasattr(self, 'btn_SM_02'):
            self.btn_SM_02.clicked.connect(lambda: self.open_sm_config_handler("SM_02"))

        if hasattr(self, 'btn_estop'): 
            # Menggunakan settingan lengkap agar tombol merah & berfungsi
            self.btn_estop.clicked.connect(self.handle_emergency_stop)
            self.btn_estop.setEnabled(True)
            self.btn_estop.setStyleSheet("""background-color: red; color: white; font-weight: bold; border: 3px solid black; border-radius: 43px;""")

        if hasattr(self, 'btn_auto'): self.btn_auto.clicked.connect(self.set_auto_mode)
        if hasattr(self, 'btn_manual'): self.btn_manual.clicked.connect(self.set_manual_mode)

    def init_main_navigation(self):
        self.dashboardMenu_btn.clicked.connect(lambda: self.workingArea.setCurrentWidget(self.dashboard))
        self.dataMenu_btn.clicked.connect(lambda: self.workingArea.setCurrentWidget(self.data))
        self.maintenanceMenu_btn.clicked.connect(lambda: self.workingArea.setCurrentWidget(self.maintenance))
        self.alarmMenu_btn.clicked.connect(lambda: self.workingArea.setCurrentWidget(self.alarm))
        self.btn0_menu.clicked.connect(lambda: (self.openedSideBar.setVisible(False), self.closedSideBar.setVisible(True)))
        self.btn0_menu_2.clicked.connect(lambda: (self.openedSideBar.setVisible(True), self.closedSideBar.setVisible(False)))
        if hasattr(self, "btn1_processFlowDiagram"): self.btn1_processFlowDiagram.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        if hasattr(self, "btn2_instrumentParameter"): self.btn2_instrumentParameter.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        if hasattr(self, "btn_view_sensor"): self.btn_view_sensor.clicked.connect(lambda: self.stackedWidget_data.setCurrentIndex(0))
        if hasattr(self, "btn_view_runtime"): self.btn_view_runtime.clicked.connect(lambda: self.stackedWidget_data.setCurrentIndex(1))
        if hasattr(self, "btn_view_totalizer"): self.btn_view_totalizer.clicked.connect(lambda: self.stackedWidget_data.setCurrentIndex(2))

    def init_tank_geometry(self):   
        for name in self.sensor_config.keys():
            if hasattr(self, name):
                geo = getattr(self, name).geometry()
                self.tank_geometry[name] = {'max_h': geo.height(), 'x': geo.x(), 'width': geo.width(), 'top_y': geo.y()}

    def init_instrument_page(self):
        # 1. Setup Layout Target
        # [FIX] Definisikan content_widget terlebih dahulu
        content_widget = self.scrollAreaWidgetContents
        
        # 2. Reset/Setup Layout
        if content_widget.layout() is not None:
            # Jika layout lama bukan Grid, ganti baru
            if not isinstance(content_widget.layout(), QtWidgets.QGridLayout):
                QtWidgets.QWidget().setLayout(content_widget.layout()) # Hack untuk melepas layout lama
                self.instrument_layout = QtWidgets.QGridLayout(content_widget)
            else:
                self.instrument_layout = content_widget.layout()
        else:
            self.instrument_layout = QtWidgets.QGridLayout(content_widget)

        # 3. Config Widget
        self.vfd_config = {
            'TP_04A': {'label': 'MBR Permeate A', 'unit': 'Hz'}, 
            'TP_04B': {'label': 'MBR Permeate B', 'unit': 'Hz'}, 
            'TP_03':  {'label': 'Backwash Pump',  'unit': 'Hz'}
        }
        
        self.sensor_chart_config = {
            'LT_101': {'label': 'Level Tank (LT-101)',      'unit': 'cm'}, 
            'PT_101': {'label': 'Pressure MBR (PT-101)',    'unit': 'Bar'}, 
            'FT_101': {'label': 'Flow Inlet / EQ (FT-101)', 'unit': 'm³/h'}, 
            'FT_102': {'label': 'Flow Permeate (FT-102)',   'unit': 'm³/h'}, 
            'FT_103': {'label': 'Flow Backwash (FT-103)',   'unit': 'm³/h'},
            'DO_101': {'label': 'Dissolved Oxygen (DO-101)','unit': 'mg/L'}
        }
        
        self.instrument_widgets = {}    
        self.instrument_indicators = {} 
        self.instrument_units = {}      
        
        row, col = 0, 0
        max_col = 2 

        # 4. Loop Pembuatan Widget
        all_items = {**self.vfd_config, **self.sensor_chart_config}

        for key, cfg in all_items.items():
            label_text = cfg['label']
            unit_text = cfg['unit']
            
            # Container
            container = QtWidgets.QWidget()
            container.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #ddd;")
            main_v_layout = QtWidgets.QVBoxLayout(container)
            
            # Label Judul
            lbl_title = QtWidgets.QLabel(f"{label_text}")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333; padding: 5px;")
            main_v_layout.addWidget(lbl_title)

            # Inner Content
            content_widget_inner = QtWidgets.QWidget()
            content_layout = QtWidgets.QVBoxLayout(content_widget_inner) 
            content_layout.setContentsMargins(0,0,0,0)
            
            if key in self.vfd_config:
                # Gauge
                widget = SemiCircularGauge()
                widget.set_range(0, 50.0)
                widget.setMinimumSize(200, 180)
                content_layout.addWidget(widget) 
            else:
                # Chart
                widget = SensorChart()
                widget.set_title_name(f"{label_text} ({unit_text})") 
                
                # Setup specific ranges for Level Sensors (Optional)
                if "LT" in key: 
                    widget.set_max_level(284.0) 

                widget.setMinimumSize(300, 200)
                content_layout.addWidget(widget)

            main_v_layout.addWidget(content_widget_inner)
            self.instrument_layout.addWidget(container, row, col)
            self.instrument_widgets[key] = widget
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1
    
    def setup_data_table(self):
        """
        [FIX] Update Header Tabel mencakup Totalizer
        """
        if not hasattr(self, 'tableWidget'): return

        headers = [
            "Time", 
            "Level EQ (cm)", "Level Aeration (cm)", "Level MBR (cm)",
            "Inlet Flow (m³/h)", "MBR Flow (m³/h)", "Backwash Flow (m³/h)",
            "Pressure (Bar)", 
        ]
        
        self.tableWidget.setColumnCount(len(headers)) 
        self.tableWidget.setHorizontalHeaderLabels(headers) 
        
        header = self.tableWidget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch) 
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.setAlternatingRowColors(True)
    
    def setup_totalizer_table(self):
        """Setup tampilan tabel Totalizer (Header & Format)"""
        if not hasattr(self, 'tableWidget_totalizer'): return

        # 1. Definisi Header (Sesuai Gambar)
        headers = ["Date", "FT 101 Inlet (m³)", "FT 102 MBR (m³)", "FT 03 Backwash (m³)"]
        self.tableWidget_totalizer.setColumnCount(len(headers))
        self.tableWidget_totalizer.setHorizontalHeaderLabels(headers)
        
        # 2. Styling Visual
        header = self.tableWidget_totalizer.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch) 
        self.tableWidget_totalizer.verticalHeader().setVisible(False) 
        self.tableWidget_totalizer.setAlternatingRowColors(True) 
        self.tableWidget_totalizer.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers) 

    def load_totalizer_history_to_table(self):
        """Membaca CSV History dan menampilkan ke Tabel"""
        if not hasattr(self, 'tableWidget_totalizer'): return
        
        # 1. Ambil data dari CSV via LogManager
        history_data = TotalizerLogger.read_history()
        
        # 2. Masukkan ke Tabel UI
        self.tableWidget_totalizer.setRowCount(0) 
        
        for row_data in history_data:
            # Pastikan data valid (minimal 4 kolom)
            if len(row_data) >= 4:
                row_idx = self.tableWidget_totalizer.rowCount()
                self.tableWidget_totalizer.insertRow(row_idx)
                
                # Loop isi kolom (Date, Val1, Val2, Val3)
                for i, val in enumerate(row_data):
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignCenter) 
                    self.tableWidget_totalizer.setItem(row_idx, i, item)
    
    def get_active_shift_suffix(self, group_name="TP_01"):
        if group_name == 'BL_01' and hasattr(self, 'auto_worker'):
            return getattr(self.auto_worker, 'blower_active_suffix', 'A')
        if hasattr(self, 'shift_worker'):
            grp = self.shift_worker.groups.get(group_name)
            if grp: return grp['Active']
        return 'A' 

    def init_maintenance_buttons(self):
        if hasattr(self, "btn_shift_config"): self.btn_shift_config.clicked.connect(self.open_shift_config)
        if hasattr(self, "btn_transmitter_config"): self.btn_transmitter_config.clicked.connect(self.open_transmitter_config)
        if hasattr(self, "btn_ceb_maintenance"): self.btn_ceb_maintenance.clicked.connect(self.open_ceb_maintenance)
        if hasattr(self, "btn_back"):
            self.btn_back.clicked.connect(lambda: self.stackedWidget_2.setCurrentIndex(0)) 
        if hasattr(self, "pushButton"):
            self.pushButton.clicked.connect(self.action_toggle_status)
        if hasattr(self, "logList"):
            self.logList.itemClicked.connect(self.on_maintenance_list_clicked)
        if hasattr(self, "btn_prev"):
            self.btn_prev.clicked.connect(self.action_prev_log)
        if hasattr(self, "btn_next"):
            self.btn_next.clicked.connect(self.action_next_log)
        if hasattr(self, "pushButton_2"):
            self.pushButton_2.clicked.connect(self.save_maintenance_description)
        self.refresh_maintenance_list()

    def refresh_maintenance_list(self):
        if not hasattr(self, 'logList'): return
        self.logList.clear()
        logs = MaintenanceLogger.read_logs()
        for row in reversed(logs):
            date_str = row.get("Date", row.get("Time", ""))
            item_name = row.get("Item", "")
            action = row.get("Action", "")
            user = row.get("User", "")
            status = row.get("Status", "Done") 
            
            # [UPDATE] Logic Teks Tampilan
            display_text = f"[{date_str}] {action} - {item_name}"
            
            if status == "Pending":
                display_text = "⚠️ [PENDING] " + display_text
                color = Qt.red
            else:
                # Jika status Done, tambahkan info siapa yang mengerjakan
                if user:
                    display_text += f" (Done by {user})"
                color = Qt.black

            list_item = QListWidgetItem(display_text)
            list_item.setForeground(color)
            
            item_data = {"date": date_str, "item": item_name, "action": action, "user": user, "status": status}
            list_item.setData(Qt.UserRole, item_data)
            self.logList.addItem(list_item)

    def on_maintenance_list_clicked(self, item):
        row = self.logList.row(item)
        self.load_maintenance_by_index(row)
    
    def load_maintenance_by_index(self, index):
        total_items = self.logList.count()
        if index < 0 or index >= total_items: return
        self.current_maint_index = index
        item = self.logList.item(index)
        data = item.data(Qt.UserRole)
        if not data: return
        if hasattr(self, "detail_name"): self.detail_name.setText(data.get('user', '-'))
        status_text = data.get('status', 'Done')
        if hasattr(self, "detail_status"): self.detail_status.setText(status_text)        
        if hasattr(self, "detail_date"): self.detail_date.setText(data.get('date', '-'))
        if hasattr(self, "detail_date_2"): self.detail_date_2.setText(data.get('item', '-'))
        if hasattr(self, "detail_issue"): 
            self.detail_issue.setPlainText(data.get('action', ''))
            self.detail_issue.setReadOnly(False) 
            self.detail_issue.setPlaceholderText("Tulis detail maintenance atau catatan di sini...")
        if hasattr(self, "lbl_agenda_title"): self.lbl_agenda_title.setText("Edit Mode") 
        self.update_toggle_button_style(status_text)
        if hasattr(self, "lbl_index"): self.lbl_index.setText(f"Log {index + 1} of {total_items}")
        if hasattr(self, "btn_prev"): self.btn_prev.setEnabled(index > 0)
        if hasattr(self, "btn_next"): self.btn_next.setEnabled(index < total_items - 1)
        if hasattr(self, "stackedWidget_2"): self.stackedWidget_2.setCurrentIndex(1)
    
    def update_toggle_button_style(self, status):
        """Mengubah warna tombol maintenance berdasarkan status"""
        if not hasattr(self, "pushButton"): return
        clean_status = str(status).strip().lower()
        if clean_status == "done":
            self.pushButton.setStyleSheet("QPushButton {background-color: #28a745; color: white; font-weight: bold; border-radius: 5px; border: 1px solid #1e7e34; font-size: 14px; padding: 8px;} QPushButton:hover {background-color: #218838;}")
            self.pushButton.setText("Maintenance Done ✓")
        else: 
            self.pushButton.setStyleSheet("QPushButton {background-color: white; color: #d9534f; font-weight: bold; border-radius: 5px; border: 2px solid #d9534f; font-size: 14px; padding: 8px;} QPushButton:hover {background-color: #fcefe9;}")
            self.pushButton.setText("Mark as Done")

    def action_toggle_status(self):
        if not hasattr(self, 'current_maint_index') or self.current_maint_index is None:
            return
        item = self.logList.item(self.current_maint_index)
        if not item: return
        data = item.data(Qt.UserRole)
        
        current_status = data.get('status', 'Done') 
        new_status = "Done" if current_status == "Pending" else "Pending"
        
        # [UPDATE] Rekam User saat ini sebagai pelaksana
        user_in_charge = self.current_user if new_status == "Done" else data.get('user', '')
        
        total_items = self.logList.count()
        csv_index = total_items - 1 - self.current_maint_index
        
        # Update ke CSV
        MaintenanceLogger.update_log_status(csv_index, new_status, user_who_updated=user_in_charge)
        
        # Update Data Item Memori
        data['status'] = new_status
        data['user'] = user_in_charge # Simpan user baru ke item data
        item.setData(Qt.UserRole, data)
        
        # Refresh Tampilan Text List (Supaya "Done by..." langsung muncul)
        display_text = f"[{data['date']}] {data['action']} - {data['item']}"
        if new_status == "Pending":
            display_text = "⚠️ [PENDING] " + display_text
            item.setForeground(Qt.red)
        else:
            if user_in_charge:
                display_text += f" (Done by {user_in_charge})"
            item.setForeground(Qt.black)
            
        item.setText(display_text)
        
        if hasattr(self, "detail_status"): self.detail_status.setText(new_status)
        if hasattr(self, "detail_name"): self.detail_name.setText(user_in_charge) # Update detail view juga
        
        self.update_toggle_button_style(new_status)
        QMessageBox.information(self, "Success", f"Status changed to {new_status}")
        
    def save_maintenance_description(self):
        if not hasattr(self, 'current_maint_index'): return
        new_text = self.detail_issue.toPlainText().strip()
        total_items = self.logList.count()
        csv_index = total_items - 1 - self.current_maint_index
        success = MaintenanceLogger.update_log_action(csv_index, new_text, user_who_updated=self.current_user)
        if success:
            item = self.logList.item(self.current_maint_index)
            data = item.data(Qt.UserRole)
            data['action'] = new_text
            data['user'] = self.current_user 
            item.setData(Qt.UserRole, data)
            display_text = f"[{data['date']}] {new_text} - {data['item']}"
            if data['status'] == "Pending":
                display_text = "⚠️ [PENDING] " + display_text
            item.setText(display_text)
            if hasattr(self, "detail_name"): self.detail_name.setText(self.current_user)
            QMessageBox.information(self, "Disimpan", "Deskripsi maintenance berhasil diperbarui!")
        else:
            QMessageBox.critical(self, "Error", "Gagal menyimpan perubahan ke file CSV.")

    def open_ceb_maintenance(self):
        from custom_dialogs import CEBMaintenanceDialog
        dialog = CEBMaintenanceDialog(parent=self)
        self._apply_contrast_style(dialog) 

        result = dialog.exec_()
        self.ceb_is_active = False
        if result == QDialog.Accepted:
            self.refresh_maintenance_list()
            if hasattr(self, 'auto_worker'): self.auto_worker.load_configs()
        else:
            print("[CEB] Process Cancelled/Interrupted. Log preserved.") 

    def open_shift_config(self):
        from custom_dialogs import ShiftConfigDialog
        dialog = ShiftConfigDialog(self)
        self._apply_contrast_style(dialog)
        self.apply_touch_logic(dialog)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_maintenance_list()
            if hasattr(self, 'shift_worker'): self.shift_worker.load_shift_settings()
            if hasattr(self, 'auto_worker'): self.auto_worker.load_configs()

    def open_transmitter_config(self):
        from custom_dialogs import TransmitterConfigDialog
        dialog = TransmitterConfigDialog(self)
        self._apply_contrast_style(dialog)
        self.apply_touch_logic(dialog)
        if dialog.exec_() == QDialog.Accepted:
            # Reload untuk Alarm Monitor (GUI Alarm)
            if hasattr(self, 'alarm_monitor'): 
                self.alarm_monitor.reload_csv_settings()
            # [BARU] Reload untuk AutoPilot (Logic Mesin & ESTOP)
            if hasattr(self, 'auto_worker'):
                self.auto_worker.load_configs()
                
            self.refresh_maintenance_list()
            QMessageBox.information(self, "Config Updated", "Limit Transmiter berhasil diperbarui!")
            
    def open_sm_config_handler(self, key): 
        if self.system_mode == "MANUAL":
            btn = getattr(self, f"btn_{key}", None)
            name = "Submersible Mixer 01" if key == "SM_01" else "Submersible Mixer 02"
            from custom_dialogs import MachineOnDialogUI
            self.open_control_dialog(btn, name, MachineOnDialogUI, key)
            return

        current_val = 30.0
        if hasattr(self, 'auto_worker'):
            current_val = self.auto_worker.sm_duration_minutes

        # Buka Dialog
        from dialog_handlers import SMConfigDialog  
        dlg = SMConfigDialog(self, current_duration=current_val)
        self._apply_contrast_style(dlg)
        self.apply_touch_logic(dlg)
        
        if dlg.exec_() == QDialog.Accepted:
            new_duration = dlg.get_duration()
            
            # Update Worker
            if hasattr(self, 'auto_worker'):
                self.auto_worker.set_sm_duration_config(new_duration)
            
            self.save_last_state()
    
    def action_prev_log(self):
        if hasattr(self, 'current_maint_index') and self.current_maint_index > 0:
            self.load_maintenance_by_index(self.current_maint_index - 1)

    def action_next_log(self):
        if hasattr(self, 'current_maint_index') and self.current_maint_index < self.logList.count() - 1:
            self.load_maintenance_by_index(self.current_maint_index + 1)

    def init_alarm_monitor(self): 
        if hasattr(self, 'alarm_monitor') and self.alarm_monitor is not None:
            print("Stopping previous AlarmMonitor thread...")
            try:
                # Putuskan semua koneksi sinyal dulu agar tidak ada sisa trigger
                self.alarm_monitor.alarm_triggered_signal.disconnect()
                self.alarm_monitor.alarm_resolved_signal.disconnect()
                self.alarm_monitor.auto_maintenance_signal.disconnect()
                self.alarm_monitor.alarm_value_update_signal.disconnect()
            except Exception:
                pass # Abaikan jika belum connect

            # Matikan Thread Lama
            self.alarm_monitor.stop()
            self.alarm_monitor.wait() # Tunggu sampai benar-benar mati
            self.alarm_monitor.deleteLater() # Hapus dari memori

        # Baru buat instance baru
        self.alarm_monitor = AlarmMonitor(parent=self) 
        # Connect Signal (Sekarang pasti single connection)
        self.alarm_monitor.alarm_triggered_signal.connect(self.handle_alarm_triggered)
        self.alarm_monitor.alarm_resolved_signal.connect(self.handle_alarm_resolved)
        # [FIX LOGIC] Gunakan fungsi yang sudah difilter tadi
        self.alarm_monitor.auto_maintenance_signal.connect(self.handle_auto_maintenance) 
        self.alarm_monitor.alarm_value_update_signal.connect(self.handle_alarm_value_update) 
        self.alarm_monitor.start()
        print("AlarmMonitor Started (Clean Instance).")
        
    def init_alarm_page_logic(self):
        if hasattr(self, 'btn2_ActiveAlarms'): self.btn2_ActiveAlarms.clicked.connect(lambda: self.alarmView.setCurrentWidget(self.activeAlarms_window))
        if hasattr(self, 'btn3_EventLog'): self.btn3_EventLog.clicked.connect(lambda: self.alarmView.setCurrentWidget(self.eventLog_window))

    def add_alarm_card(self, data):
        if not hasattr(self, 'activeAlarms_contents'): return
        alarm_name = data['alarmName']
        if alarm_name in self.active_alarm_widgets:
            return 
        card = QtWidgets.QFrame()
        color = "red" if "critical" in data.get('alarmType', '').lower() else "orange"
        card.setStyleSheet(f"background-color: #ffcccc; border-left: 5px solid {color}; margin-bottom: 5px; border-radius: 4px;")
        card.setMinimumHeight(70)
        layout = QtWidgets.QHBoxLayout(card)
        layout.addWidget(QtWidgets.QLabel(data['timestamp']))
        lbl = QtWidgets.QLabel(f"<b>{alarm_name}</b><br>{data['message']} (Val: {data['value']:.2f})")
        layout.addWidget(lbl)
        if self.activeAlarms_contents.layout() is None: 
            self.activeAlarms_contents.setLayout(QtWidgets.QVBoxLayout())
        self.activeAlarms_contents.layout().insertWidget(0, card)
        self.active_alarm_widgets[alarm_name] = (card, lbl)

    def remove_alarm_card(self, name):
        if name in self.active_alarm_widgets:
            self.active_alarm_widgets[name][0].deleteLater()
            del self.active_alarm_widgets[name]
            
    def refresh_event_log_ui(self):
        """
        [AESTHETIC UPGRADE] Membaca Event Log dengan tampilan Modern Card.
        """

        # 1. Tentukan Path File Hari Ini
        today = datetime.datetime.now()
        month_str = today.strftime("%Y-%m")
        date_str = today.strftime("%Y-%m-%d")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "datalog_alarms", month_str, f"{date_str}.csv")

        # [OPTIMASI] Cek Apakah File Berubah?
        if not os.path.exists(file_path): return
        
        try:
            current_mtime = os.path.getmtime(file_path)
            # Jika waktu modifikasi file SAMA dengan terakhir kali baca, JANGAN LAKUKAN APAPUN.
            if hasattr(self, 'last_log_mtime') and current_mtime == self.last_log_mtime:
                return 
            
            # Update timestamp terakhir
            self.last_log_mtime = current_mtime
        except Exception: 
            pass

        # 2. Setup Layout
        if not hasattr(self, 'eventLog_contents'): return

        # [FIX] Check for existing layout carefully
        if self.eventLog_contents.layout() is None:
            layout = QtWidgets.QVBoxLayout(self.eventLog_contents)
            layout.setAlignment(Qt.AlignTop)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)
        else:
            layout = self.eventLog_contents.layout()

        # 3. Bersihkan Tampilan Lama
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None) # Detach first
                widget.deleteLater()   # Then delete

        # 4. BACA CSV (LOGIC RELATIVE PATH)
        logs = []
        try:
            today = datetime.datetime.now()
            month_str = today.strftime("%Y-%m")
            date_str = today.strftime("%Y-%m-%d")

            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, "datalog_alarms", month_str, f"{date_str}.csv")

            if os.path.exists(file_path):
                with open(file_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    logs = list(reader)[::-1] 
        except Exception as e:
            print(f"[EVENT LOG] Error: {e}")

        # 5. TAMPILKAN KE UI (NEW AESTHETIC DESIGN)
        for log in logs:
            ts = log.get('Timestamp', '-')
            event_type = log.get('Event', 'EVENT').upper()
            item_name = log.get('Alarm Name', log.get('Item', 'Unknown'))
            details = log.get('Message', log.get('Details', '-'))
            user = log.get('User', 'SYSTEM')

            # --- Logic Warna & Badge (Soft/Pastel Colors) ---
            # Default (Grey/Info)
            bg_color = "#f3f4f6"
            text_color = "#374151"
            border_color = "#9ca3af"
            icon_symbol = "ℹ️"

            evt_check = str(event_type).upper()
            if "TRIGGER" in evt_check or "CRITICAL" in evt_check or "TRIP" in evt_check:
                bg_color = "#fee2e2"   # Merah Muda Soft
                text_color = "#b91c1c" # Merah Tua
                border_color = "#ef4444"
                icon_symbol = "🚨"
            elif "RESOLVED" in evt_check or "NORMAL" in evt_check:
                bg_color = "#dcfce7"   # Hijau Muda Soft
                text_color = "#15803d" # Hijau Tua
                border_color = "#22c55e"
                icon_symbol = "✅"
            elif "ACK" in evt_check:
                bg_color = "#dbeafe"   # Biru Muda Soft
                text_color = "#1d4ed8" # Biru Tua
                border_color = "#3b82f6"
                icon_symbol = "👤"

            # --- Container Kartu ---
            card = QtWidgets.QFrame()
            # Style CSS: Rounded corners, light border, slight shadow effect
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: white;
                    border-radius: 8px;
                    border: 1px solid #e5e7eb;
                    border-left: 4px solid {border_color};
                }}
                QLabel {{
                    border: none;
                    background-color: transparent;
                }}
            """)
            
            # Layout Horizontal agar rapi
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(4)

            # --- CONTENT MENGGUNAKAN HTML TABLE AGAR RAPI ---
            # Baris 1: Badge Event + Waktu (Kanan)
            # Baris 2: Nama Item (Besar)
            # Baris 3: Pesan + User
            
            html_content = f"""
            <html>
            <head>
                <style>
                    * {{ font-family: 'Segoe UI', sans-serif; }}
                </style>
            </head>
            <body>
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td valign="middle">
                            <span style="background-color: {bg_color}; color: {text_color}; 
                                         font-weight: bold; padding: 3px 6px; border-radius: 4px; font-size: 10px;">
                                {icon_symbol} {event_type}
                            </span>
                        </td>
                        <td align="right" valign="middle">
                            <span style="color: #9ca3af; font-size: 11px;">{ts}</span>
                        </td>
                    </tr>
                    <tr><td colspan="2" height="4"></td></tr> <tr>
                        <td colspan="2">
                            <span style="font-size: 14px; font-weight: 600; color: #1f2937;">{item_name}</span>
                        </td>
                    </tr>
                    
                    <tr>
                        <td colspan="2">
                            <span style="font-size: 12px; color: #6b7280;">{details}</span>
                            <br>
                            <span style="font-size: 10px; color: #9ca3af; font-style: italic;">
                                Action by: <b>{user}</b>
                            </span>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

            lbl_content = QtWidgets.QLabel(html_content)
            lbl_content.setWordWrap(True)
            lbl_content.setTextInteractionFlags(Qt.NoTextInteraction) # Agar tidak bisa diblok kursor
            
            card_layout.addWidget(lbl_content)
            layout.addWidget(card)
            
    @pyqtSlot(str)
    def handle_auto_signals(self, msg):
        if msg == "ESTOP_TRIGGERED": 
            self.handle_estop_active()
        elif msg.startswith("TRIP:"):
            reason = msg.split(":", 1)[1]
            self.handle_soft_emergency(reason)

    def load_external_stylesheet(self):
        try:
            with open(os.path.join(os.path.dirname(__file__), "Dashboard_new.css"), "r") as f:
                self.setStyleSheet(f.read())
        except: pass

    def _apply_contrast_style(self, dialog):
        troublemakers = [
            "groupBox_komponen", "groupBox_siklus", 
            "alarm_setting_bg", "recipient_setting_bg", 
            "alarm_setting", "recipient_setting",
            "top_widget", "bottom_widget",
            "recipient_data", "message_to_recipient", 
            "btn_apply", "btn_cancel", "create_btn", "cancel_btn"
        ]
        for name in troublemakers:
            widget = dialog.findChild(QWidget, name)
            if widget:
                widget.setStyleSheet("") 
                widget.setAttribute(Qt.WA_StyledBackground, True)
        dialog.setStyleSheet("""
            QDialog {background-color: #052460; color: white; font-family: "Segoe UI", "Arial", sans-serif; font-size: 14px;}
            QGroupBox, QFrame, QWidget#alarm_setting_bg, QWidget#recipient_setting_bg {background-color: #052460; border: 1px solid #aaaaaa; border-radius: 5px; margin-top: 15px; color: white;}
            QGroupBox::title {subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 5px; background-color: #052460; color: #ffaa00; font-weight: bold;}
            QLabel {color: white; background-color: transparent; font-weight: bold;}
            QLineEdit, QDoubleSpinBox, QSpinBox, QTimeEdit, QTextEdit {background-color: white; color: black; border: 1px solid #aaaaaa; border-radius: 4px; padding: 5px;}
            QLineEdit:focus, QDoubleSpinBox:focus {border: 2px solid #0d6efd;}
            QComboBox {background-color: white; color: black; border: 1px solid #aaaaaa; border-radius: 4px; padding: 5px; min-height: 25px;}
            QComboBox::drop-down {subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border-left: 1px solid #aaaaaa; background-color: #e0e0e0;}
            QComboBox::down-arrow {image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #052460; margin-right: 2px;}
            QComboBox QAbstractItemView {background-color: white; color: black; selection-background-color: #0d6efd; selection-color: white; border: 1px solid #052460; outline: 0px;}
            QComboBox QAbstractItemView::item {color: black; background-color: white;}
            QComboBox QAbstractItemView::item:selected {background-color: #0d6efd; color: white;}
            QPushButton {background-color: #0d6efd; color: white; font-weight: bold; border-radius: 5px; padding: 8px 15px; border: 1px solid #0a58ca;}
            QPushButton:hover {background-color: #0b5ed7;}
            QPushButton[text="Cancel"], QPushButton#btn_cancel, QPushButton#cancel_btn {background-color: #6c757d; border: 1px solid #5c636a;}
            QPushButton[text="Cancel"]:hover, QPushButton#btn_cancel:hover {background-color: #5c636a;}
        """)

    def set_dashboard_grayscale(self, enable=True):
        for btn in self.dashboard_components:
            if enable: self._apply_grayscale(btn)
            else: self._remove_grayscale(btn)

    def _apply_grayscale(self, widget):
        if widget:
            effect = QGraphicsColorizeEffect(widget)
            effect.setColor(Qt.gray) 
            effect.setStrength(1.0)  
            widget.setGraphicsEffect(effect)
            widget.setStyleSheet("opacity: 0.5;") 

    def _remove_grayscale(self, widget):
        if widget:
            widget.setGraphicsEffect(None) 
            widget.setStyleSheet("")    

    # --- FITUR BARU: STATE PERSISTENCE ---
    def save_last_state(self):
        """Menyimpan status terakhir ke file JSON"""

        sm_dur = 30.0
        if hasattr(self, 'auto_worker'):
            sm_dur = self.auto_worker.sm_duration_minutes

        state_data = {
            "system_mode": self.system_mode,
            "smart_flags": getattr(self, 'smart_active_flags', {}),
            "estop_active": getattr(self, 'physical_estop_active', False),
            "soft_emergency": getattr(self, 'soft_emergency_active', False),
            "blower_hz": self.saved_blower_hz, "sm_duration_minutes": sm_dur
        }
        try:
            with open("last_state.json", "w") as f:
                json.dump(state_data, f, indent=4)
                f.flush() 
                os.fsync(f.fileno()) 
            print("[SYSTEM] State saved successfully.")
        except Exception as e:
            print(f"[SYSTEM] Failed to save state: {e}") 

    def restore_last_state(self):
        """Mengembalikan status dari file JSON"""
        if not os.path.exists("last_state.json"):
            return  
        try:
            with open("last_state.json", "r") as f:
                data = json.load(f) 
            
            # 1. Restore Mode Global (Auto/Manual)
            last_mode = data.get("system_mode", "MANUAL")
            if last_mode == "AUTO":
                self.set_auto_mode()
            else:
                self.set_manual_mode() 
            
            # 2. Restore Smart Flags
            saved_flags = data.get("smart_flags", {})
            if hasattr(self, 'smart_active_flags'):
                self.smart_active_flags.update(saved_flags) 
            
            # 3. [PENTING] Restore Blower Hz ke AutoWorker
            saved_hz = data.get("blower_hz", 45.0)
            self.saved_blower_hz = float(saved_hz)
            if hasattr(self, 'auto_worker'):
                self.auto_worker.set_blower_setpoint(self.saved_blower_hz)
                print(f"[RESTORE] Blower Hz restored to: {self.saved_blower_hz}")
            
            saved_sm_duration = data.get("sm_duration_minutes", 30.0)
            if hasattr(self, 'auto_worker'):
                self.auto_worker.set_sm_duration_config(saved_sm_duration)
                print(f"[RESTORE] SM Duration restored to: {saved_sm_duration} min")
            
            # 4. Refresh Worker Logic
            if hasattr(self, 'auto_worker'):
                self.auto_worker.last_sent_states = {} 

        except Exception as e:
            print(f"[RESTORE] Failed to restore state: {e}")   

    def closeEvent(self, event):
        print("Shutting down system...")
        
        # 1. STOP FLAG
        if hasattr(self, 'sensor_worker'): self.sensor_worker.running = False
        if hasattr(self, 'shift_worker'): self.shift_worker.running = False
        if hasattr(self, 'auto_worker'): self.auto_worker.running = False
        if hasattr(self, 'estop_monitor'): self.estop_monitor.stop() 
        if hasattr(self, 'alarm_monitor'): self.alarm_monitor.stop()

        # 2. WAIT FOR THREADS
        if hasattr(self, 'sensor_worker'): self.sensor_worker.wait(2000)
        if hasattr(self, 'shift_worker'): self.shift_worker.wait(2000)
        if hasattr(self, 'auto_worker'): self.auto_worker.wait(2000)
        if hasattr(self, 'estop_monitor'): self.estop_monitor.wait(2000)
        if hasattr(self, 'alarm_monitor'): self.alarm_monitor.wait(2000)
        
        self.threadpool.clear()

        # 3. SIMPAN STATE
        self.save_last_state()
        
        # --- [NEW] SIMPAN TOTALIZER ---
        self.save_totalizers()
        
        # 4. KILL HARDWARE
        try:
            print("[SHUTDOWN] Killing all outputs...")
            self._worker_kill_safe(keep_alarm=False)
        except Exception as e:
            print(f"[SHUTDOWN ERR] Kill failed: {e}")

        # 5. CLOSE MODBUS
        if hasattr(self, 'modbus_client'): 
            try:
                self.modbus_client.close()
            except: pass

        print("System Safe to Close.")
        event.accept()

# =========================================================================
#  MAIN EXECUTION (MODULAR LOGIN -> DASHBOARD)
# =========================================================================

def enforce_display_resolution():
    """
    Enforces native 1280x800 resolution on Linux systems (e.g. Bodhi Linux / Mini PC)
    so that HDMI/DP output matches the native 10.1" IPS LCM screen (1280x800) automatically.
    """
    if sys.platform.startswith('linux'):
        import subprocess
        import time
        try:
            res = subprocess.run(["xrandr"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            if res.returncode == 0:
                applied = False
                for line in res.stdout.splitlines():
                    if " connected" in line:
                        port = line.split()[0]
                        subprocess.run(["xrandr", "--output", port, "--mode", "1280x800"], check=False, timeout=3)
                        print(f"[DISPLAY] Enforced 1280x800 on display port: {port}")
                        applied = True
                if applied:
                    time.sleep(0.5)
        except Exception as e:
            print(f"[DISPLAY WARN] Could not enforce display resolution via xrandr: {e}")

def main():
    enforce_display_resolution()
    try:
        sync_thread = threading.Thread(target=data_sync.start_monitoring, daemon=True)
        sync_thread.start()
        print("[SYSTEM] Background Data Sync started.")
    except Exception as e:
        print(f"[SYSTEM ERR] Failed to start Data Sync: {e}")
        
    app = QApplication(sys.argv)
    login_gui = loginWindow()
    main_system = None

    def launch_dashboard(role, username):
        nonlocal main_system
        print(f"[LAUNCHER] Login verified. Starting Main System for {username}...")
        main_system = MainSystemController(user_role=role, username=username)
        main_system.showMaximized()
        login_gui.close()

    login_gui.login_successful.connect(launch_dashboard)
    login_gui.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()