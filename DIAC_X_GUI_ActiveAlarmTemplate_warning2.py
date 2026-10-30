import sys
import os
from PyQt5.QtWidgets import QWidget
from PyQt5 import uic, QtCore

class activeAlarmTemplate_warning(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            myGUI = os.path.join(os.path.dirname(__file__), "DIAC_X_GUI_ActiveAlarmTemplate_failure.ui")
            uic.loadUi(myGUI, self)
            
            # --- FIX 1: Agar Background Abu-abu Muncul ---
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            
        except Exception as e:
            print(f"Error loading UI Failure: {e}")

    def set_data(self, timestamp, alarm_name, alarm_type, instrument, message):
        """
        Mengisi data ke widget UI.
        Menerima 5 parameter terpisah.
        """
        try:
            # 1. Pecah Timestamp (Date & Time)
            if timestamp and " " in timestamp:
                date_part, time_part = timestamp.split(" ", 1)
            else:
                date_part = timestamp
                time_part = "-"

            # 2. Set DATE & TIME
            if hasattr(self, 'date_data'): self.date_data.setText(str(date_part))
            if hasattr(self, 'time_data'): self.time_data.setText(str(time_part))
                
            # 3. Set ALARM NAME (Judul Alarm)
            # Pastikan di Qt Designer nama objectnya 'alarm_name'
            if hasattr(self, 'alarm_name'): 
                self.alarm_name.setText(str(alarm_name))
            
            # 4. Set STATUS DATA (Diisi dengan Tipe Alarm: Warning/Failure)
            # Sesuai request Anda
            if hasattr(self, 'status_data'): 
                self.status_data.setText(str(alarm_type))

            # 5. Set INSTRUMENT & MESSAGE (Opsional)
            # Jika Anda punya label untuk instrumen atau pesan detail, set disini
            if hasattr(self, 'instrument_data'): 
                self.instrument_data.setText(str(instrument))
                
            # Jika Anda ingin menampilkan pesan detail di tooltip atau label lain
            self.setToolTip(f"{message}") 

        except Exception as e:
            print(f"Gagal set data ke widget: {e}")