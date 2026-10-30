@echo off
title DIAC-X STP-50 Merdeka Copper Gold (Laptop Test Simulation)
echo ==============================================================
echo   DIAC-X STP-50 - MERDEKA COPPER GOLD (PT BATUTUA TEMBAGA RAYA)
echo   Direktori: [Project] Merdeka Copper Gold\STP 50
echo ==============================================================
echo Menjalankan aplikasi dalam mode simulasi manual...
echo Username & Password login otomatis terisi: admin / admin
echo.
cd /d "%~dp0"
python main_manual_test.py
pause
