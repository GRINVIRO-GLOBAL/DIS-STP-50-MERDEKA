import os
from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QDialog, QTableWidgetItem, QHeaderView

class ActivityLogDialog(QDialog):
    def __init__(self, log_manager, parent=None):
        super().__init__(parent)
        self.log_manager = log_manager # Simpan referensi ke LogManager
        
        # 1. Load UI File
        # Pastikan file .ui ada di folder yang sama
        ui_path = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_ActivityLog.ui")
        try:
            uic.loadUi(ui_path, self)
        except Exception as e:
            print(f"Error loading UI: {e}")
            return

        # 2. Setup Tabel
        # PENTING: Cek nama object tabel di QtDesigner. 
        # Di final19.py biasanya namanya 'tableWidget' atau 'eventLog_content'
        # Disini saya asumsikan namanya 'tableWidget'. Ganti jika berbeda.
        if hasattr(self, 'tableWidget'):
            self.setup_table()
            self.load_data()
        else:
            print("Warning: Widget tabel tidak ditemukan di .ui (Cek ObjectName di QtDesigner)")

    def setup_table(self):
        """Mengatur header tabel agar sesuai dengan format LogManager"""
        # Format Data kita: [Timestamp, User, Action, Details]
        headers = ["Waktu", "User", "Aktivitas", "Detail"]
        
        self.tableWidget.setColumnCount(len(headers))
        self.tableWidget.setHorizontalHeaderLabels(headers)
        
        # Agar kolom terakhir memenuhi ruang kosong
        header = self.tableWidget.horizontalHeader()
        header.setSectionResizeMode(len(headers)-1, QHeaderView.Stretch)

    def load_data(self):
        """Mengambil data dari LogManager dan memasukkannya ke tabel UI"""
        # Minta 100 log terakhir hari ini dari LogManager
        logs = self.log_manager.load_last_logs(limit=100)
        
        self.tableWidget.setRowCount(0) # Bersihkan tabel lama
        
        # Masukkan data (Looping Efisien)
        for row_idx, row_data in enumerate(logs):
            self.tableWidget.insertRow(row_idx)
            for col_idx, item_text in enumerate(row_data):
                item = QTableWidgetItem(str(item_text))
                self.tableWidget.setItem(row_idx, col_idx, item)