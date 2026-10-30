# DIAC-X STP-50 (PT Batutua Tembaga Raya - Merdeka Copper Gold)

Program HMI / SCADA untuk Sewage Treatment Plant (STP) kapasitas 50 CMD berbasis PyQt5 dan arsitektur DIAC-X standar (direferensikan dari project FFI paling mutakhir).

---

## 1. Pemetaan Peralatan & Instrumen (P&ID Rev. 01 & I/O List)

### A. Unit Tangki
- **TK-01**: *Incoming Wastewater Inlet Tank* (By Client)
- **EQ-01**: *Equalizing Tank* (18 m³) dilengkapi Basket Screen `BS-01` & Diffuser `DF-0*`
- **AE-01**: *Aeration Tank* dilengkapi Submersible Mixer `SM-01` (0.75 kW)
- **MBR-01**: *Membrane Bio Reactor Tank* (29.6 m³) dengan Kaset Membran `CS-01` (PVDF)
- **TK-02**: *Backwash Tank* (PE 3000 L)
- **JC-01**: *Chlorine Jerry Can* (50 L)
- **CLT-01**: *Chlorination / Discharge Line*

### B. Pompa & Motor
| Tag | Deskripsi | Tipe Kontrol | Catatan P&ID Rev. 01 |
| :--- | :--- | :--- | :--- |
| **TP-01A / B** | Inlet Transfer Pump (TK-01 $\rightarrow$ EQ-01) | DOL (Machine Dialog) | 2.5 CMH, 0.75 kW (1W + 1S) |
| **TP-02A / B** | EQ Transfer Pump (EQ-01 $\rightarrow$ AE/MBR) | DOL (Machine Dialog) | 2.5 CMH, 0.75 kW (1W + 1S) |
| **TP-04A / B** | MBR Permeate Pump (Sedot Hasil Membran) | **VFD Controlled (0 - 50 Hz)** | 3.0 CMH, 0.55 kW (1W + 1S) |
| **TP-03** | MBR Backwash Pump (Pencucian Membran) | **VFD Controlled (0 - 50 Hz)** | 6.0 CMH, 0.75 kW (1 Unit) |
| **TP-05A / B** | MBR RAS Pump (Sludge Recycle ke AE-01) | DOL (Machine Dialog) | 10.0 CMH, 0.75 kW (1W + 1S) |
| **BL-01A / B** | MBR Blower (Aerasi) | DOL (Machine Dialog) | Side Channel 3 kW *(Rev.01: Non-VFD)* |
| **SM-01** | Submersible Mixer (di AE-01) | DOL (Timer On/Off) | 0.75 kW (1 Unit) |
| **DP-01** | Chlorine Dosing Pump | DOL (Machine Dialog) | Dosing ke CLT-01 |
| **AV-101** | Auto Valve Permeate Line | Open / Close | Interlock arah sedot membran |
| **AV-102** | Auto Valve Backwash Line | Open / Close | Interlock arah backwash |

### C. Instrumen & Sensor
- **FT-101**: Flowmeter Inlet / EQ (Modbus RS485, m³/h)
- **FT-102**: Flowmeter MBR Permeate (Modbus RS485, m³/h)
- **FT-103**: Flowmeter MBR Backwash (Modbus RS485, m³/h)
- **PT-101**: Pressure Transmitter Header MBR (4-20mA / bar)
- **DO-101**: Dissolved Oxygen Analyzer (Modbus RS485, mg/L)
- **LT-101**: Level Transmitter Tangki (4-20mA / cm)
- **LS-101 s/d LS-104**: Level Switch batas tangki (Digital Input)

---

## 2. Cara Menjalankan Mode Simulasi di Laptop

1. **Menggunakan Batch File**:
   Double click file `RUN_TEST_LAPTOP.bat`.
2. **Menggunakan Terminal / PowerShell**:
   ```bash
   python main_manual_test.py
   ```
3. **Kredensial Login**:
   - Username: `admin`
   - Password: `admin`
   *(Sudah otomatis terisi saat form login muncul)*

---

## 3. Fitur Utama
- **Theme & Styling**: 100% konsisten dengan desain DIAC-X FFI (`Dashboard_new.css`).
- **P&ID Interactive Dashboard**: Klik tombol pompa untuk menyalakan/mematikan secara manual dengan konfirmasi pop-up dialog.
- **VFD Dialog**: Pengaturan frekuensi Hz untuk Permeate Pump (`TP-04A`, `TP-04B`) dan Backwash Pump (`TP-03`).
- **Siklus MBR Otomatis**: Filtrasi (Run $\rightarrow$ Relax) secara periodik diselingi Backwash otomatis dan proteksi dead-heading katup `AV-101` / `AV-102`.
- **Siklus CEB (Chemical Enhanced Backwash)**: Maintenance wizard 5 fase (Backwash + Chemical Dosing $\rightarrow$ Soaking $\rightarrow$ Aerasi $\rightarrow$ Flushing $\rightarrow$ Selesai).
- **Sensor & Totalizer Logging**: Pencatatan data sensor ke CSV/grafik dan perhitungan totalizer harian/shift.
