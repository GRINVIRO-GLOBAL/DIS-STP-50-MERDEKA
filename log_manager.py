# filename: log_manager.py
import os
import csv
import time
import datetime

# --- CLASS UTAMA (PARENT) ---
class LogManager:
    def __init__(self, base_dir="datalog"):
        self.base_dir = os.path.abspath(base_dir)
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)

    # [FIX] Method ini dikembalikan agar tidak Error saat Start/Stop mesin
    def add_log(self, user, action, details):
        """Mencatat aktivitas operasional (Start/Stop Mesin, Login, dll)"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            month_folder = now.strftime("%Y-%m")
            full_folder_path = os.path.join(self.base_dir, month_folder)
            os.makedirs(full_folder_path, exist_ok=True)
            
            filename = now.strftime("%Y-%m-%d") + ".csv"
            target_file = os.path.join(full_folder_path, filename)
            
            # Cek apakah file baru (untuk tulis header)
            file_exists = os.path.isfile(target_file) and os.path.getsize(target_file) > 0
            row_data = [timestamp, user, action, details]

            with open(target_file, mode='a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "User", "Action", "Details"])
                writer.writerow(row_data)
        except Exception as e:
            print(f"Error writing activity log: {e}")

# --- SENSOR LOGGER (Untuk Data Page) ---
class SensorLogger(LogManager):
    def __init__(self, base_dir, sensor_headers):
        super().__init__(base_dir)
        self.headers = ["Timestamp"] + sensor_headers
        self.last_logged_time = 0

    def log_data(self, data_values): 
        current_time = time.time()
        if current_time - self.last_logged_time < 1.0:
            return
        
        # Update waktu terakhir log
        self.last_logged_time = current_time

        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            month_folder = now.strftime("%Y-%m")
            full_folder_path = os.path.join(self.base_dir, month_folder)
            os.makedirs(full_folder_path, exist_ok=True)
            
            filename = now.strftime("%Y-%m-%d") + ".csv"
            target_file = os.path.join(full_folder_path, filename)
            
            file_exists = os.path.isfile(target_file)
            row_data = [timestamp] + data_values

            with open(target_file, mode='a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(self.headers)
                writer.writerow(row_data)
            return True
        except Exception as e:
            print(f"Error sensor log: {e}")
            return False

# --- EVENT LOGGER (Untuk Alarm Page) ---
class EventLogger:
    @staticmethod
    def get_filepath():
        base_dir = os.path.join(os.path.dirname(__file__), "datalog_alarms")
        now = datetime.datetime.now()
        month_folder = now.strftime("%Y-%m")
        full_folder_path = os.path.join(base_dir, month_folder)
        os.makedirs(full_folder_path, exist_ok=True)
        return os.path.join(full_folder_path, now.strftime("%Y-%m-%d") + ".csv")

    @staticmethod
    def log_event(event_type, alarm_name, message, value="-", user="SYSTEM"):
        """
        [UPDATED] Sekarang menerima parameter 'user'.
        """
        filepath = EventLogger.get_filepath()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # [UPDATE] Menambahkan Header "User" agar sama dengan Maintenance
        headers = ["Timestamp", "Event", "Alarm Name", "Message", "Value", "User"]
        row = [timestamp, event_type, alarm_name, message, str(value), user]
        
        try:
            file_exists = os.path.exists(filepath)
            with open(filepath, mode='a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists: writer.writerow(headers)
                writer.writerow(row)
        except Exception as e: 
            print(f"[EventLogger] Error: {e}")

    @staticmethod
    def read_new_logs(last_position=0):
        filepath = EventLogger.get_filepath()
        if not os.path.exists(filepath): 
            return [], 0
        
        new_logs = []
        current_pos = last_position

        try:
            with open(filepath, mode='r') as f:
                f.seek(last_position)
                
                if last_position == 0:
                    header = f.readline() 
                    current_pos = f.tell()

                reader = csv.reader(f)
                for row in reader:
                    if row:
                        # [UPDATE] Handle format lama (5 kolom) vs baru (6 kolom)
                        user_val = row[5] if len(row) > 5 else "SYSTEM"
                        
                        if len(row) >= 5:
                            log_dict = {
                                "Timestamp": row[0],
                                "Event": row[1],
                                "Alarm Name": row[2],
                                "Message": row[3],
                                "Value": row[4],
                                "User": user_val # Tambahkan ke dict UI
                            }
                            new_logs.append(log_dict)
                
                current_pos = f.tell()

        except Exception as e: 
            print(f"Error reading log: {e}")
            
        return new_logs, current_pos

class MaintenanceLogger:
    @staticmethod
    def get_filepath():
        base_dir = os.path.join(os.path.dirname(__file__), "datalog_maintenance")
        now = datetime.datetime.now()
        month_folder = now.strftime("%Y-%m")
        full_folder_path = os.path.join(base_dir, month_folder)
        os.makedirs(full_folder_path, exist_ok=True)
        filename = now.strftime("%Y-%m-%d") + ".csv"
        return os.path.join(full_folder_path, filename)
    
    @staticmethod
    def update_log_status(csv_index, new_status, user_who_updated="Engineer"):
        """
        [FIXED] Menambahkan parameter user_who_updated agar sesuai panggilan di main_app.
        """
        filepath = MaintenanceLogger.get_filepath()
        if not os.path.exists(filepath): return

        fieldnames = ["Time", "Item", "Action", "User", "Status"]

        try:
            rows = []
            with open(filepath, mode='r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if 0 <= csv_index < len(rows):
                # Update status
                rows[csv_index]["Status"] = new_status
                # [FIXED] Sekarang variabel ini dikenali karena ada di parameter
                rows[csv_index]["User"] = user_who_updated 
                
                cleaned_rows = []
                for row in rows:
                    clean_row = {key: row.get(key, "") for key in fieldnames}
                    cleaned_rows.append(clean_row)
                
                with open(filepath, mode='w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(cleaned_rows)
                    
                print(f"[MAINTENANCE] Row {csv_index} updated to {new_status} by {user_who_updated}")
            else:
                print(f"[ERR] Index {csv_index} out of range")

        except Exception as e:
            print(f"Gagal update status: {e}")
    
    @staticmethod
    def update_log_action(csv_index, new_action_text, user_who_updated="Engineer"):
        """
        [FIXED] Menambahkan parameter user_who_updated juga disini.
        """
        filepath = MaintenanceLogger.get_filepath()
        if not os.path.exists(filepath): return False

        fieldnames = ["Time", "Item", "Action", "User", "Status"]

        try:
            rows = []
            with open(filepath, mode='r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if 0 <= csv_index < len(rows):
                rows[csv_index]["Action"] = new_action_text
                # [FIXED] Update user yang mengedit deskripsi
                rows[csv_index]["User"] = user_who_updated 

                cleaned_rows = [{k: row.get(k, "") for k in fieldnames} for row in rows]
                
                with open(filepath, mode='w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(cleaned_rows)
                
                print(f"[MAINTENANCE] Row {csv_index} updated desc by {user_who_updated}")
                return True
            else:
                return False

        except Exception as e:
            print(f"Gagal update action: {e}")
            return False

    # ... (Method log_action dan read_logs biarkan tetap sama) ...
    @staticmethod
    def log_action(item, action, user="Engineer", status="Done"):
        filepath = MaintenanceLogger.get_filepath()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        headers = ["Time", "Item", "Action", "User", "Status"]
        row = [timestamp, item, action, user, status]
        try:
            file_exists = os.path.exists(filepath)
            with open(filepath, mode='a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists: writer.writerow(headers)
                writer.writerow(row)
        except Exception: pass

    @staticmethod
    def read_logs():
        filepath = MaintenanceLogger.get_filepath()
        if not os.path.exists(filepath): return []
        logs = []
        try:
            with open(filepath, mode='r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    logs.append({
                        "Date": row.get("Time", ""), 
                        "Item": row.get("Item", ""),
                        "Action": row.get("Action", ""),
                        "User": row.get("User", ""),
                        "Status": row.get("Status", "Done") 
                    })
        except Exception: pass
        return logs

class TotalizerLogger:
    @staticmethod
    def get_filepath():
        # Menyimpan file di folder khusus agar rapi
        base_dir = os.path.join(os.path.dirname(__file__), "datalog_totalizer")
        if not os.path.exists(base_dir):
            os.makedirs(base_dir, exist_ok=True)
        # File history tunggal (bukan per bulan) agar mudah ditampilkan di tabel
        return os.path.join(base_dir, "totalizer_history.csv")

    @staticmethod
    def log_daily(date_str, ft101, ft102, ft103):
        """
        Mencatat data totalizer harian ke CSV.
        Dipanggil saat pergantian hari (00:00).
        """
        filepath = TotalizerLogger.get_filepath()
        headers = ["Date", "FT_101", "FT_102", "FT_103"]
        
        # Pastikan format angka 2 desimal
        row = [
            date_str, 
            f"{float(ft101):.2f}", 
            f"{float(ft102):.2f}", 
            f"{float(ft103):.2f}"
        ]
        
        try:
            file_exists = os.path.exists(filepath)
            with open(filepath, mode='a', newline='') as f:
                writer = csv.writer(f)
                # Tulis Header jika file baru dibuat
                if not file_exists:
                    writer.writerow(headers)
                writer.writerow(row)
            print(f"[Totalizer] History logged for {date_str}")
            return True
        except Exception as e:
            print(f"[Totalizer] Save Error: {e}")
            return False

    @staticmethod
    def read_history():
        """
        Membaca seluruh history untuk ditampilkan di Tabel UI.
        Mengembalikan list of rows (sudah dibalik urutannya: terbaru di atas).
        """
        filepath = TotalizerLogger.get_filepath()
        if not os.path.exists(filepath): 
            return []
        
        data_rows = []
        try:
            with open(filepath, mode='r') as f:
                reader = csv.reader(f)
                all_rows = list(reader)
                
                # Cek apakah baris pertama adalah Header, jika ya hapus
                if all_rows and "Date" in all_rows[0][0]:
                    all_rows.pop(0)
                
                # Balik urutan agar tanggal terbaru muncul di baris paling atas tabel
                for row in reversed(all_rows):
                    if len(row) >= 4: # Pastikan data tidak korup
                        data_rows.append(row)
                        
        except Exception as e:
            print(f"[Totalizer] Read Error: {e}")
            
        return data_rows