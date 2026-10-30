import sys
import os
import csv
from PyQt5.QtWidgets import (QApplication, QDialog, QComboBox)
from PyQt5 import uic
from DIAC_X_GUI_NewRecipient import newRecipient

class alarmCreationWindow(QDialog):
    def __init__(self, equipment_list=None, sensor_value_list=None, parent=None):
        super().__init__(parent)

        try:
            myGUI = os.path.join(os.path.dirname(__file__),"DIAC_X_GUI_AlarmCreationForm.ui")
            uic.loadUi(myGUI, self)
        except:
            print("No file found")

        self.equipment_list = equipment_list if equipment_list else []
        self.sensor_value_list = sensor_value_list if sensor_value_list else []

        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("DIAC-X Alarm Creation Form")
        self.create_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.add_recipient_btn.clicked.connect(self.openNewRecipientForm)
        
        # 1. SETUP INSTRUMENT NAME
        self.instrument_name_comboBox.clear()
        if self.equipment_list:
            self.instrument_name_comboBox.addItems(self.equipment_list)
        else:
            self.instrument_name_comboBox.addItem("No Equipment Defined")

        # 2. SETUP ALARM TRIP (SENSOR)
        if hasattr(self, 'alarm_trip_data'):
            if isinstance(self.alarm_trip_data, QComboBox):
                self.alarm_trip_data.clear()
                if self.sensor_value_list:
                    self.alarm_trip_data.addItems(self.sensor_value_list)
                else:
                    self.alarm_trip_data.addItem("No Live Sensor")
        
        # 3. LOAD EMAIL FROM CSV
        self.load_emails_from_csv()

    # ================= LOGIKA CSV EMAIL (BARU) =================
    def load_emails_from_csv(self):
        csv_file = "data_emails.csv"
        full_path = os.path.join(os.path.dirname(__file__), csv_file)
        
        self.recipient_email.clear()
        
        # Creating new csv file if it does not exist
        if not os.path.exists(full_path):
            # Optional : default email if creating new file
            default_emails = ["grinV.01@gmail.com"]
            self.recipient_email.addItems(default_emails)
            self.save_email_to_csv("grinV.01@gmail.com", mode='w')
            return

        try:
            with open(full_path, mode='r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        email = row[0]
                        self.recipient_email.addItem(email)
        except Exception as e:
            print(f"Failed to load email: {e}")

    def save_email_to_csv(self, new_email, mode='a'):
        csv_file = "data_emails.csv"
        full_path = os.path.join(os.path.dirname(__file__), csv_file)
        
        try:
            with open(full_path, mode=mode, newline='') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow([new_email])
        except Exception as e:
            print(f"Gagal menyimpan email: {e}")
    # ===========================================================

    def openNewRecipientForm(self):
        form = newRecipient(self)
        result = form.exec()
        if result == QDialog.Accepted:
            new_recipient = form.submitData()
            self.addNewRecipient(new_recipient)

    def addNewRecipient(self, data):
        # Cek apakah email sudah ada di ComboBox (untuk menghindari duplikat visual)
        if self.recipient_email.findText(data) == -1:
            # 1. Tambahkan ke UI
            self.recipient_email.addItem(data)
            self.recipient_email.setCurrentText(data) # Otomatis pilih yang baru
            
            # 2. Simpan ke CSV (Permanen)
            self.save_email_to_csv(data)

    def sentData(self):
        if hasattr(self, 'alarm_trip_data') and isinstance(self.alarm_trip_data, QComboBox):
            trip_condition_val = self.alarm_trip_data.currentText()
        elif hasattr(self, 'alarm_trip_data'):
            trip_condition_val = self.alarm_trip_data.text()
        else:
            trip_condition_val = ""

        data = {
            "alarmName" : self.alarm_name_data.text(),
            "alarmType" : self.alarm_type_comboBox.currentText(),
            "instrumentName" : self.instrument_name_comboBox.currentText(), 
            "eventName" : self.event_name_data.text(),
            "popUpInterval" : f"{self.popUp_interval_spinBox.value()} {self.popUp_interval_comboBox.currentText()}",
            "alarmTripCondition" : trip_condition_val, 
            "alarmTripOperator" : self.alarm_trip_comboBox.currentText(),
            "alarmTripValue" : self.alarm_trip_compare.value(),
            "recipientEmail" : self.recipient_email.currentText(),
            "alarmMessage" : self.message_to_recipient_data.toPlainText()
        }
        return data 

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = alarmCreationWindow()
    window.show()
    sys.exit(app.exec_())