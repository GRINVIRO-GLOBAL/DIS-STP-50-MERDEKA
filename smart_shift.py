# filename: smart_shift.py
import os
import json
import time
import re
import datetime 
from PyQt5.QtCore import QThread, pyqtSignal, QMutexLocker

class SmartShiftWorker(QThread):
    shift_changed = pyqtSignal(str, str)
    
    # Signal untuk UI Update
    lock_component = pyqtSignal(str)   
    unlock_component = pyqtSignal(str) 
    
    # Signal Critical Failure (jika kedua pompa A & B mati)
    critical_failure_detected = pyqtSignal(bool) 

    def __init__(self, main_controller):
        super().__init__()
        self.main = main_controller
        self.running = True
        self.is_auto = False
        self.trip_states = {} 
        self.critical_states = {}

        # Konfigurasi Group
        # SM TETAP ADA DI SINI agar Trip-nya bisa dipantau
        self.groups = {
            'TP_IN': {'A': 'TP_IN_A', 'B': 'TP_IN_B', 'TripA': 'TRIP_IN_A', 'TripB': 'TRIP_IN_B', 'Active': 'A', 'Limit': 14400},
            'TP_01': {'A': 'TP_01A', 'B': 'TP_01B', 'TripA': 'TRIP_TP_01A', 'TripB': 'TRIP_TP_01B', 'Active': 'A', 'Limit': 14400},
            'TP_02': {'A': 'TP_02A', 'B': 'TP_02B', 'TripA': 'TRIP_TP_02A', 'TripB': 'TRIP_TP_02B', 'Active': 'A', 'Limit': 14400},
            'TP_03': {'A': 'TP_03A', 'B': 'TP_03B', 'TripA': 'TRIP_TP_03A', 'TripB': 'TRIP_TP_03B', 'Active': 'A', 'Limit': 14400},
            'BL_01': {'A': 'BL_01A', 'B': 'BL_01B', 'TripA': 'TRIP_BL_01A', 'TripB': 'TRIP_BL_01B', 'Active': 'A', 'Limit': 14400},
            'SM':    {'A': 'SM_01', 'B': 'SM_02',   'TripA': 'TRIP_SM_01', 'TripB': 'TRIP_SM_02',  'Active': 'A', 'Limit': 14400}
        }
        self.load_shift_settings()

    def set_auto_status(self, active: bool):
        self.is_auto = active

    def run(self):
        print("[SHIFT] Worker Started (Failover & Emergency Monitoring Active)")
        
        while self.running:
            try:
                # Hitung detik sejak tengah malam
                now = datetime.datetime.now()
                seconds_since_midnight = (now.hour * 3600) + (now.minute * 60) + now.second
                
                for name, grp in self.groups.items():
                    self.process_pump_schedule(name, grp, seconds_today=seconds_since_midnight)

            except Exception as e:
                print(f"[SHIFT ERR] {e}")
            
            self.msleep(1000) 

    # ------------------------------------------------------------------
    # 1. LOGIC POMPA BIASA (FAILOVER SYSTEM)
    #    Jika A Trip -> Paksa ke B (Switching ditunda sampai A sehat)
    # ------------------------------------------------------------------
    def process_pump_schedule(self, name, grp, seconds_today):
        if not self.is_auto: return
        
        cache = self.main.sensor_data_cache
        
        # --- [PERBAIKAN 1: Tipe Data Kebal] ---
        # Ambil raw data
        raw_trip_a = cache.get(grp['TripA'], 0)
        raw_trip_b = cache.get(grp['TripB'], 0)
        
        # Konversi ke Boolean murni apapun format aslinya
        trip_a = str(raw_trip_a).strip().lower() in ['1', 'true', 'on']
        trip_b = str(raw_trip_b).strip().lower() in ['1', 'true', 'on']
        # ---------------------------------------

        key_a = grp['A']
        key_b = grp['B']

        # A. Update Visual Lock (Merah/Normal)
        self.handle_lock_logic(key_a, trip_a)
        self.handle_lock_logic(key_b, trip_b)

        # B. CRITICAL CHECK: Jika DUA-DUANYA Trip -> Critical Failure
        if trip_a and trip_b:
            if not self.critical_states.get(name, False):
                self.critical_failure_detected.emit(True)
                self.critical_states[name] = True
            
            # Matikan Output secara paksa lewat Main App
            self.main.direct_write_hardware(key_a, False)
            self.main.direct_write_hardware(key_b, False)
            return 
            
        else:
            # --- [PERBAIKAN 2: Blok else membungkus seluruh sisa logika] ---
            # Reset status critical jika salah satu sembuh
            if self.critical_states.get(name, False):
                self.critical_failure_detected.emit(False)
                self.critical_states[name] = False

            # [BLOWER KHUSUS]: Switching Blower diatur oleh akumulasi running hours di AutoPilotWorker
            if name == 'BL_01':
                return

            # C. LOGIC FAILOVER (Auto Switch saat Trip)
            raw_setting = grp.get('RawSetting', '').lower()
            if "only" in raw_setting:
                if "01a" in raw_setting or "a only" in raw_setting:
                    target_suffix = 'A'
                elif "01b" in raw_setting or "b only" in raw_setting:
                    target_suffix = 'B'
                else:
                    target_suffix = 'A'
            else:
                interval = grp.get('Limit', 14400)
                if interval <= 0: interval = 14400
                slot_index = int(seconds_today / interval)
                
                # Target Normal Sesuai Jam (Genap=A, Ganjil=B)
                target_suffix = 'A' if (slot_index % 2 == 0) else 'B'

                # OVERRIDE: Jika trip terjadi di target, switch ke backup
                if target_suffix == 'A' and trip_a:
                    target_suffix = 'B'
                    print(f"[FAILOVER] {name}: A is Trip! Forcing shift to B.")
                elif target_suffix == 'B' and trip_b:
                    target_suffix = 'A'
                    print(f"[FAILOVER] {name}: B is Trip! Forcing shift to A.")

            # D. EKSEKUSI (Hanya jika target berbeda dari status aktif sekarang)
            if grp['Active'] != target_suffix:
                print(f"[SCHEDULE] {name}: Switching {grp['Active']} -> {target_suffix}")
                
                # Matikan pompa lama
                old_key = grp[grp['Active']]
                self.main.direct_write_hardware(old_key, False)
                
                grp['Active'] = target_suffix
                self.shift_changed.emit(name, target_suffix)

    def handle_lock_logic(self, component_key, trip_status):
        """Helper untuk mendeteksi perubahan status trip"""
        current_state = (trip_status == 1)
        previous_state = self.trip_states.get(component_key, False)
        
        if current_state != previous_state:
            # Status Berubah!
            if current_state: 
                self.lock_component.emit(component_key) # Lock (Merah)
            else: 
                self.unlock_component.emit(component_key) # Unlock (Normal)
                
            self.trip_states[component_key] = current_state

    def load_shift_settings(self):
        json_path = os.path.join(os.path.dirname(__file__), "data_shift_settings.json")
        if not os.path.exists(json_path): return
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                mapping = {
                    "combo_tp01": "TP_01", "combo_tp02": "TP_02", 
                    "combo_tp03": "TP_03", "combo_bl01": "BL_01", 
                    "combo_tpin": "TP_IN", "combo_sm": "SM"
                }
                for json_key, group_name in mapping.items():
                    val_str = data.get(json_key, "4 jam")
                    if group_name in self.groups:
                        self.groups[group_name]['RawSetting'] = val_str
                    seconds = self.parse_duration(val_str)
                    if group_name in self.groups: self.groups[group_name]['Limit'] = seconds
        except: pass

    def parse_duration(self, duration_str):
        try:
            s = str(duration_str).lower().strip()
            num_match = re.search(r'\d+', s)
            if not num_match: return 14400
            val = int(num_match.group())
            if "detik" in s or "second" in s: return val
            elif "menit" in s or "minute" in s: return val * 60
            else: return val * 3600
        except: return 14400

    def stop(self):
        self.running = False
        self.wait()