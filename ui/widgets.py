# ui/widgets.py

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
import os


class ThumbnailWidget(QWidget):
    def __init__(self, placeholder_path="assets/placeholder.png"):
        super().__init__()

        self.label = QLabel("Thumbnail")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedSize(320, 180)
        self.label.setStyleSheet("border: 1px solid #444;")

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        if placeholder_path and os.path.exists(placeholder_path):
            self.set_thumbnail(placeholder_path)

    def set_thumbnail(self, image_path):
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.label.setPixmap(
                pixmap.scaled(
                    self.label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )


class DownloadProgressBar(QProgressBar):
    def __init__(self):
        super().__init__()
        self.setRange(0, 100)
        self.setValue(0)
        self.setFormat("%p%")
