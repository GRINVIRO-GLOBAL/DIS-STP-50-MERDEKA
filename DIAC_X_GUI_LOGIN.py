import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
from PyQt5 import uic
from PyQt5.QtGui import QPixmap, QPalette, QBrush, QKeyEvent
from PyQt5.QtCore import Qt, QTimer, QEventLoop, QEvent, pyqtSignal

# NOTE: keyboard.py is kept untouched (FloatingKeyboardButton, launch_virtual_keyboard)
from keyboard import FloatingKeyboardButton, launch_virtual_keyboard


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(CURRENT_DIR)

UI_FILE = "DIAC_X_GUI_LOGIN.ui"
JSON_FILE = "user_accounts.json"
BG_IMAGE = os.path.join("Assets", "HexagonsBackground_resized.png")


class loginWindow(QDialog):
    login_successful = pyqtSignal(str, str) # Mengirim role dan username
    def __init__(self):
        super().__init__()
        self._bg_pixmap = None
        self.final_role = "guest"
        self.final_username = "Guest"

        self.initUI()

        # floating keyboard MUST have parent
        self.floating_kb = FloatingKeyboardButton(self)

        # shadow widget used for safe X11 regrab (1px widget)
        self._shadow = None

        # guard so we don't spam regrabs
        self._last_regrab_ms = 0

    # ======================================================================
    # CORE UI
    # ======================================================================
    def initUI(self):
        try:
            uic.loadUi(UI_FILE, self)
        except Exception as e:
            print(f"UI Load Error: {e}")

        self.setWindowTitle("DIAC-X Login Window")

        self.login_btn.clicked.connect(self.openDashboard)
        self.login_btn.setAutoDefault(True)
        self.login_btn.setDefault(True)

        if hasattr(self, "password_data"):
            self.password_data.returnPressed.connect(self.openDashboard)
        if hasattr(self, "email_data"):
            self.email_data.returnPressed.connect(self.openDashboard)

        self.setup_manual_background()

    # ======================================================================
    # BACKGROUND
    # ======================================================================
    def setup_manual_background(self):
        if os.path.exists(BG_IMAGE):
            self._bg_pixmap = QPixmap(BG_IMAGE)
            self.apply_background_pixmap()

    def apply_background_pixmap(self):
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            pal = self.palette()
            pal.setBrush(QPalette.Window, QBrush(scaled))
            self.setPalette(pal)
            self.setAutoFillBackground(True)

    # ======================================================================
    def showEvent(self, e):
        super().showEvent(e)

        # 1) Small delay then try wakeup (fake key) — helps X11/Qt accept keyboard
        QTimer.singleShot(120, self.force_x11_keyboard_wakeup)

        # 2) Show floating keyboard + auto-launch (after QDialog stabilized)
        QTimer.singleShot(400, self.force_keyboard_show)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_background_pixmap()
        if self.floating_kb.isVisible():
            self.position_keyboard()

    # ======================================================================
    # X11 keyboard wakeup: send a synthetic Shift press+release to the focused widget.
    # This wakes X11/Qt keyboard routing without user typing in terminal.
    # ======================================================================
    def force_x11_keyboard_wakeup(self):
        try:
            target = None
            # prefer the email field, fallback to dialog itself
            if hasattr(self, "email_data") and self.email_data is not None:
                target = self.email_data
            else:
                target = self

            # send KeyPress
            ev_press = QKeyEvent(QEvent.KeyPress, Qt.Key_Shift, Qt.NoModifier, "")
            QApplication.sendEvent(target, ev_press)
            QApplication.processEvents()

            # send KeyRelease
            ev_release = QKeyEvent(QEvent.KeyRelease, Qt.Key_Shift, Qt.NoModifier, "")
            QApplication.sendEvent(target, ev_release)
            QApplication.processEvents()
        except Exception as ex:
            print("[X11 Wakeup Error]", ex)

    # ======================================================================
    # SAFE shadow regrab: create a tiny Qt Tool window (1px) then hide it.
    # This forces X11 to remap input context without touching the main window flags.
    # ======================================================================
    def trigger_x11_regrab(self):
        # minimal rate limiting (prevent frequent calls)
        try:
            import time
            now = int(time.time() * 1000)
            if now - self._last_regrab_ms < 800:
                return
            self._last_regrab_ms = now

            if self._shadow is None:
                self._shadow = QWidget()

            # set as a Tool window so WM maps/unmaps it quickly and without decoration
            self._shadow.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
            self._shadow.setAttribute(Qt.WA_TranslucentBackground, True)

            # place off-screen or tiny at origin
            self._shadow.setGeometry(0, 0, 1, 1)
            self._shadow.show()
            QApplication.processEvents()

            # hide immediately to force X11 remap
            self._shadow.hide()
            QApplication.processEvents()

            # then perform a keyboard wakeup
            QTimer.singleShot(50, self.force_x11_keyboard_wakeup)

        except Exception as ex:
            print("[Shadow Regrab Error]", ex)

    # ======================================================================
    def position_keyboard(self):
        try:
            self.floating_kb.position_bottom_right()
        except:
            pass

    # ======================================================================
    # Show floating keyboard and auto-launch OSK. After OSK launched,
    # trigger shadow regrab and synthetic wakeup to ensure Qt receives keys.
    # ======================================================================
    def force_keyboard_show(self):
        self.floating_kb.show()
        self.floating_kb.raise_()
        self.position_keyboard()

        # Launch external OSK (onboard/florence/matchbox/xvkbd or osk.exe on Windows)
        launch_virtual_keyboard()

        # After a short delay: wakeup and then shadow-regrab to be robust.
        QTimer.singleShot(200, self.force_x11_keyboard_wakeup)
        QTimer.singleShot(1000, self.trigger_x11_regrab)

    # ======================================================================
    # LOGIN PROCESS
    # ======================================================================
    def openDashboard(self):
        input_user = ""
        input_pass = ""
        try:
            input_user = self.email_data.text()
        except:
            input_user = ""
        try:
            input_pass = self.password_data.text()
        except:
            input_pass = ""

        login_success = False
        user_role = "guest"

        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r") as f:
                    users = json.load(f)
                for user in users:
                    if user.get("username") == input_user and user.get("password") == input_pass:
                        login_success = True
                        user_role = user.get("access_level", "guest")
                        break
            except Exception as e:
                print("JSON read error:", e)

        if login_success:
            print("Login OK:", input_user, "Role:", user_role)

            self.final_role = user_role
            self.final_username = input_user

            try:
                self.floating_kb.close()
            except:
                pass

            # Close Windows OSK (ignored on Linux)
            try:
                os.system("taskkill /f /im osk.exe >nul 2>&1")
                os.system("taskkill /f /im tabtip.exe >nul 2>&1")
            except:
                pass

            # # small delay
            # loop = QEventLoop()
            # QTimer.singleShot(150, loop.quit)
            # loop.exec_()

            # self.accept()

            self.login_successful.emit(user_role, input_user)

        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Login Failed")
            msg.setText("Username atau Password salah!")
            msg.exec_()


# ======================================================================
# MAIN APP
# ======================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = loginWindow()
    w.showMaximized()
    sys.exit(app.exec_())