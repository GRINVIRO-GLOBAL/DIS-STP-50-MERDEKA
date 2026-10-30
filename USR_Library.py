import struct
from pymodbus.client import ModbusSerialClient
from time import sleep

class USRIOController:
    def __init__(self, conn):
        self.conn = conn

    def _flush(self):
        """Cleans dirty/residual bytes from serial UART buffers to avoid CRC desync"""
        try:
            ser = getattr(self.conn, 'socket', getattr(self.conn, 'comm', None))
            if ser:
                if hasattr(ser, 'reset_input_buffer'): ser.reset_input_buffer()
                if hasattr(ser, 'reset_output_buffer'): ser.reset_output_buffer()
        except Exception:
            pass

    #======================================= Outputs #=======================================
    def digitalOutput(self, address, value, slave):
        if not self.conn.connected:
            print(f"Not connected")

        try:
            self.conn.write_coil(address=address,
                                value=value,
                                slave=slave)
            
            data = value
            return int(data)
        
        except Exception as e:
            print(f"Error: Error writing: {e}")
            self._flush()
            return None

    def analogOutput(self, address, value, slave):
        if not self.conn.connected:
            print(f"Not connected")
        
        try:
            #Converting float to unsigned short
            data = value * 1000

            input_data = struct.pack(">f", data)
            hex_data = struct.unpack(">HH", input_data)
            val1 = hex_data[0]
            val2 = hex_data[1]

            #Writing analog output value
            self.conn.write_registers(address=address,
                                      values=[val1, val2],
                                      slave=slave)
            
            return value
        
        except Exception as e:
            print(f"Error: Error writing: {e}")
            self._flush()
            return None
    
    #======================================= Inputs #=======================================
    def digitalInput(self, address, slave):
        if not self.conn.connected:
            print(f"Not connected")
        
        try:
            readDI = self.conn.read_discrete_inputs(address=address,
                                                    count=1,
                                                    slave=slave)
            
            if readDI.isError():
                print(f"Modbus Error Reading DI: {readDI}")
                self._flush()
                return None
        
            data = readDI.bits[0]
            return int(data)
        
        except Exception as e:
            print(f"Error: Error reading: {e}")
            self._flush()
            return None

    def analogInput(self, address, slave, use_holding=False):
        if not self.conn.connected:
            print(f"Not connected")
            return None
        
        try:
            # OPSI 1: Default Read Input Registers (Function Code 04)
            if not use_holding:
                rr = self.conn.read_input_registers(address=address, count=2, slave=slave)
            else:
            # OPSI 2: Read Holding Registers (Function Code 03) - Banyak device pakai ini
                rr = self.conn.read_holding_registers(address=address, count=2, slave=slave)
        
            if rr.isError():
                print(f"Modbus Error Reading AI (Dev {slave} Addr {address}): {rr}")
                self._flush()
                return None

            r1 = rr.registers[0]
            r2 = rr.registers[1]

            raw_data = struct.pack(">HH", r1, r2)
            float_data = struct.unpack(">f", raw_data)

            data = float_data[0]/1000
            return round(data, 2) # Ubah ke 2 desimal biar rapi
        
        except Exception as e:
            print(f"Error: Error reading: {e}")
            self._flush()
            return None


if __name__ == "__main__":
    PORT = "COM3"
    BAUDRATE = 9600
    BYTESIZE = 8
    STOPBITS = 1
    PARITY = "N"

    client = ModbusSerialClient(port=PORT, baudrate=BAUDRATE, bytesize=BYTESIZE, stopbits=STOPBITS, parity=PARITY)

    client.connect()

    if client.connected:
        print(f"Device connected to {PORT}")

        # Making connection
        USR_BOX = USRIOController(client)

        # Write test
        DO33 = USR_BOX.digitalOutput(address=2, value=1, slave=3)
        print(f"Wrote {DO33} to DO33")

        AO = USR_BOX.analogOutput(address=6, value=5.0, slave=5)
        print(f"Wrote {AO} to AO")


        # Read Test
        DI23 = USR_BOX.digitalInput(address=2, slave=2)
        print(f"Read DI23 data: {DI23}")

        AI = USR_BOX.analogInput(address=0, slave=5)
        print(f"Read AI data: {AI}")
    
    else: print("Failed to connect to COM port")

    client.close()