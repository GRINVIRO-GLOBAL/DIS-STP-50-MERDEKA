"""
=============================================================================
  SIMULATED HARDWARE & MODBUS ENGINE UNTUK TEST MODE LAPTOP (MANUAL SIMULATION)
=============================================================================
File ini menyediakan simulasi perangkat keras (Virtual Modbus Client) sehingga
seluruh sistem HMI DIAC-X (STP-FFI) dapat dijalankan dan diuji coba 100% dari
laptop tanpa memerlukan koneksi fisik ke kabel USB RS485 / Waveshare / modul USR.

Fitur Simulasi:
- Mendukung penulisan & pembacaan Coil (DO), Holding Register, dan Input Register.
- Simulasi dinamis aliran pipa & sensor:
  * Jika Pompa Inlet ON -> FT_101 terbaca ~5.5 m³/jam
  * Jika Pompa MBR (TP-03) ON -> FT_102 terbaca ~6.0 m³/jam, PT_101 terbaca -0.15 bar
  * Jika Pompa Backwash (TP-04) ON -> FT_103 terbaca ~8.0 m³/jam
  * Jika Blower ON -> VFD terbaca ~380V, ~11.5A
  * Level Tangki (LT_101, LT_102, LT_103) diatur aman & realistis (~180 - 225 cm)
  * E-Stop fisik & Trip berada dalam kondisi normal (Ready / No Trip)
=============================================================================
"""

import struct
import time
import random

class MockModbusResponse:
    def __init__(self, is_error=False, bits=None, registers=None):
        self._is_error = is_error
        self.bits = bits or []
        self.registers = registers or []

    def isError(self):
        return self._is_error

    def __repr__(self):
        return f"<MockModbusResponse error={self._is_error} bits={self.bits} reg={self.registers}>"


class SimulatedModbusClient:
    def __init__(self, *args, **kwargs):
        self.port = kwargs.get('port', 'SIMULATION_PORT')
        self.client_type = kwargs.get('client_type', 'MAIN')
        self.connected = True
        self.socket = self # Dummy socket untuk serial attribute access
        
        # State penyimpanan internal (slave, address) -> value
        self.coils = {}
        self.registers = {}
        
        # Inisialisasi status DO awal (Semua pompa & valve mati)
        for slave in [3, 4, 6]:
            for addr in range(8):
                self.coils[(slave, addr)] = False
                
        # Inisialisasi E-Stop (Slave 1, Addr 0) -> 1 (Normal / tidak ditekan)
        self.di_inputs = {
            (1, 0): 1, # EMC
            (1, 1): 0, # TRIP_IN_A / TRIP_TP_01A
            (1, 2): 0, # TRIP_IN_B / TRIP_TP_01B
            (1, 3): 0, # TRIP_TP_01A
            (1, 4): 0, # TRIP_TP_01B
            (1, 5): 0, # TRIP_TP_02A
            (1, 6): 0, # TRIP_TP_02B
            (1, 7): 0, # TRIP_TP_03A / TRIP_TP_04A
            (2, 0): 0, # TRIP_TP_03B / TRIP_TP_04B
            (2, 1): 0, # TRIP_TP_04 / TRIP_TP_03
            (2, 2): 0, # TRIP_SM_01
            (2, 3): 0, # TRIP_SM_02
            (2, 4): 0, # TRIP_BL_01A
            (2, 5): 0, # TRIP_BL_01B
            (2, 6): 1, # LS_101 (Inlet Tank Level Switch: 1 = High / Normal)
            (2, 7): 1, # LS_102 (EQ Tank Level Switch: 1 = High / Normal)
            (3, 0): 1, # LS_103 (Permeate Tank Level Switch: 1 = High / Normal)
            (3, 1): 0, # LS_104
            (3, 2): 1, # AV_101_OP
            (3, 3): 0, # AV_101_CL
            (3, 4): 0, # AV_102_OP
            (3, 5): 1, # AV_102_CL
        }
        
        # Setpoint frekuensi VFD
        self.vfd_freq = {2: 45.0, 3: 45.0}

    # Dummy socket methods untuk PySerial
    def is_socket_open(self):
        return True

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def flush(self):
        pass

    def connect(self):
        self.connected = True
        return True

    def close(self):
        self.connected = False
        return True

    # --- WRITE COIL (DO) ---
    def write_coil(self, address, value, slave=1):
        self.coils[(slave, address)] = bool(value)
        return MockModbusResponse(is_error=False)

    # --- WRITE REGISTER (VFD / AO) ---
    def write_register(self, address, value, slave=1):
        self.registers[(slave, address)] = int(value)
        if address == 0x1000:
            self.vfd_freq[slave] = float(value) / 100.0 if value > 100 else float(value)
        return MockModbusResponse(is_error=False)

    def write_registers(self, address, values, slave=1):
        self.registers[(slave, address)] = list(values)
        return MockModbusResponse(is_error=False)

    # --- READ COILS (DO Status) ---
    def read_coils(self, address, count=1, slave=1):
        bits = []
        for i in range(count):
            bits.append(self.coils.get((slave, address + i), False))
        return MockModbusResponse(is_error=False, bits=bits)

    # --- READ DISCRETE INPUTS (DI Status & Trips) ---
    def read_discrete_inputs(self, address, count=1, slave=1):
        bits = []
        for i in range(count):
            val = self.di_inputs.get((slave, address + i), 0)
            bits.append(bool(val))
        return MockModbusResponse(is_error=False, bits=bits)

    # --- READ HOLDING / INPUT REGISTERS (Sensors & VFD) ---
    def read_holding_registers(self, address, count=2, slave=1):
        return self._generate_simulated_registers(address, count, slave)

    def read_input_registers(self, address, count=2, slave=1):
        return self._generate_simulated_registers(address, count, slave)

    def _generate_simulated_registers(self, address, count, slave):
        # 1. Blower VFD (Slave 2 atau Slave 3 di alamat 0x1003)
        if address == 0x1003:
            # Voltage ~ 380V, Current ~ 11.5A jika Blower aktif
            bl_key = 'BL_01A' if slave == 2 else 'BL_01B'
            is_on = self.coils.get((4, 4 if slave == 2 else 5), False)
            volt = 380 + random.randint(-2, 2) if is_on else 0
            amp = int((11.5 + random.uniform(-0.3, 0.3)) * 100) if is_on else 0
            return MockModbusResponse(is_error=False, registers=[volt, amp])

        # 2. Sensor Analog (AI)
        # Format USR_Library: float_data * 1000 di-pack jadi dua buah short (HH)
        target_value = 0.0

        # Slave 5 / 6: FT_101 (addr 0), FT_102 (addr 2), FT_103 (addr 4), PT_101 (addr 6)
        if slave in [5, 6]:
            if address == 0: # FT_101 (EQ Recirculation / Transfer Flow ~7.0 m³/h)
                inlet_on = (self.coils.get((4, 0), False) or self.coils.get((4, 1), False) or
                            self.coils.get((3, 0), False) or self.coils.get((3, 1), False) or
                            self.coils.get((3, 2), False) or self.coils.get((3, 3), False))
                target_value = (7.0 + random.uniform(-0.15, 0.15)) if inlet_on else 0.0
            elif address == 2: # FT_102 (MBR Permeate Flow ~2.5 m³/h)
                mbr_on = (self.coils.get((4, 4), False) or self.coils.get((4, 5), False) or
                          self.coils.get((3, 6), False) or self.coils.get((3, 7), False))
                target_value = (2.5 + random.uniform(-0.08, 0.08)) if mbr_on else 0.0
            elif address == 4: # FT_103 (Backwash Flow ~5.7 m³/h)
                bw_on = (self.coils.get((4, 6), False) or self.coils.get((4, 0), False) or
                         self.coils.get((3, 4), False))
                target_value = (5.7 + random.uniform(-0.12, 0.12)) if bw_on else 0.0
            elif address == 6: # PT_101 (Pressure MBR Suction / Backwash)
                mbr_on = (self.coils.get((4, 4), False) or self.coils.get((4, 5), False) or
                          self.coils.get((3, 6), False) or self.coils.get((3, 7), False))
                bw_on = (self.coils.get((4, 6), False) or self.coils.get((4, 0), False) or
                         self.coils.get((3, 4), False))
                if bw_on:
                    target_value = 0.35 + random.uniform(-0.02, 0.02) # Positif saat backwash
                elif mbr_on:
                    target_value = -0.15 + random.uniform(-0.01, 0.01) # Vakum saat sedot permeate
                else:
                    target_value = 0.01

        # Slave 6 / 7: DO_101 (addr 0), LT_101 (addr 2), LT_102 (addr 6), LT_103 (addr 4)
        elif slave in [6, 7]:
            if address == 0: # DO_101 Dissolved Oxygen (~3.5 mg/L)
                bl_on = (self.coils.get((5, 1), False) or self.coils.get((5, 2), False) or
                         self.coils.get((4, 4), False) or self.coils.get((4, 5), False))
                target_value = (3.5 + random.uniform(-0.1, 0.1)) if bl_on else 0.8
            elif address in [2, 4, 6]: # LT_101 / Level MBR Tank (~1.85 m)
                target_value = 1.85 + random.uniform(-0.02, 0.02)

        # Konversi target_value ke format float Modbus USR (value * 1000)
        try:
            packed_float = struct.pack(">f", float(target_value) * 1000.0)
            reg1, reg2 = struct.unpack(">HH", packed_float)
            return MockModbusResponse(is_error=False, registers=[reg1, reg2])
        except Exception:
            return MockModbusResponse(is_error=False, registers=[0, 0])
