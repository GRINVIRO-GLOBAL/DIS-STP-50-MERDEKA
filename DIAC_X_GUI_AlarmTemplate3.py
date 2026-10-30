import sys
import os
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5 import uic, QtCore
from PyQt5.QtCore import pyqtSignal

# Import file details yang baru kita update
from DIAC_X_GUI_ActiveAlarmTemplate_details2 import alarmTemplateDetails

class alarmTemplate(QWidget):
    delete_signal = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            myGUI = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_AlarmTemplate.ui")
            uic.loadUi(myGUI, self)
            
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True) 
            
            # Hubungkan tombol Delete
            if hasattr(self, 'delete_btn'):
                self.delete_btn.clicked.connect(self.on_delete_clicked)
            
            # --- TAMBAHAN: Hubungkan tombol Details ---
            if hasattr(self, 'details_btn'):
                self.details_btn.clicked.connect(self.open_details_window)
            
            self.current_alarm_name = ""
            self.full_data_storage = {} # Variabel untuk menyimpan data lengkap
            
        except Exception as e:
            print(f"Error loading UI Alarm Template: {e}")

    def set_data(self, data):
        # 1. Simpan Data Lengkap untuk dikirim ke Details nanti
        self.full_data_storage = data
        self.current_alarm_name = data.get("alarmName")

        def safe_set_text(obj_name, value):
            if hasattr(self, obj_name):
                getattr(self, obj_name).setText(str(value))

        # Mapping untuk Tampilan Kecil (Card)
        safe_set_text("alarm_name",      data.get("alarmName"))
        safe_set_text("type_data",       data.get("alarmType"))
        safe_set_text("event_data",      data.get("eventName"))
        safe_set_text("instrument_data", data.get("instrumentName"))
        safe_set_text("time_data",       data.get("popUpInterval"))

    def on_delete_clicked(self):
        if self.current_alarm_name:
            self.delete_signal.emit(self.current_alarm_name, self)

    def open_details_window(self):
        """Membuka jendela details dan mengirimkan data"""
        try:
            # Buat instance jendela details
            # self.details_window disimpan di 'self' agar tidak dihapus garbage collector
            self.details_window = alarmTemplateDetails()
            
            # Masukkan data
            self.details_window.set_data(self.full_data_storage)
            
            # Tampilkan sebagai Dialog (Modal)
            self.details_window.exec_()
            
        except Exception as e:
            print(f"Gagal membuka details: {e}")

# ========================================================
# BAGIAN INI WAJIB ADA DI PALING BAWAH (LUAR CLASS)
# ========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 1. Buat Dummy Data untuk Tes
    dummy_data = {
        "alarmName": "TEST ALARM",
        "alarmType": "Warning",
        "eventName": "High Temperature",
        "instrumentName": "Boiler A",
        "popUpInterval": "10 Minutes"
    }
    
    # 2. Inisialisasi Widget
    print("Mencoba menjalankan Alarm Template...")
    window = alarmTemplate()
    
    # 3. Masukkan Data Dummy
    window.set_data(dummy_data)
    
    # 4. Tampilkan
    window.show()
    
    # 5. Eksekusi Loop
    print("Window ditampilkan. Cek taskbar jika tidak muncul.")
    sys.exit(app.exec_())