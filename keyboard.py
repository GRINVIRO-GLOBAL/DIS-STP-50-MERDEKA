from PyQt5.QtWidgets import QWidget, QPushButton, QFrame, QApplication
from PyQt5.QtCore import Qt, QPoint, QTimer
import platform
import subprocess


def launch_virtual_keyboard():
    """Launch OS virtual keyboard with restart logic."""
    try:
        system = platform.system().lower()

        # ============================
        # WINDOWS
        # ============================
        if system == "windows":
            try:
                subprocess.Popen(["taskkill", "/f", "/im", "osk.exe"])
            except:
                pass

            subprocess.Popen(["osk.exe"], shell=True)

        # ============================
        # LINUX
        # ============================
        elif system == "linux":

            # Kill previous OSK
            for proc in ["onboard", "florence", "matchbox-keyboard", "xvkbd"]:
                try:
                    subprocess.Popen(["pkill", "-f", proc])
                except:
                    pass

            # Launch available OSK
            for kb in ["onboard", "florence", "matchbox-keyboard", "xvkbd"]:
                try:
                    subprocess.Popen([kb])
                    break
                except FileNotFoundError:
                    continue

    except Exception as e:
        print(f"Failed to launch virtual keyboard: {e}")


class FloatingKeyboardButton(QFrame):
    """Floating circular keyboard button that launches OSK."""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setFixedSize(70, 70)

        self.dragging = False
        self.offset = None

        self.button = QPushButton("⌨️", self)
        self.button.setFixedSize(60, 60)
        self.button.move(5, 5)

        self.button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A90E2, stop:1 #357ABD
                );
                color: white;
                border-radius: 30px;
                font-size: 24px;
                font-weight: bold;
                border: 3px solid #FFFFFF;
            }
            QPushButton:hover {
                border: 3px solid #FFD700;
            }
            QPushButton:pressed {
                border: 3px solid #FFA500;
            }
        """)

        self.button.clicked.connect(self.on_clicked)

    # ===================== BUTTON HANDLER FIX =====================
    def on_clicked(self):
        launch_virtual_keyboard()

        # FIX Linux focus recovery
        try:
            if self.parent() is not None and hasattr(self.parent(), "force_linux_input_recover"):
                QTimer.singleShot(300, self.parent().force_linux_input_recover)
        except:
            pass

    # ===================== DRAG SUPPORT =====================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.dragging and self.offset:
            new_pos = event.globalPos() - self.offset
            self.move(new_pos)
            self.raise_()

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.offset = None

    # ===================== POSITION =====================
    def position_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width() - 20
        y = screen.height() - self.height() - 60
        self.move(x, y)
        self.raise_()
