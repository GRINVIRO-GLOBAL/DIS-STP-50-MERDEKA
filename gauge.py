from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics
from PyQt5.QtCore import Qt, QRectF

class SemiCircularGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        
        # Default awal (akan berubah otomatis jika data lebih besar)
        self.min_value = 0
        self.max_value = 10 
        
        # Set minimum size lebih kecil agar fleksibel
        self.setMinimumSize(100, 50) 

    def set_range(self, min_val, max_val):
        """Fungsi manual untuk memaksa range tertentu (misal 0-14 untuk pH)"""
        self.min_value = min_val
        self.max_value = max_val
        self.update()

    def set_value(self, val):
        # --- LOGIKA AUTO-EXPAND (DINAMIS) ---
        # Jika nilai melebihi Max, tarik Max ke atas
        if val > self.max_value:
            # Tambahkan buffer 10% supaya jarum tidak nempel banget di ujung
            self.max_value = val + (val * 0.1)
        
        # Jika nilai kurang dari Min, tarik Min ke bawah
        if val < self.min_value:
            self.min_value = val
            
        self.value = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # --- KONFIGURASI TAMPILAN ---
        pen_width = max(10, min(self.width() / 15, 30))
        margin = pen_width / 2

        # --- PERHITUNGAN GEOMETRI ---
        w = self.width()
        h = self.height()
        available_width = w - 2 * margin
        available_height = h - 2 * margin
        diameter = min(available_width, available_height * 2)
        radius = diameter / 2

        cx = w / 2
        cy = h - margin 

        rect = QRectF(cx - radius, cy - radius, diameter, diameter)

        # --- MENGGAMBAR ---

        # 1. Background (Abu-abu - Track Gauge)
        pen_bg = QPen(QColor(220, 220, 220), pen_width, Qt.SolidLine, Qt.FlatCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 180 * 16, -180 * 16)

        # 2. Progress Value (Warna Warni Dinamis)
        # Kita buat warnanya berubah: Hijau (Normal), Kuning (Tinggi), Merah (Max)
        # Ini opsional, tapi bagus untuk visual
        progress_color = QColor(0, 120, 215) # Default Biru
        
        pen_val = QPen(progress_color, pen_width, Qt.SolidLine, Qt.FlatCap)
        painter.setPen(pen_val)

        # Hitung sudut
        total_range = self.max_value - self.min_value
        
        # Hindari pembagian dengan nol
        if total_range == 0: total_range = 1 
        
        # Clamping display (agar gambar tidak error melebih 180 derajat)
        display_val = max(self.min_value, min(self.max_value, self.value))
        
        val_per_deg = (display_val - self.min_value) / total_range
        span_angle = -180 * val_per_deg * 16
        
        painter.drawArc(rect, 180 * 16, int(span_angle))

        # 3. Teks Nilai (Besar di Tengah)
        font_size = max(10, int(radius / 4.0)) # Sedikit diperbesar
        font = QFont("Segoe UI", font_size, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))

        text_rect = QRectF(rect.left(), cy - radius, rect.width(), radius)
        # Tampilkan nilai integer
        painter.drawText(text_rect, Qt.AlignBottom | Qt.AlignHCenter, str(int(self.value)))

        # 4. Teks Skala Min & Max (Kecil di Kiri & Kanan)
        # Agar user tahu batas gauge saat ini berapa
        small_font = QFont("Segoe UI", max(8, int(radius / 8.0)))
        painter.setFont(small_font)
        painter.setPen(QColor(100, 100, 100))
        
        fm = QFontMetrics(small_font)
        text_height = fm.height()             # Tinggi teks aktual
        text_width = fm.width("9999") + 10    # Estimasi lebar (buffer)

        fm = QFontMetrics(small_font)
        text_height = fm.height()             # Tinggi teks aktual
        text_width = fm.width("9999") + 10    # Estimasi lebar (buffer)
        
        # Y Position: 
        # Kita ingin bagian 'bawah' teks sejajar dengan 'cy'. 
        # Jadi koordinat Y atas (Top) adalah cy - text_height.
        
        # Posisi Min (Kiri Bawah)
        # Rect: x, y, width, height
        rect_min = QRectF(cx - radius - margin, cy - text_height, text_width, text_height)
        painter.drawText(rect_min, Qt.AlignLeft | Qt.AlignBottom, str(int(self.min_value)))
        
        # Posisi Max (Kanan Bawah)
        # Geser X ke kiri sejauh text_width agar rata kanan terhadap ujung gauge
        rect_max = QRectF(cx + radius + margin - text_width, cy - text_height, text_width, text_height)
        painter.drawText(rect_max, Qt.AlignRight | Qt.AlignBottom, str(int(self.max_value)))

        painter.end()