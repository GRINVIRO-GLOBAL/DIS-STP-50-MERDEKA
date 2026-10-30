# filename: custom_dialogs.py
import os
import json
import csv
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox, QDialogButtonBox, QDialog, QGraphicsColorizeEffect
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

# Import Logger
from log_manager import EventLogger, MaintenanceLogger 
from workers import CEBWorker

# --- CLASS 1: MACHINE OFF DIALOG ---
class MachineOffDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, component_name="Component"):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_Machine_off.ui")
        try:
            uic.loadUi(ui_path, self)
            if hasattr(self, "lbl_machine_name"):
                self.lbl_machine_name.setText(component_name)
            if hasattr(self, "Machine_Yes"): self.Machine_Yes.clicked.connect(self.accept)
            if hasattr(self, "Machine_No"): self.Machine_No.clicked.connect(self.reject)
        except FileNotFoundError:
            self.fallback_ui(component_name)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(f"Turn OFF: {component_name}")

    def fallback_ui(self, name):
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(f"Matikan {name}?", self))
        btns = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

# --- CLASS 2: SHIFT CONFIGURATION ---
class ShiftConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "shiftConfig2.ui")
        self.json_path = os.path.join(os.path.dirname(__file__), "data_shift_settings.json")
        try:
            uic.loadUi(ui_path, self)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            self.btn_apply.clicked.connect(self.save_settings)
            self.btn_cancel.clicked.connect(self.reject)
            
            # Programmatically add single blower options if they don't exist
            if hasattr(self, "combo_bl01"):
                items = [self.combo_bl01.itemText(i) for i in range(self.combo_bl01.count())]
                if "Blower 01A Only" not in items:
                    self.combo_bl01.addItem("Blower 01A Only")
                if "Blower 01B Only" not in items:
                    self.combo_bl01.addItem("Blower 01B Only")
                    
            self.load_settings()
        except FileNotFoundError: pass

    def save_settings(self):
        data = {
            "combo_tp01": self.combo_tp01.currentText(),
            "combo_tp02": self.combo_tp02.currentText(),
            "combo_tp03": self.combo_tp03.currentText(),
            "combo_bl01": self.combo_bl01.currentText(),
            "combo_tpin": self.comboBox.currentText(),
            "combo_sm":   self.comboBox_2.currentText(),
            "spin_siklus_tp03": self.spin_siklus_tp03.value(),
            "line_ceb": self.line_ceb.text(),
            "line_soaking" : self.line_soaking.text(),
            "line_aeration": self.line_aeration.text(),
            "line_flushing": self.line_flushing.text()
        }
        try:
            with open(self.json_path, "w") as f:
                json.dump(data, f, indent=4)
            MaintenanceLogger.log_action("Shift Configuration", "Update parameter shift & siklus", "Engineer")
            QMessageBox.information(self, "Success", "Konfigurasi Shift Berhasil Disimpan!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan: {e}")

    def load_settings(self):
        if not os.path.exists(self.json_path): return
        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)
            
            if "combo_tp01" in data: self.combo_tp01.setCurrentText(data["combo_tp01"])
            if "combo_tp02" in data: self.combo_tp02.setCurrentText(data["combo_tp02"])
            if "combo_tp03" in data: self.combo_tp03.setCurrentText(data["combo_tp03"])
            if "combo_bl01" in data: self.combo_bl01.setCurrentText(data["combo_bl01"])
            if "combo_tpin" in data: self.comboBox.setCurrentText(data["combo_tpin"])
            if "combo_sm" in data:   self.comboBox_2.setCurrentText(data["combo_sm"])
            if "spin_siklus_tp03" in data: self.spin_siklus_tp03.setValue(int(data["spin_siklus_tp03"]))
            if "line_ceb" in data: self.line_ceb.setText(data["line_ceb"])
            if "line_soaking" in data: self.line_soaking.setText(data["line_soaking"])
            if "line_aeration" in data: self.line_aeration.setText(data["line_aeration"])
            if "line_flushing" in data: self.line_flushing.setText(data["line_flushing"])
        except Exception as e: print(f"Error loading settings: {e}")
        
# --- CLASS 3: TRANSMITTER CONFIGURATION ---
class TransmitterConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "TransmitterConfig.ui")
        self.csv_path = os.path.join(os.path.dirname(__file__), "data_alarm_settings.csv")
        try:
            uic.loadUi(ui_path, self)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            
            self.comboBox.clear()
            allowed_items = [
                "FT-101 (Recirculation Flow)",
                "FT-102 (MBR Permeate Flow)",
                "FT-103 (MBR Backwash Flow)",
                "PT-101 (MBR Pressure)",
                "LT-101 (MBR Tank Level)",
                "DO-101 (Dissolved Oxygen)"
            ]
            self.comboBox.addItems(allowed_items)

            self.sensor_map = {
                "FT-101 (Recirculation Flow)": "FT_101",
                "FT-102 (MBR Permeate Flow)": "FT_102",
                "FT-103 (MBR Backwash Flow)": "FT_103",
                "PT-101 (MBR Pressure)": "PT_101",
                "LT-101 (MBR Tank Level)": "LT_101",
                "DO-101 (Dissolved Oxygen)": "DO_101"
            }
            
            self.create_btn.clicked.connect(self.save_to_csv)
            self.cancel_btn.clicked.connect(self.reject)
            self.comboBox.currentIndexChanged.connect(self.on_component_changed)
            self.on_component_changed() 
            
        except FileNotFoundError: print("UI TransmitterConfig.ui not found")

    def on_component_changed(self):
        comp_name = self.comboBox.currentText()
        unit_text = "m"
        if "PT" in comp_name: unit_text = "bar"
        elif "FT" in comp_name: unit_text = "m³/h"
        elif "LT" in comp_name: unit_text = "m"
        elif "DO" in comp_name: unit_text = "mg/L"
        
        if hasattr(self, 'unit_hh'): self.unit_hh.setText(unit_text)
        if hasattr(self, 'unit_hi'): self.unit_hi.setText(unit_text)
        if hasattr(self, 'unit_lo'): self.unit_lo.setText(unit_text)
        if hasattr(self, 'unit_ll'): self.unit_ll.setText(unit_text)

        # Enable all 4 fields for STP 50 since each has HH, H, L, LL
        self.enable_field(self.line_hh, True)
        self.enable_field(self.line_hi, True)
        self.enable_field(self.line_lo, True)
        self.enable_field(self.line_ll, True)
            
        self.load_existing_values()

    def enable_field(self, line_edit, enabled):
        line_edit.setEnabled(enabled)
        if not enabled:
            line_edit.clear()
            line_edit.setStyleSheet("background-color: #f0f0f0; color: #a0a0a0;")
            line_edit.setPlaceholderText("Locked")
        else:
            line_edit.setStyleSheet("background-color: white; color: black;")
            line_edit.setPlaceholderText("Value")

    def load_existing_values(self):
        component_name = self.comboBox.currentText()
        sensor_key = self.sensor_map.get(component_name, "")
        
        if self.line_hh.isEnabled(): self.line_hh.clear()
        if self.line_hi.isEnabled(): self.line_hi.clear()
        if self.line_lo.isEnabled(): self.line_lo.clear()
        if self.line_ll.isEnabled(): self.line_ll.clear()

        if not os.path.exists(self.csv_path): return
        
        try:
            with open(self.csv_path, 'r') as f:
                reader = csv.DictReader(f, skipinitialspace=True)
                for row in reader:
                    if row.get('instrumentName') == sensor_key or row.get('alarmTripCondition') == sensor_key:
                        alarm_name = row.get('alarmName', "")
                        val = row.get('alarmTripValue', "")
                        if " HH" in alarm_name and self.line_hh.isEnabled(): self.line_hh.setText(str(val))
                        elif " HI" in alarm_name and self.line_hi.isEnabled(): self.line_hi.setText(str(val))
                        elif " LO" in alarm_name and self.line_lo.isEnabled(): self.line_lo.setText(str(val))
                        elif " LL" in alarm_name and self.line_ll.isEnabled(): self.line_ll.setText(str(val))
        except Exception as e: print(f"CSV Load Error: {e}")

    def save_to_csv(self):
        component_name = self.comboBox.currentText()
        sensor_key = self.sensor_map.get(component_name, "")
        
        txt_hh = self.line_hh.text().strip()
        txt_hi = self.line_hi.text().strip()
        txt_lo = self.line_lo.text().strip()
        txt_ll = self.line_ll.text().strip()
        
        email_recipient = ""
        custom_msg = ""
        if hasattr(self, "line_email"): email_recipient = self.line_email.text().strip()
        if hasattr(self, "line_msg"): custom_msg = self.line_msg.text().strip()

        new_rows = []
        def add_alarm_row(suffix, val_text, combo_box_widget, operator_char, default_msg):
            if not val_text: return
            try:
                val = float(val_text)
                level_str = combo_box_widget.currentText()
                alarm_type = "Critical" if level_str == "Fault" else "Warning"
                alarm_name = f"{sensor_key} {suffix}"
                new_rows.append({
                    "alarmName": alarm_name,
                    "alarmType": alarm_type,
                    "instrumentName": sensor_key,
                    "alarmTripCondition": sensor_key,
                    "alarmTripOperator": operator_char,
                    "alarmTripValue": val,
                    "alarmMessage": f"{default_msg} ({val})",
                    "emailRecipient": email_recipient,
                    "customEmailMessage": custom_msg
                })
            except ValueError: pass

        if self.line_hh.isEnabled(): add_alarm_row("HH", txt_hh, self.combo_hh, ">", "High High Level Detected")
        if self.line_hi.isEnabled(): add_alarm_row("HI", txt_hi, self.combo_hi, ">", "High Level Detected")
        if self.line_lo.isEnabled(): add_alarm_row("LO", txt_lo, self.combo_lo, "<", "Low Level Detected")
        if self.line_ll.isEnabled(): add_alarm_row("LL", txt_ll, self.combo_ll, "<", "Low Low Level Detected")

        all_rows = []
        headers = ["alarmName", "alarmType", "instrumentName", "alarmTripCondition", "alarmTripOperator", "alarmTripValue", "alarmMessage", "emailRecipient", "customEmailMessage"]
        
        if os.path.exists(self.csv_path):
            try:
                with open(self.csv_path, 'r') as f:
                    reader = csv.DictReader(f, skipinitialspace=True)
                    for row in reader:
                        if row.get("instrumentName") != sensor_key and row.get("alarmTripCondition") != sensor_key:
                            all_rows.append(row)
            except Exception: pass

        all_rows.extend(new_rows)

        try:
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(all_rows)
            
            MaintenanceLogger.log_action("Transmitter Config", f"Update Config {sensor_key}", "Engineer")
            QMessageBox.information(self, "Success", f"Konfigurasi {component_name} berhasil disimpan!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal menulis CSV: {e}")

# --- CLASS 4: CEB MAINTENANCE (UPDATED FOR 4-PHASE SEQUENCE) ---
class CEBMaintenanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_controller = parent
        
        # [CRITICAL FIX 1] Set Flag & Paksa Stop MBR saat Dialog Dibuka
        self.main_controller.ceb_is_active = True
        
        # Panggil fungsi stop di AutoPilot secara langsung agar pompa mati detik ini juga
        if hasattr(self.main_controller, 'auto_worker'):
            self.main_controller.auto_worker.stop_mbr_sequence_outputs()
            print("[CEB] MBR Sequence Force Stopped.")

        # 1. Load UI Baru
        ui_path = os.path.join(os.path.dirname(__file__), "CEB_Backwash.ui")
        try:
            uic.loadUi(ui_path, self)
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "File CEB_Backwash.ui tidak ditemukan!")
            return

        # 2. Init Worker
        self.worker = CEBWorker(self.main_controller)
        self.worker.countdown_signal.connect(self.update_timer)
        self.worker.status_signal.connect(self.update_status_label)
        self.worker.phase_finished_signal.connect(self.on_phase_finished)
        self.worker.error_signal.connect(self.on_worker_error)

        # 3. Setup Halaman Awal
        self.stackedWidget.setCurrentIndex(0) 
        self.lcdNumber.display("0")
        
        # Gunakan visual_placeholder untuk teks status
        if hasattr(self, 'visual_placeholder'):
            self.visual_placeholder.setText("Ready to Start CEB")

        # 4. Mapping Tombol Navigasi (FIXED BUTTON NAMES)
        self.buttonBox.accepted.connect(self.start_phase_1)
        self.buttonBox.rejected.connect(self.reject)

        # Halaman 1: Phase 1 -> Lanjut ke Soaking (pushButton_4)
        page_1 = self.findChild(QtWidgets.QWidget, "Sensor_Calibration_1")
        if page_1:
            self.btn_goto_soak = page_1.findChild(QtWidgets.QPushButton, "pushButton_4") 
            if self.btn_goto_soak:
                self.btn_goto_soak.clicked.connect(self.start_phase_2)
                self.btn_goto_soak.setEnabled(False) 

        # Halaman 2: Phase 2 -> Lanjut ke Aerasi (pushButton_3)
        page_2 = self.findChild(QtWidgets.QWidget, "Sensor_Calibration_1.5")
        if page_2:
            self.btn_goto_air = page_2.findChild(QtWidgets.QPushButton, "pushButton_3") 
            if self.btn_goto_air:
                self.btn_goto_air.clicked.connect(self.start_phase_3)
                self.btn_goto_air.setEnabled(False)

        # Halaman 3: Phase 3 -> Lanjut ke Flushing (pushButton_2)
        page_3 = self.findChild(QtWidgets.QWidget, "Sensor_Calibration_2")
        if page_3:
            self.btn_goto_flush = page_3.findChild(QtWidgets.QPushButton, "pushButton_2")
            if self.btn_goto_flush:
                self.btn_goto_flush.clicked.connect(self.start_phase_4)
                self.btn_goto_flush.setEnabled(False)

        # Halaman 4: Phase 4 -> Selesai (pushButton)
        page_4 = self.findChild(QtWidgets.QWidget, "Sensor_Calibration_3")
        if page_4:
            self.btn_finish = page_4.findChild(QtWidgets.QPushButton, "pushButton")
            if self.btn_finish:
                self.btn_finish.clicked.connect(self.finish_sequence)
                self.btn_finish.setEnabled(False)

        # Halaman 5: Done -> Tutup
        page_done = self.findChild(QtWidgets.QWidget, "Sensor_Calibration_Done")
        if page_done:
            self.btn_close = page_done.findChild(QtWidgets.QPushButton, "done_AE102_Calibration")
            if self.btn_close:
                self.btn_close.clicked.connect(self.accept)

        self.reset_visuals()

    # --- PHASE LOGIC ---
    def start_phase_1(self):
        """Mulai Fase 1: Backwash + Dosing"""
        self.stackedWidget.setCurrentIndex(1)
        self.run_worker_phase(1)
        self.update_visual_icons(tp04=True, dosing=True, blower=True) 

    def start_phase_2(self):
        """Mulai Fase 2: Soaking"""
        self.stackedWidget.setCurrentIndex(2)
        self.run_worker_phase(2)
        self.update_visual_icons(tp04=False, dosing=False, blower=False)

    def start_phase_3(self):
        """Mulai Fase 3: Aerasi"""
        self.stackedWidget.setCurrentIndex(3)
        self.run_worker_phase(3)
        self.update_visual_icons(tp04=False, dosing=False, blower=True)

    def start_phase_4(self):
        """Mulai Fase 4: Flushing"""
        self.stackedWidget.setCurrentIndex(4)
        self.run_worker_phase(4)
        self.update_visual_icons(tp04=True, dosing=False, blower=False)

    def finish_sequence(self):
        self.stackedWidget.setCurrentIndex(5) # Done Page
        self.reset_visuals()
        if hasattr(self.main_controller, 'logger'):
            self.main_controller.logger.add_log("System", "CEB Sequence", "Completed Successfully")

    def run_worker_phase(self, phase_id):
        self.worker.set_phase(phase_id)
        self.worker.start()

    # --- SIGNALS ---
    def update_timer(self, val):
        self.lcdNumber.display(str(val))

    def update_status_label(self, text):
        if hasattr(self, 'visual_placeholder'):
            self.visual_placeholder.setText(text)

    def on_phase_finished(self):
        current_idx = self.stackedWidget.currentIndex()
        # self.lbl_t4.setText("Phase Complete.")
        
        # Enable tombol Next sesuai halaman aktif
        if current_idx == 1 and hasattr(self, 'btn_goto_soak'):
            self.btn_goto_soak.setEnabled(True)
            self.btn_goto_soak.setText("Lanjut ke Soaking >>")
        elif current_idx == 2 and hasattr(self, 'btn_goto_air'):
            self.btn_goto_air.setEnabled(True)
            self.btn_goto_air.setText("Lanjut ke Aerasi >>")
        elif current_idx == 3 and hasattr(self, 'btn_goto_flush'):
            self.btn_goto_flush.setEnabled(True)
            self.btn_goto_flush.setText("Lanjut ke Flushing >>")
        elif current_idx == 4 and hasattr(self, 'btn_finish'):
            self.btn_finish.setEnabled(True)
            self.btn_finish.setText("Selesai >>")

    def on_worker_error(self, msg):
        QMessageBox.critical(self, "CEB Error", f"Terjadi kesalahan: {msg}")
        self.reset_visuals()
        self.reject()
        
    # --- HANDLING CLOSE / REJECT ---
    def closeEvent(self, event):
        self.cleanup_ceb()
        event.accept()

    def reject(self):
        self.cleanup_ceb()
        super().reject()

    def cleanup_ceb(self):
        # [CRITICAL FIX] Kembalikan Flag saat dialog ditutup
        if self.worker.isRunning():
            self.worker.stop()
            self.worker._emergency_stop_all()
        
        self.main_controller.ceb_is_active = False
        print("[CEB] Maintenance Mode END. Flag Reset.")

    # --- VISUAL EFFECTS ---
    def update_visual_icons(self, tp04=False, dosing=False, blower=False):
        # Gunakan atribut UI yang diload dari .ui
        if hasattr(self, 'TP_04'): self.set_icon_color(self.TP_04, tp04)
        # btn_DP_01 adalah QToolButton khusus di UI
        if hasattr(self, 'btn_DP_01'): self.set_icon_color(self.btn_DP_01, dosing)
        if hasattr(self, 'blower_A'): self.set_icon_color(self.blower_A, blower)

    def set_icon_color(self, widget, is_active):
        if is_active:
            # Hapus efek grayscale (jadi warna asli)
            widget.setGraphicsEffect(None)
        else:
            # Beri efek grayscale/abu-abu
            effect = QGraphicsColorizeEffect(widget)
            effect.setColor(QColor(100, 100, 100)) # Abu-abu
            effect.setStrength(1.0)
            widget.setGraphicsEffect(effect)

    def reset_visuals(self):
        self.update_visual_icons(False, False, False)

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.stop()
            self.worker._emergency_stop_all()
        event.accept()

# --- CLASS 5: FLOW SENSOR CONFIG ---
class FlowSensorConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Konfigurasi Luas Penampang Pipa (Flow Area)")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(400, 250)
        self.json_path = os.path.join(os.path.dirname(__file__), "data_flow_settings.json")
        
        layout = QtWidgets.QVBoxLayout(self)
        info_label = QtWidgets.QLabel("Masukkan Luas Penampang (Area) untuk perhitungan Debit.\nRumus: Debit = Raw Value (Kecepatan) x Area")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #555; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(info_label)

        form_layout = QtWidgets.QFormLayout()
        self.input_area_ft101 = QtWidgets.QLineEdit()
        self.input_area_ft101.setPlaceholderText("Contoh: 0.5")
        self.input_area_ft102 = QtWidgets.QLineEdit()
        self.input_area_ft102.setPlaceholderText("Contoh: 1.2")
        self.input_area_ft103 = QtWidgets.QLineEdit()
        self.input_area_ft103.setPlaceholderText("Contoh: 0.8")

        form_layout.addRow("Luas FT-101 (Inlet):", self.input_area_ft101)
        form_layout.addRow("Luas FT-102 (MBR):", self.input_area_ft102)
        form_layout.addRow("Luas FT-103 (Backwash):", self.input_area_ft103)
        layout.addLayout(form_layout)
        
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.save_settings)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.load_settings()

    def load_settings(self):
        defaults = {"area_ft101": 1.0, "area_ft102": 1.0, "area_ft103": 1.0}
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r") as f:
                    data = json.load(f)
                    defaults.update(data)
            except Exception as e: print(f"Error loading flow settings: {e}")
        self.input_area_ft101.setText(str(defaults["area_ft101"]))
        self.input_area_ft102.setText(str(defaults["area_ft102"]))
        self.input_area_ft103.setText(str(defaults["area_ft103"]))

    def save_settings(self):
        try:
            val1 = float(self.input_area_ft101.text() or 1.0)
            val2 = float(self.input_area_ft102.text() or 1.0)
            val3 = float(self.input_area_ft103.text() or 1.0)
            data = {"area_ft101": val1, "area_ft102": val2, "area_ft103": val3}
            with open(self.json_path, "w") as f: json.dump(data, f, indent=4)
            MaintenanceLogger.log_action("Flow Config", "Update Area Pipa Flowmeter", "Engineer")
            QMessageBox.information(self, "Sukses", "Data Luas Penampang Berhasil Disimpan!")
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Masukkan angka desimal yang valid (gunakan titik '.' sebagai koma).")