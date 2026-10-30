import os
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QDialog 
from PyQt5.QtCore import Qt

# --- 1. CACHING UI CLASS (Hanya Load 1x dari Disk) ---
# Ini teknik paling efisien resource. File .ui diparse jadi Class Python di memori.
BASE_DIR = os.path.dirname(__file__)
MACHINE_UI_PATH = os.path.join(BASE_DIR, "DIAC_X_GUI_Machine.ui")
VFD_UI_PATH = os.path.join(BASE_DIR, "DIAC_X_GUI_VFD.ui")

# Load definition once
try:
    MachineForm, MachineBase = uic.loadUiType(MACHINE_UI_PATH)
    VFDForm, VFDBase = uic.loadUiType(VFD_UI_PATH)
except FileNotFoundError:
    print("CRITICAL: File .ui tidak ditemukan! Pastikan file ada di folder.")
    # Fallback dummy classes agar tidak crash saat import
    MachineForm, MachineBase = object, QtWidgets.QDialog
    VFDForm, VFDBase = object, QtWidgets.QDialog

# --- 2. OOP CLASS DEFINITION ---

class BaseControlDialog(QtWidgets.QDialog):
    """Parent class untuk logic umum (menghilangkan tanda tanya, style, dll)"""
    def __init__(self, parent=None, title="Confirmation"):
        super().__init__(parent)
        # Hapus tanda tanya (?) di header window
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(title)

class MachineDialog(BaseControlDialog, MachineForm):
    """Class khusus untuk Dialog Mesin (ON/OFF saja)"""
    def __init__(self, parent=None, component_name="Component"):
        # Init Base (QDialog) dan Form UI
        BaseControlDialog.__init__(self, parent, title=f"Control: {component_name}")
        self.setupUi(self) # Setup UI dari cache memori

        # Koneksi Tombol (Sesuai nama object di QtDesigner)
        self.Machine_Yes.clicked.connect(self.accept)
        self.Machine_No.clicked.connect(self.reject)

class VFDDialog(BaseControlDialog, VFDForm):
    """Class khusus untuk Dialog VFD (Ada setting Frekuensi)"""
    def __init__(self, parent=None, component_name="VFD Component", current_freq=0.0):
        BaseControlDialog.__init__(self, parent, title=f"Setting: {component_name}")
        self.setupUi(self)
        
        # Setup Spinbox
        if hasattr(self, "doubleSpinBox"):
            self.doubleSpinBox.setValue(float(current_freq))
            # Logic tambahan: Batasan Min/Max
            self.doubleSpinBox.setMinimum(0.0)
            self.doubleSpinBox.setMaximum(50.0)

        # Koneksi Tombol
        self.VFD_OK.clicked.connect(self.accept)
        self.VFD_cancel.clicked.connect(self.reject)
        
        for val in [10, 20, 30, 50]:
            btn_name = f"set_{val}" 
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name) 
                btn.clicked.connect(lambda _, v=val: self.doubleSpinBox.setValue(float(v)))

    def get_frequency(self):
        """Method getter untuk mengambil nilai frekuensi bersih"""
        if hasattr(self, "doubleSpinBox"):
            return self.doubleSpinBox.value()
        return 0.0

class SMConfigDialog(QDialog):
    def __init__(self, parent=None, current_duration=30.0):
        super().__init__(parent)
        self.setWindowTitle("Set SM Duration")
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setFixedSize(350, 200)

        # Apply Stylesheet (Mirip gaya MachineOnDialog)
        self.setStyleSheet("""
            QDialog { background-color: #052460; border: 2px solid #555; }
            QLabel { font-size: 14px; font-weight: bold; color: white; }
            QDoubleSpinBox { 
                font-size: 16px; padding: 5px; border: 1px solid #aaa; border-radius: 4px;
            }
            QPushButton {
                font-size: 12px; font-weight: bold; padding: 8px; border-radius: 5px;
            }
            QPushButton#btn_save { background-color: #28a745; color: white; }
            QPushButton#btn_cancel { background-color: #dc3545; color: white; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        
        # Label Instruksi
        lbl_info = QtWidgets.QLabel("Atur durasi nyala SM dalam siklus")
        lbl_info.setWordWrap(True)
        lbl_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_info)

        # Input SpinBox
        self.spin_duration = QtWidgets.QDoubleSpinBox()
        self.spin_duration.setRange(0.0, 60.0)    # 0 sampai 60 menit
        self.spin_duration.setSingleStep(5.0)     # Naik turun 5 menit
        self.spin_duration.setDecimals(0)         # Tampilkan bilangan bulat
        self.spin_duration.setSuffix(" Menit")
        self.spin_duration.setValue(current_duration)
        self.spin_duration.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spin_duration)

        # Feedback Label (Contoh: 20 Menit ON / 40 Menit OFF)
        self.lbl_feedback = QtWidgets.QLabel(f"Siklus: {int(current_duration)}m ON / {60-int(current_duration)}m OFF")
        self.lbl_feedback.setAlignment(Qt.AlignCenter)
        self.lbl_feedback.setStyleSheet("color: white; font-size: 12px;")
        layout.addWidget(self.lbl_feedback)

        # Update feedback saat nilai berubah
        self.spin_duration.valueChanged.connect(self.update_feedback)

        # Tombol Action
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("Simpan")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.clicked.connect(self.accept)

        self.btn_cancel = QtWidgets.QPushButton("Batal")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def update_feedback(self, val):
        on_time = int(val)
        off_time = 60 - on_time
        self.lbl_feedback.setText(f"Siklus: {on_time}m ON / {off_time}m OFF")

    def get_duration(self):
        return self.spin_duration.value()