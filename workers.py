# filename: workers.py
import os
import json
import re
import time
from log_manager import MaintenanceLogger 
from PyQt5.QtCore import QThread, pyqtSignal, QRunnable, pyqtSlot, QObject

class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

class FunctionWorker(QRunnable):
    """
    Worker generic untuk menjalankan fungsi berat di background.
    """
    def __init__(self, func, *args, **kwargs):
        super(FunctionWorker, self).__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
            print(f"Worker Error: {e}")

# --- CLASS WORKER KHUSUS CEB (Maintenance Sequence) ---
class CEBWorker(QThread):
    countdown_signal = pyqtSignal(int)      # Update LCD Number
    phase_finished_signal = pyqtSignal()    # Sinyal fase selesai
    status_signal = pyqtSignal(str)         # Update Label Status
    error_signal = pyqtSignal(str)

    def __init__(self, main_controller):
        super().__init__()
        self.main = main_controller
        self.running = False
        self.current_phase = 0 
        
        # [SAFETY] Waktu tunggu valve terbuka (detik)
        self.VALVE_DELAY = 15  
        
        # Konfigurasi Durasi (Default 60 detik/1 menit)
        # Konfigurasi Durasi STP 50 (Dosing: 120s, Soaking: 1800s, Aerasi: 600s, Backwash: 60s)
        self.durations = {
            'phase1_ceb': 120,     # 2 Menit (Dosing)
            'phase2_soak': 1800,   # 30 Menit (Soaking)
            'phase3_air': 600,     # 10 Menit (Aeration)
            'phase4_flush': 60     # 1 Menit (Backwash)
        }
        self.load_settings()

    def load_settings(self):
        """Load durasi dari JSON (jika ada custom setting)"""
        json_path = os.path.join(os.path.dirname(__file__), "data_shift_settings.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    # Mapping setting JSON ke variable
                    self.durations['phase1_ceb'] = self.parse_seconds(data.get('line_ceb', '120'))
                    self.durations['phase2_soak'] = self.parse_seconds(data.get('line_soaking', '1800'))
                    self.durations['phase3_air'] = self.parse_seconds(data.get('line_aeration', '600'))
                    self.durations['phase4_flush'] = self.parse_seconds(data.get('line_flushing', '60'))
            except Exception as e:
                print(f"[CEB CONFIG ERR] {e}")

    def parse_seconds(self, val_str):
        """
        [FIX] Membaca durasi lebih pintar. 
        "10 menit" -> 600 detik
        "60" -> 60 detik
        """
        try:
            s = str(val_str).lower().strip()
            # Ambil angka
            num_match = re.search(r'\d+', s)
            if not num_match: return 60 # Default aman
            
            num = int(num_match.group())
            
            # Cek satuan
            if "menit" in s or "minute" in s:
                return num * 60
            elif "jam" in s or "hour" in s:
                return num * 3600 
            return num
        except: return 60

    def set_phase(self, phase_id):
        self.current_phase = phase_id

    def get_active_blower_key(self):
        """Helper untuk mencari Blower mana yang harus aktif (Shift A/B)"""
        suffix_bl = self.main.get_active_shift_suffix('BL_01')
        return f"BL_01{suffix_bl}"
    
    def get_target_hz(self): 
        if hasattr(self.main, 'saved_blower_hz'):
            return float(self.main.saved_blower_hz)
        return 44.0 

    def run(self):
        self.running = True
        
        try:
            # =========================================================
            # PHASE 1: CEB DOSING (TP-03 BW Pump + DP-01 Dosing, Blower OFF)
            # =========================================================
            if self.current_phase == 1:
                duration = self.durations['phase1_ceb']
                bl_key = self.get_active_blower_key()
                
                self.status_signal.emit(f"Phase 1: Opening Valve AV-102 ({self.VALVE_DELAY}s)...")
                
                # 1. Pastikan Blower Mati saat Dosing (sesuai spesifikasi STP 50)
                self.main.direct_write_hardware(bl_key, False, freq=0.0)
                
                # 2. Buka Valve Backwash (AV-102)
                self.main.direct_write_hardware('ACT_02', True)
                
                # 3. Delay Safety Valve
                if not self._safe_delay(self.VALVE_DELAY): return

                # 4. Start Pompa Backwash & Dosing
                self.status_signal.emit("Phase 1: CEB Dosing Running (Backwash Pump + Dosing Pump)")
                self.main.direct_write_hardware('TP_04', True, freq=26.0)
                self.main.direct_write_hardware('DP_01', True)
                
                # 5. Timer Jalan
                self.run_timer(duration)
                
                # 6. Cleanup Phase 1 (Matikan Pompa & Dosing)
                self.main.direct_write_hardware('TP_04', False, freq=0)
                self.main.direct_write_hardware('DP_01', False)

            # =========================================================
            # PHASE 2: SOAKING (PERENDAMAN) - ALL OFF
            # =========================================================
            elif self.current_phase == 2:
                duration = self.durations['phase2_soak']
                
                self.status_signal.emit("Phase 2: Soaking (Valve Stays Open)")
                
                # 1. Nyalakan Flag agar AutoPilotWorker tahu Blower harus mati
                self.main.ceb_blower_force_off = True 
                # 2. Matikan Blower secara fisik untuk memastikan
                bl_key = self.get_active_blower_key()
                self.main.direct_write_hardware(bl_key, False, freq=0.0)

                # Pastikan Valve masih terbuka (Redundancy)
                self.main.direct_write_hardware('ACT_02', True) 
                # Pastikan pompa mati
                self.main.direct_write_hardware('TP_04', False)
                self.main.direct_write_hardware('DP_01', False)
                
                self.run_timer(duration)

                # 4. Matikan Flag setelah Soaking selesai
                self.main.ceb_blower_force_off = False

            # =========================================================
            # PHASE 3: AERATION (BLOWER ONLY)
            # =========================================================
            elif self.current_phase == 3:
                duration = self.durations['phase3_air']
                bl_key = self.get_active_blower_key()
                target_hz = self.get_target_hz() 
                
                self.status_signal.emit("Phase 3: Aeration Agitation")
                
                # Valve tetap terbuka untuk venting/safety
                self.main.direct_write_hardware('ACT_02', True)
                
                # Blower ON
                self.main.direct_write_hardware(bl_key, True, freq=target_hz)
                
                self.run_timer(duration)

            # =========================================================
            # PHASE 4: BACKWASH (NO CHEMICAL)
            # =========================================================
            elif self.current_phase == 4:
                duration = self.durations['phase4_flush']
                
                self.status_signal.emit("Phase 4: Flushing (Backwash without Chemical)")
                
                # Valve Tetap Buka
                self.main.direct_write_hardware('ACT_02', True) 
                # Start Pompa TP-04 (Tanpa Dosing)
                self.main.direct_write_hardware('TP_04', True, freq=26.0)
                
                self.run_timer(duration)
                
                # === FINAL CLEANUP (SEMUA MATI) ===
                self.status_signal.emit("Finishing...")
                self.main.direct_write_hardware('TP_04', False, freq=0)
                self.main.direct_write_hardware('DP_01', False)
                self.msleep(2000) # Tunggu tekanan turun
                self.main.direct_write_hardware('ACT_02', False)

                try:
                    MaintenanceLogger.log_action(
                        item="CEB System",
                        action="Chemical Enhanced Backwash Sequence Completed Successfully",
                        user=self.main.current_user, # Mencatat siapa user yang login saat ini
                        status="Done"
                    )
                    print("[CEB WORKER] Log saved successfully.")
                except Exception as log_err:
                    print(f"[CEB WORKER] Failed to save log: {log_err}")

        except Exception as e:
            self.error_signal.emit(str(e))
            self._emergency_stop_all()
        
        # Selesai Phase
        self.phase_finished_signal.emit()
        self.running = False

    def _safe_delay(self, seconds):
        """Helper untuk delay dengan check stop signal"""
        for i in range(seconds):
            if not self.running: 
                self._emergency_stop_all()
                return False
            self.msleep(1000)
        return True

    def _stop_pumps_and_valve(self):
        """Urutan mematikan yang aman: Pompa mati -> Jeda -> Valve tutup"""
        self.main.direct_write_hardware('TP_04', False, freq=0)
        self.main.direct_write_hardware('DP_01', False)
        self.msleep(1000) # Tunggu tekanan turun dikit
        self.main.direct_write_hardware('ACT_02', False)

    def _emergency_stop_all(self):
        """Matikan paksa semua komponen terkait CEB"""
        self.main.ceb_blower_force_off = False  # <--- TAMBAHKAN INI
        self.main.direct_write_hardware('TP_04', False)
        self.main.direct_write_hardware('DP_01', False)
        self.main.direct_write_hardware('ACT_02', False)
        # Matikan blower juga untuk safety
        bl_key = self.get_active_blower_key()
        self.main.direct_write_hardware(bl_key, False, freq=0)

    def run_timer(self, seconds):
        """Helper countdown timer"""
        for i in range(seconds, -1, -1):
            if not self.running: break # Safety Stop
            self.countdown_signal.emit(i)
            self.msleep(1000)
            
    def stop(self):
        self.running = False
        self.wait()