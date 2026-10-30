"""
=============================================================================
  DIAC-X STP-FFI - LAPTOP MANUAL TEST & SIMULATION RUNNER
=============================================================================
Script ini khusus dijalankan di LAPTOP (Windows) untuk menguji seluruh fungsi
Mode Manual HMI tanpa memerlukan koneksi fisik ke panel / modul Waveshare / USR.

Cara Menjalankan:
    python main_manual_test.py

Fitur dalam mode ini:
1. Virtual Hardware Simulator aktif (Mock Modbus).
2. Semua tombol pompa, blower, valve, dan mixer dapat diklik dan menyala.
3. Animasi pipa dan gauge bergerak dinamis saat pompa dinyalakan.
4. Nilai sensor (Flow, Pressure, Level) disimulasikan sesuai status pompa.
5. Bebas dari error COM port / Modbus disconnected / ERR status.
6. Kredensial login: admin / admin (atau operator / operator).
=============================================================================
"""

import sys
import os

# Pastikan direktori saat ini masuk ke sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Reconfigure stdout/stderr to UTF-8 on Windows console
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QApplication, QMessageBox

# 1. Import dan pasang Simulated Hardware SEBELUM inisialisasi modul lain
from simulated_hardware import SimulatedModbusClient
import main_app

# Ganti ModbusSerialClient dengan simulator virtual
main_app.ModbusSerialClient = SimulatedModbusClient

print("=" * 70)
print("  🚀 DIAC-X STP-50 - MERDEKA COPPER GOLD (PT BATUTUA TEMBAGA RAYA)")
print("  ⚡ Virtual Modbus Hardware: Connected (Simulated)")
print("  🎮 Mode: MANUAL TEST MODE (LAPTOP)")
print("=" * 70)

def run_simulation():
    app = QApplication(sys.argv)
    
    # Jalankan background data sync jika ada
    try:
        import threading
        import data_sync
        sync_thread = threading.Thread(target=data_sync.start_monitoring, daemon=True)
        sync_thread.start()
        print("[SIMULATION] Background Data Sync thread started.")
    except Exception as e:
        print(f"[SIMULATION WARN] Data Sync skipped: {e}")

    # Buka jendela login terlebih dahulu (bisa login dengan admin / admin)
    login_gui = main_app.loginWindow()
    main_system = None

    # Pre-fill username dan password untuk kenyamanan test di laptop
    if hasattr(login_gui, 'input_username'):
        login_gui.input_username.setText("admin")
    if hasattr(login_gui, 'input_password'):
        login_gui.input_password.setText("admin")

    def launch_dashboard(role, username):
        nonlocal main_system
        print(f"[SIMULATION LAUNCHER] Login verified. Starting Main System for {username} ({role})...")
        main_system = main_app.MainSystemController(user_role=role, username=username)
        
        # Pastikan sistem mulai di Mode MANUAL
        main_system.system_mode = "MANUAL"
        if hasattr(main_system, 'btn_manual'):
            main_system.btn_manual.setText("MANUAL\nMODE")
        if hasattr(main_system, 'update_mode_ui'):
            main_system.update_mode_ui()
            
        main_system.showMaximized()
        login_gui.close()
        print("[SIMULATION READY] Main Dashboard is now active. Silakan test klik tombol pompa/blower!")

    login_gui.login_successful.connect(launch_dashboard)
    login_gui.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_simulation()
