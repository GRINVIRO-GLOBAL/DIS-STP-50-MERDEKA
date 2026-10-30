from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PyQt5.QtCore import Qt, QRectF, QPointF
import datetime

class SensorChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # --- Data ---
        self.hum_data = []  
        self.time_labels = [] 
        self.max_points = 100
        
        # Extended Data for new features
        self.total_accumulated = 0.0 # For Flow Totalizer
        self.max_level_range = 100.0 # For Level Percentage (Default 100cm)
        
        # Nama & Satuan Default
        self.instrument_name = "Sensor"
        self.unit_name = "" 
        self.status = "OK"  # Default status
    
        # --- Style & Warna ---
        self.setMinimumSize(400, 200) 
        self.bg_color = QColor(255, 255, 255)
        self.grid_color = QColor(230, 230, 230)
        self.hum_color = QColor(50, 50, 220) 
        self.text_color = QColor(60, 60, 60)
        self.secondary_text_color = QColor(120, 120, 120)

        # --- Font Configuration ---
        self.title_font = QFont("Segoe UI", 10, QFont.Bold)
        self.value_font = QFont("Segoe UI", 26, QFont.Bold)
        self.unit_font = QFont("Segoe UI", 12)  
        self.detail_font = QFont("Segoe UI", 14, QFont.Bold) # New font for Total/Pct
        self.label_font = QFont("Segoe UI", 8) 

    def set_title_name(self, name):
        """Mengubah nama instrumen untuk judul"""
        self.instrument_name = name
        self.update()

    def set_unit(self, unit):
        """Set satuan pembacaan (contoh: 'Bar', '°C', 'L/m')"""
        self.unit_name = unit
        self.update()
        
    def set_max_level(self, max_val):
        """Set nilai maksimum untuk perhitungan persentase level (Khusus LT)"""
        self.max_level_range = float(max_val) if max_val > 0 else 100.0

    def update_values(self, hum, total=None, status="OK"):
        """
        Update data chart.
        :param hum: Nilai realtime (float)
        :param total: (Optional) Nilai totalizer untuk Flow Meter
        :param status: Status pembacaan ("OK", "ERR", "OFFLINE")
        """
        self.hum_data.append(hum)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.time_labels.append(now)

        self.status = status

        if total is not None:
            self.total_accumulated = total

        if len(self.hum_data) > self.max_points:
            self.hum_data.pop(0)
            self.time_labels.pop(0)
        
        self.update() 

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # 1. Gambar Background
        painter.fillRect(self.rect(), self.bg_color)

        # --- [LOGIKA AUTO SCALE] ---
        if not self.hum_data:
            draw_min = 0; draw_max = 100; current_val = 0.0
        else:
            current_val = self.hum_data[-1]
            data_min = min(self.hum_data)
            data_max = max(self.hum_data)
            
            if data_min == data_max:
                if data_min == 0: draw_min = 0; draw_max = 10
                else:
                    padding = abs(data_min) * 0.2 
                    draw_min = data_min - padding; draw_max = data_max + padding
            else:
                rng = data_max - data_min
                padding = rng * 0.1
                draw_min = data_min - padding; draw_max = data_max + padding

        if draw_max <= draw_min: draw_max = draw_min + 1.0

        # --- LAYOUT MANAGEMENT ---
        split_x = w * 0.25
        
        chart_margin_top = 20
        chart_margin_bottom = 30
        chart_margin_right = 15
        chart_margin_left = 40 
        
        plot_rect = QRectF(
            split_x + chart_margin_left, 
            chart_margin_top, 
            w - split_x - chart_margin_left - chart_margin_right,
            h - chart_margin_top - chart_margin_bottom
        )

        # ==========================================================
        # BAGIAN 1: PANEL KIRI (Value, Unit, Title)
        # ==========================================================
        
        # 1. Judul
        painter.setFont(self.title_font)
        painter.setPen(self.text_color)
        title_rect = QRectF(15, 15, split_x - 20, 30)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self.instrument_name)
        
        # 2. Nilai Realtime
        painter.setFont(self.value_font)
        value_rect = QRectF(15, 50, split_x - 20, 50)
        
        status_val = getattr(self, 'status', 'OK')
        if status_val != "OK":
            painter.setPen(QColor(255, 0, 0)) # Red color for warning
            val_display = status_val
        else:
            painter.setPen(self.hum_color)
            if "Bar" in self.unit_name or "Pressure" in self.instrument_name:
                val_display = f"{current_val:.3f}"
            elif "Flow" in self.instrument_name:
                val_display = f"{current_val:.2f}"
            else:
                val_display = f"{current_val:.1f}"
        
        painter.drawText(value_rect, Qt.AlignLeft | Qt.AlignVCenter, val_display)
        
        # 3. Dynamic Footer (Totalizer / Percentage / Unit)
        # Area di bawah nilai utama
        footer_rect = QRectF(15, 105, split_x - 20, 50)
        
        if "Flow" in self.instrument_name:
            # === MODIFIKASI: TAMPILAN TOTALIZER ===
            painter.setFont(self.detail_font)
            painter.setPen(self.text_color)
            total_str = f"{self.total_accumulated:.2f}"
            
            # Gambar Angka Total
            painter.drawText(footer_rect, Qt.AlignLeft | Qt.AlignTop, total_str)
            
            # Gambar label "Total m3" di bawah angka total (lebih kecil)
            painter.setFont(self.label_font)
            painter.setPen(self.secondary_text_color)
            sub_rect = QRectF(15, 130, split_x - 20, 20)
            painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignTop, f"Total {self.unit_name}")

        elif "Level" in self.instrument_name:
            # === MODIFIKASI: TAMPILAN PERSENTASE ===
            pct = (current_val / self.max_level_range) * 100
            pct = max(0.0, min(100.0, pct)) # Clamp 0-100
            
            painter.setFont(self.detail_font)
            painter.setPen(self.text_color)
            painter.drawText(footer_rect, Qt.AlignLeft | Qt.AlignTop, f"{pct:.1f} %")
            
            # Gambar label "Capacity"
            painter.setFont(self.label_font)
            painter.setPen(self.secondary_text_color)
            sub_rect = QRectF(15, 130, split_x - 20, 20)
            painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignTop, "Capacity")

        else:
            # Standard Unit Display
            painter.setFont(self.unit_font)
            painter.setPen(self.secondary_text_color)
            label_unit = self.unit_name if self.unit_name else "Value"
            painter.drawText(footer_rect, Qt.AlignLeft | Qt.AlignTop, label_unit)

        # Separator Line
        painter.setPen(QPen(QColor(240,240,240), 2))
        painter.drawLine(int(split_x), 10, int(split_x), h-10)

        # ==========================================================
        # BAGIAN 2: PANEL KANAN (Chart Dinamis) - Tidak Berubah
        # ==========================================================

        painter.setFont(self.label_font)
        pen_grid = QPen(self.grid_color, 1, Qt.SolidLine)
        
        num_grid_lines = 5
        for i in range(num_grid_lines):
            ratio = i / (num_grid_lines - 1)
            y_pos = plot_rect.bottom() - (ratio * plot_rect.height())
            painter.setPen(pen_grid)
            painter.drawLine(QPointF(plot_rect.left(), y_pos), QPointF(plot_rect.right(), y_pos))
            
            val_at_grid = draw_min + (ratio * (draw_max - draw_min))
            txt_label = f"{val_at_grid:.1f}" if (draw_max - draw_min) < 10 else f"{int(val_at_grid)}"

            painter.setPen(self.secondary_text_color)
            label_area = QRectF(split_x, y_pos - 10, chart_margin_left - 5, 20)
            painter.drawText(label_area, Qt.AlignRight | Qt.AlignVCenter, txt_label)

        if len(self.hum_data) > 1:
             path = QPainterPath()
             range_val = draw_max - draw_min 
             x_step = plot_rect.width() / (self.max_points - 1)
             start_offset_idx = self.max_points - len(self.hum_data)
             
             first_val = max(draw_min, min(draw_max, self.hum_data[0]))
             first_y = plot_rect.bottom() - ((first_val - draw_min) / range_val * plot_rect.height())
             path.moveTo(plot_rect.left() + (start_offset_idx * x_step), first_y)
             
             for i in range(1, len(self.hum_data)):
                 x = plot_rect.left() + ((start_offset_idx + i) * x_step)
                 val = max(draw_min, min(draw_max, self.hum_data[i]))
                 y = plot_rect.bottom() - ((val - draw_min) / range_val * plot_rect.height())
                 path.lineTo(x, y)
                 
             painter.setPen(QPen(self.hum_color, 2))
             painter.drawPath(path)

        num_x_labels = 4
        if len(self.time_labels) > 0:
             indices = [int(i * (len(self.time_labels)-1) / (num_x_labels-1)) for i in range(num_x_labels)]
             x_step = plot_rect.width() / (self.max_points - 1)
             start_offset_idx = self.max_points - len(self.time_labels)
             
             for idx in indices:
                 if idx < len(self.time_labels):
                     x_pos = plot_rect.left() + ((start_offset_idx + idx) * x_step)
                     painter.setPen(self.grid_color)
                     painter.drawLine(QPointF(x_pos, plot_rect.bottom()), QPointF(x_pos, plot_rect.bottom() + 5))
                     painter.setPen(self.secondary_text_color)
                     time_str = self.time_labels[idx][:5] 
                     painter.drawText(QRectF(x_pos - 15, plot_rect.bottom() + 5, 30, 20), Qt.AlignCenter, time_str)
        painter.end()