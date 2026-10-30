from PyQt5.QtWidgets import (QDialog, QGridLayout, QPushButton, QLineEdit, 
                             QVBoxLayout, QWidget, QMessageBox)
from PyQt5.QtCore import Qt, QSize

class NumpadDialog(QDialog):
    def __init__(self, parent=None, initial_value="", title="Input Number"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                border: 2px solid #0d6efd;
                border-radius: 10px;
            }
            QLineEdit {
                font-size: 28px;
                padding: 10px;
                color: #333;
                background-color: #f0f0f0;
                border: 2px solid #555;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #444;
                color: white;
                font-size: 20px;
                font-weight: bold;
                border-radius: 5px;
                border: 1px solid #555;
                min-width: 60px;
                min-height: 60px;
            }
            QPushButton:pressed {
                background-color: #0d6efd;
            }
            QPushButton#ActionBtn {
                background-color: #666;
            }
            QPushButton#ConfirmBtn {
                background-color: #198754; 
            }
            QPushButton#CancelBtn {
                background-color: #dc3545;
            }
        """)

        layout = QVBoxLayout(self)
        
        # Display Area
        self.display = QLineEdit()
        self.display.setAlignment(Qt.AlignRight)
        self.display.setText(str(initial_value))
        self.display.setReadOnly(True) 
        layout.addWidget(self.display)

        # Grid Tombol
        grid = QGridLayout()
        layout.addLayout(grid)

        # Definisi Tombol
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('0', 3, 0), ('.', 3, 1), ('C', 3, 2),
        ]

        for text, row, col in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(lambda ch, t=text: self.on_digit_clicked(t))
            grid.addWidget(btn, row, col)

        # Tombol Aksi
        self.btn_backspace = QPushButton("⌫")
        self.btn_backspace.setObjectName("ActionBtn")
        self.btn_backspace.clicked.connect(self.backspace)
        grid.addWidget(self.btn_backspace, 0, 3)

        self.btn_sign = QPushButton("+/-")
        self.btn_sign.setObjectName("ActionBtn")
        self.btn_sign.clicked.connect(self.toggle_sign)
        grid.addWidget(self.btn_sign, 1, 3)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("CancelBtn")
        self.btn_cancel.clicked.connect(self.reject)
        grid.addWidget(self.btn_cancel, 2, 3)

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("ConfirmBtn")
        self.btn_ok.setMinimumHeight(125)
        self.btn_ok.clicked.connect(self.accept_value)
        grid.addWidget(self.btn_ok, 3, 3)

        self.final_value = 0.0 # Variable untuk menyimpan hasil akhir

    def on_digit_clicked(self, char):
        current_text = self.display.text()
        
        if char == 'C':
            self.display.clear()
        elif char == '.':
            if '.' not in current_text:
                if current_text == "": self.display.setText("0.")
                else: self.display.setText(current_text + ".")
        else:
            if current_text == "0": 
                self.display.setText(char)
            else:
                self.display.setText(current_text + char)

    def backspace(self):
        text = self.display.text()
        self.display.setText(text[:-1])

    def toggle_sign(self):
        text = self.display.text()
        if not text: return
        if text.startswith("-"):
            self.display.setText(text[1:])
        else:
            self.display.setText("-" + text)

    def accept_value(self):
        try:
            val_str = self.display.text()
            if not val_str or val_str == "." or val_str == "-": 
                self.final_value = 0
            elif "." in val_str:
                self.final_value = float(val_str)
            else:
                self.final_value = int(val_str)
        except ValueError:
            self.final_value = 0
        super().accept()
        
    def get_value(self):
        return self.final_value