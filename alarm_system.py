import sys
import os
import csv
import time
import datetime
from PyQt5.QtCore import QThread, pyqtSignal

try:
    from global_data import GlobalData
except ImportError:
    class GlobalData:
        sensor_data = {}

class AlarmMonitor(QThread):
    # Signal
    alarm_triggered_signal = pyqtSignal(dict)       # Untuk Toast Notif (Delayed)
    alarm_resolved_signal = pyqtSignal(dict)        # Untuk Toast Resolve
    alarm_value_update_signal = pyqtSignal(dict)    # Untuk update angka di kartu (jika aktif)
    auto_maintenance_signal = pyqtSignal(str, str)  # Untuk Log Maintenance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        
        # State Management
        self.active_alarm_names = set()     # Alarm yang SUDAH TAMPIL (Toast sudah muncul)
        self.pending_alarm_times = {}       # Alarm yang SEDANG MENUNGGU Timer (Belum Toast)
        
        self.current_sensor_data = {}
        self.alarm_configs = []
        self.alarm_map = {} 
        
        self.reload_csv_settings()

    def reload_csv_settings(self):
        """Membaca ulang konfigurasi alarm dari CSV"""
        self.alarm_configs = []
        self.alarm_map = {}
        csv_path = os.path.join(os.path.dirname(__file__), "data_alarm_settings.csv")
        
        if os.path.exists(csv_path):
            try:
                with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames:
                        reader.fieldnames = [n.strip() for n in reader.fieldnames]
                    for row in reader:
                        try:
                            cfg = {
                                "alarmName": row.get("alarmName", "").strip(),
                                "instrumentName": row.get("instrumentName", "").strip(),
                                "operator": row.get("alarmTripOperator", ">").strip(),
                                "tripValue": float(row.get("alarmTripValue", 0.0)),
                                "alarmType": row.get("alarmType", "Warning").strip(),
                                "alarmMessage": row.get("alarmMessage", "").strip(),
                                "emailRecipient": row.get("emailRecipient", ""),
                                "customEmailMessage": row.get("customEmailMessage", "")
                            }
                            self.alarm_configs.append(cfg)
                            self.alarm_map[cfg["alarmName"]] = cfg["instrumentName"]
                        except ValueError:
                            continue
            except Exception: pass

    def update_data(self, sensor_values):
        self.current_sensor_data = sensor_values

    def run(self):
        while self.running:
            try:
                current_time = time.time()
                
                # Set untuk melacak sensor mana yang sedang error saat ini (detik ini)
                currently_in_error_state = set()

                # --- 1. EVALUASI SETIAP SENSOR ---
                for cfg in self.alarm_configs:
                    instr_name = cfg["instrumentName"]
                    current_val = self.current_sensor_data.get(instr_name)
                    name = cfg["alarmName"]

                    if current_val is None: continue 

                    # Cek Threshold
                    is_triggered = False
                    op = cfg["operator"]
                    limit = cfg["tripValue"]

                    if "FT" in instr_name or "Flow" in instr_name:
                        if op == ">" or op == ">=":
                            limit = limit * 1.20 
                    
                    if op == ">" and current_val > limit: is_triggered = True
                    elif op == "<" and current_val < limit: is_triggered = True
                    elif op == ">=" and current_val >= limit: is_triggered = True
                    elif op == "<=" and current_val <= limit: is_triggered = True

                    if is_triggered:
                        currently_in_error_state.add(name)
                        
                        # --- LOGIKA TIMER (DELAY) ---
                        
                        # A. Jika alarm SUDAH aktif (sudah Toast sebelumnya), update value saja
                        if name in self.active_alarm_names:
                            self.alarm_value_update_signal.emit({
                                "alarmName": name, "value": current_val,
                                "message": cfg["alarmMessage"]
                            })
                            
                        # B. Jika belum aktif, cek apakah baru mulai error?
                        else:
                            if name not in self.pending_alarm_times:
                                self.pending_alarm_times[name] = current_time 
                            
                            # Hitung durasi error
                            start_t = self.pending_alarm_times[name]
                            elapsed = current_time - start_t
                            
                            # Tentukan Batas Waktu Berdasarkan Tipe Sensor
                            limit_seconds = 0.5 
                            check_str = name.upper()
                            
                            # [ATURAN WAKTU ANDA]
                            if "LT" in check_str or "LEVEL" in check_str:
                                limit_seconds = 5.0
                            elif "FT" in check_str or "FLOW" in check_str:
                                limit_seconds = 20.0
                            
                            # Jika Timer Tembus -> FIRE TOAST & LOG
                            if elapsed >= limit_seconds:
                                self.active_alarm_names.add(name)
                                del self.pending_alarm_times[name]
                                now_str = datetime.datetime.now().strftime("%H:%M:%S")
                                
                                # 1. Trigger TOAST Notif (Delayed)
                                self.alarm_triggered_signal.emit({
                                    "alarmName": name,
                                    "alarmType": cfg["alarmType"],
                                    "message": cfg["alarmMessage"],
                                    "value": current_val,
                                    "timestamp": now_str,
                                    "emailTo": cfg.get("emailRecipient", ""),
                                    "emailMsg": cfg.get("customEmailMessage", "")
                                })
                                
                                # 2. Trigger MAINTENANCE Log
                                log_msg = f"Auto-Detected: {cfg['alarmMessage']} (> {int(limit_seconds)}s). Val: {current_val:.2f}"
                                self.auto_maintenance_signal.emit(name, log_msg)

                # --- 2. RESOLVE LOGIC (RESET) ---
                
                # A. Cek Alarm yang sedang Pending (Belum Toast) -> Jika sembuh, reset timer
                for name in list(self.pending_alarm_times.keys()):
                    if name not in currently_in_error_state:
                        # Sensor kembali normal sebelum waktu delay habis
                        del self.pending_alarm_times[name]
                
                # B. Cek Alarm yang SUDAH Active (Sudah Toast) -> Jika sembuh, kirim Resolve
                for name in list(self.active_alarm_names):
                    if name not in currently_in_error_state:
                        self.active_alarm_names.remove(name)
                        
                        instr_name = self.alarm_map.get(name, "")
                        val = self.current_sensor_data.get(instr_name, 0.0)
                            
                        self.alarm_resolved_signal.emit({"alarmName": name, "value": val})
            
            except Exception: pass
            time.sleep(0.2)

    def stop(self):
        self.running = False
        self.wait()