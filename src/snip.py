import sys
import mss
import io
from PIL import Image
from PyQt6.QtWidgets import QApplication, QWidget, QRubberBand
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QGuiApplication

class SnippingWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. Window Setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")
        self.setWindowOpacity(0.4) # Dims the screen by 40%
        
        # Make cursor targeting crosshair
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 2. Stretch the widget to cover the entire primary monitor
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        
        # 3. Initialize the visual selection box
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()

    def mousePressEvent(self, event):
        # Start drawing the box where the user clicks
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.rubberBand.setGeometry(QRect(self.origin, self.origin))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        # Update the box size as the user drags the mouse
        self.rubberBand.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            
            # 100ms delay
            QTimer.singleShot(100, lambda: self.capture_screen(rect))

    def capture_screen(self, rect):
        region = {
            "top": rect.top(),
            "left": rect.left(),
            "width": rect.width(),
            "height": rect.height()
        }
        
        with mss.MSS() as sct:
            sct_img = sct.grab(region)
            
            # We can go back to the standard, fast conversion now!
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            img.save("snip_test.png")
            print(f"Success! Snipped a {rect.width()}x{rect.height()} region.")

        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SnippingWidget()
    ex.show()
    sys.exit(app.exec())