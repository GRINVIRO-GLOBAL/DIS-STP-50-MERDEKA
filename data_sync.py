import time
import json
import csv
import requests
import os
import threading
import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- KONFIGURASI API ---
API_URL_SENSOR    = "https://api-ffi.grinviro-global.com/api/v1/iot/plc/webhook"
API_URL_EQUIPMENT = "https://api-ffi.grinviro-global.com/api/v1/iot/equipment/status/batch/legacy"
API_URL_ALARM     = "https://api-ffi.grinviro-global.com/api/v1/iot/alarms"

BASE_DIR = "/home/diac-x/FFI" 
BATCH_INTERVAL = 1 
BATCH_COUNTER_FILE = "batch_counter.txt" 

# KATEGORI 1: DATA BATCH
BATCH_FILES = {"data_runtime.json"}
BATCH_FOLDERS = {"datalog_sensors"}

# KATEGORI 2: DATA REAL-TIME
IMMEDIATE_FILES = {
    "data_shift_settings.json", "last_state.json", "runtime_shift.json"
}
# File & Folder Alarm
ALARM_SETTINGS_FILE = "data_alarm_settings.csv"
ALARM_LOG_FOLDER = "datalog_alarms"

# CONFIG PAYLOAD
PLANT_TYPE = "STP"

# --- FUNGSI BANTUAN BATCH ID ---
def get_next_batch_id():
    current_id = 1
    if os.path.exists(BATCH_COUNTER_FILE):
        try:
            with open(BATCH_COUNTER_FILE, 'r') as f:
                val = f.read().strip()
                if val.isdigit(): current_id = int(val) + 1
        except: pass
    try:
        with open(BATCH_COUNTER_FILE, 'w') as f: f.write(str(current_id))
    except: pass
    return current_id

class MultiTargetHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_pointers = {}
        self.csv_headers = {}
        self.pending_batch_files = set()
        self.lock = threading.Lock() 
        self.alarm_config_cache = {}
        
        settings_path = os.path.join(BASE_DIR, ALARM_SETTINGS_FILE)
        if os.path.exists(settings_path):
             self.load_alarm_settings(settings_path)
             self.file_pointers[os.path.abspath(settings_path)] = os.path.getsize(settings_path)

    def load_alarm_settings(self, path):
        """Cache isi data_alarm_settings.csv untuk lookup cepat"""
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                new_cache = {}
                for row in reader:
                    name = row.get('alarmName')
                    if name: new_cache[name] = row
                
                with self.lock:
                    self.alarm_config_cache = new_cache
                print(f"[System] Alarm settings reloaded: {len(new_cache)} rules.")
        except Exception as e:
            print(f"Gagal load alarm settings: {e}")

    def on_modified(self, event):
        if event.is_directory: return
        path = os.path.abspath(event.src_path)
        filename = os.path.basename(path)
        
        if filename == ALARM_SETTINGS_FILE:
            self.load_alarm_settings(path)
            return

        is_batch = False
        if filename in BATCH_FILES: is_batch = True
        else:
            for folder in BATCH_FOLDERS:
                if folder in path and filename.endswith(".csv"):
                    is_batch = True; break
        
        if is_batch:
            with self.lock: self.pending_batch_files.add(path)
            return

        if ALARM_LOG_FOLDER in path or (filename.endswith(".csv") and "202" in filename): 
            self.send_alarm_data(path)

    # --- PROCESSORS ---

    def process_queue(self):
        with self.lock:
            files = list(self.pending_batch_files)
            self.pending_batch_files.clear()

        if not files: return
        
        unique_paths = set(files)
        curr_id = get_next_batch_id()

        for path in unique_paths:
            fname = os.path.basename(path)
            if fname == "data_runtime.json":
                self.send_equipment_data(path)
            elif "datalog_sensors" in path:
                self.send_sensor_data(path, curr_id)

    # --- SENDERS ---

    def send_sensor_data(self, path, batch_id):
        try:
            new_rows = self.read_csv_tail(path)
            if not new_rows: return
            
            # Ambil Snapshot Terakhir
            last_row = new_rows[-1]
            ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            sensors = {}
            for k, v in last_row.items():
                if "date" in k.lower() or "time" in k.lower(): continue 
                
                is_skip = False
                for skip in ["Voltage", "Current", "Ampere", "Volt", "Hz", "BL_"]: 
                    if skip in k: is_skip = True; break
                if is_skip: continue

                try: sensors[k] = float(v)
                except: sensors[k] = v

            payload = {
                "plant_type": PLANT_TYPE,
                "sensors": sensors,
                "batch_id": batch_id,
                "timestamp": ts
            }
            self.post_to_api(API_URL_SENSOR, payload, f"SENSOR ({os.path.basename(path)})")
        except Exception as e: print(f"Err Sensor: {e}")

    def send_equipment_data(self, path):
        try:
            with open(path, 'r') as f: data = json.load(f)
            self.post_to_api(API_URL_EQUIPMENT, data, "EQUIPMENT")
        except Exception as e: print(f"Err Equip: {e}")

    def send_alarm_data(self, path):
        """LOGIKA KHUSUS ALARM: Join Log + Settings"""
        try:
            new_rows = self.read_csv_tail(path)
            if not new_rows: return

            filename = os.path.basename(path)
            date_part = filename.replace(".csv", "") 
            
            try:
                datetime.datetime.strptime(date_part, "%Y-%m-%d")
            except ValueError:
                date_part = datetime.datetime.utcnow().strftime("%Y-%m-%d")

            for row in new_rows:
                event_type = row.get('Event', '')
                if event_type != 'ALARM_TRIGGERED':
                    continue

                alarm_key = row.get('Alarm Name')
                message_log = row.get('Message', '')
                setting = self.alarm_config_cache.get(alarm_key, {})
                
                sensor_code = setting.get('instrumentName', alarm_key) 
                operator = setting.get('alarmTripOperator', '')
                atype = "general"
                if ">" in operator or "HH" in alarm_key or "HI" in alarm_key:
                    atype = "high"
                elif "<" in operator or "LL" in alarm_key or "LO" in alarm_key:
                    atype = "low"
                
                severity = setting.get('alarmType', 'warning').lower()
                
                is_trip = "TRIP" in alarm_key.upper() or "TRIP" in message_log.upper()
                if is_trip:
                    severity = "critical" 
                    atype = "trip"

                msg = row.get('Message', setting.get('alarmMessage', ''))
                try: curr_val = float(row.get('Value', 0))
                except: curr_val = 0.0
                
                try: threshold = float(setting.get('alarmTripValue', 0))
                except: threshold = 0.0
                
                time_part = row.get('Timestamp', '00:00:00')
                try:
                    dt_obj = datetime.datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
                    triggered_at = dt_obj.strftime('%Y-%m-%dT%H:%M:%SZ')
                except:
                    triggered_at = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

                payload = {
                    "sensor_code": sensor_code,
                    "alarm_type": atype,
                    "severity": severity,
                    "message": msg,
                    "current_value": curr_val,
                    "threshold_value": threshold,
                    "triggered_at": triggered_at
                }
                
                self.post_to_api(API_URL_ALARM, payload, f"ALARM ({alarm_key})")

        except Exception as e: print(f"Err Alarm Logic: {e}")

    # --- HELPERS ---

    def read_csv_tail(self, path):
        header = self.get_header(path)
        if not header: return []

        last_pos = self.file_pointers.get(path, 0)
        curr_size = os.path.getsize(path)
        if curr_size < last_pos: last_pos = 0

        rows = []
        with open(path, 'r') as f:
            if path not in self.file_pointers:
                f.seek(0, os.SEEK_END)
                self.file_pointers[path] = f.tell()
                return []

            f.seek(last_pos)
            lines = f.readlines()
            self.file_pointers[path] = f.tell()

            for line in lines:
                if not line.strip(): continue 
                try:
                    parts = list(csv.reader([line]))
                    if not parts: continue
                    vals = parts[0]
                    if len(vals) == len(header):
                        rows.append(dict(zip(header, vals)))
                except: pass
        return rows

    def get_header(self, path):
        if path in self.csv_headers: return self.csv_headers[path]
        try:
            with open(path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader)
                self.csv_headers[path] = header
                return header
        except: return None

    def post_to_api(self, url, payload, label):
        try:
            print(f"\n--- [SEND -> {label}] ---")
            print(json.dumps(payload, indent=2, default=str))
            
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            if response.status_code in [200, 201]:
                print(f"   [SUCCESS] Code: {response.status_code}")
            else:
                print(f"   [FAIL] {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Fail POST: {e}")

# --- RUNNER ---
def start_monitoring():
    observer = Observer()
    handler = MultiTargetHandler()
    path = os.path.abspath(BASE_DIR)
    
    if not os.path.exists(path):
        print(f"ERROR: {path} tidak ditemukan!")
        return

    observer.schedule(handler, path, recursive=True)
    observer.start()
    print(f"[Sync Started] Mode: Alarm Intelligence Active")
    
    try:
        while True:
            time.sleep(BATCH_INTERVAL)
            handler.process_queue()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_monitoring()