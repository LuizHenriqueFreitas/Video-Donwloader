# ui/componets/thumbnail_widget.py

""" Here you will find:
    - ThumbnailWidget class;
    - Set thumbnail function;
    - Set fallback placeholder image;
"""

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
import os


class ThumbnailWidget(QWidget):
    def __init__(self, placeholder_path=None):
        super().__init__()

        self._current_path = None
        self._placeholder = placeholder_path

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedSize(320, 180)
        self.label.setStyleSheet("border: 1px solid #444;")

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        # load initial placeholder
        if placeholder_path:
            self.set_thumbnail(placeholder_path)


    """ =====================
        SAFE SET THUMBNAIL
      ===================== """
    def set_thumbnail(self, image_path: str):
        if not image_path or not os.path.exists(image_path):
            self._set_placeholder()
            return

        # avoid load the same image
        if image_path == self._current_path:
            return

        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            self._set_placeholder()
            return

        self._current_path = image_path

        self.label.setPixmap(
            pixmap.scaled(
                self.label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    # ==========================
    # FALLBACK
    # ==========================
    def _set_placeholder(self):
        if self._placeholder and os.path.exists(self._placeholder):
            pixmap = QPixmap(self._placeholder)

            if not pixmap.isNull():
                self.label.setPixmap(
                    pixmap.scaled(
                        self.label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                return

        # final fallback - without image
        # that will need to be translated on location update
        self.label.setText("Sem imagem")