# filename: alarm_state_manager.py

class AlarmStateManager:
    def __init__(self):
        self.active_alarms = set()       # Daftar alarm yang sedang error (Sensor HH/LL)
        self.acknowledged_alarms = set() # Daftar alarm yang sudah di-ACK (User menekan tombol)

    def trigger(self, alarm_name):
        """Sensor mendeteksi Error"""
        self.active_alarms.add(alarm_name)
        # Jika alarm baru muncul (atau kambuh), status ACK harus dicabut agar bunyi lagi
        if alarm_name in self.acknowledged_alarms:
            self.acknowledged_alarms.remove(alarm_name)

    def resolve(self, alarm_name):
        """Sensor kembali Normal"""
        self.active_alarms.discard(alarm_name)
        self.acknowledged_alarms.discard(alarm_name)

    def acknowledge_all(self):
        """User menekan tombol Alarm di GUI (Mode Manual)"""
        # Pindahkan semua yang aktif ke daftar 'sudah tahu' (ACK)
        self.acknowledged_alarms.update(self.active_alarms)

    def should_buzz(self, system_mode):
        """
        Menentukan apakah Buzzer Hardware harus bunyi?
        Logic Hybrid:
        1. Jika tidak ada alarm aktif -> MATI.
        2. Mode AUTO: Bunyi TERUS sampai resolved (User tidak bisa edit/ack).
        3. Mode MANUAL: Bunyi hanya jika belum di-ACK.
        """
        if not self.active_alarms:
            return False

        if system_mode == "AUTO":
            # Di Mode Auto: Bunyi terus selama ada alarm (Safety First)
            # Akan mati otomatis ketika sensor kembali normal (resolved)
            return True
        else:
            # Di Mode Manual: Bunyi hanya jika ada yang BELUM di-ACK
            # (Set Aktif dikurangi Set ACK)
            unacked_alarms = self.active_alarms - self.acknowledged_alarms
            return len(unacked_alarms) > 0
            
    def should_blink_red(self):
        """Untuk Visual Tombol Alarm di GUI (Merah)"""
        return len(self.active_alarms) > 0