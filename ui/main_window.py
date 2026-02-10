# ui/main_window.py

import os
import requests

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import QThread

from core.video_info import VideoInfo
from core.worker import DownloadWorker
from ui.widgets import ThumbnailWidget, DownloadProgressBar


TEMP_THUMBNAIL = "temp/thumbnail.jpg"
PLACEHOLDER = "assets/placeholder.png"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Video Downloader")
        self.setMinimumSize(600, 600)

        self.thread = None
        self.worker = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        # URL
        layout.addWidget(QLabel("URL do vídeo:"))
        self.url_input = QLineEdit()
        self.url_input.editingFinished.connect(self._load_video_info)
        layout.addWidget(self.url_input)

        # Thumbnail
        self.thumbnail = ThumbnailWidget(PLACEHOLDER)
        layout.addWidget(self.thumbnail)

        # Formato
        layout.addWidget(QLabel("Formato:"))
        self.format_selector = QComboBox()
        self.format_selector.addItems(["MP4", "MP3"])
        layout.addWidget(self.format_selector)

        # Qualidade
        layout.addWidget(QLabel("Qualidade:"))
        self.quality_selector = QComboBox()
        self.quality_selector.addItems(["Máxima", "Full HD"])
        layout.addWidget(self.quality_selector)

        # Pasta
        layout.addWidget(QLabel("Pasta de destino:"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        path_button = QPushButton("Escolher pasta")
        path_button.clicked.connect(self._choose_folder)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(path_button)
        layout.addLayout(path_layout)

        # Nome
        layout.addWidget(QLabel("Nome do arquivo (opcional):"))
        self.filename_input = QLineEdit()
        layout.addWidget(self.filename_input)

        # Progresso
        self.progress_bar = DownloadProgressBar()
        layout.addWidget(self.progress_bar)

        # Botão
        self.download_button = QPushButton("Baixar")
        self.download_button.clicked.connect(self._start_download)
        layout.addWidget(self.download_button)

    # -------------------------
    # AÇÕES
    # -------------------------

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta")
        if folder:
            self.path_input.setText(folder)

    def _load_video_info(self):
        url = self.url_input.text().strip()
        if not url:
            return

        try:
            info = VideoInfo().extract(url)
            thumb_url = info.get("thumbnail")

            if thumb_url:
                os.makedirs("temp", exist_ok=True)
                r = requests.get(thumb_url, timeout=10)
                with open(TEMP_THUMBNAIL, "wb") as f:
                    f.write(r.content)

                self.thumbnail.set_thumbnail(TEMP_THUMBNAIL)

        except Exception as e:
            QMessageBox.warning(self, "Erro", str(e))

    def _start_download(self):
        url = self.url_input.text().strip()
        path = self.path_input.text().strip()

        if not url or not path:
            QMessageBox.warning(self, "Erro", "URL ou pasta inválida")
            return

        self.progress_bar.setValue(0)

        self.thread = QThread()
        self.worker = DownloadWorker(
            url=url,
            format_type=self.format_selector.currentText(),
            quality=self.quality_selector.currentText(),
            output_path=path,
            filename=self.filename_input.text().strip(),
        )

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._download_finished)
        self.worker.error.connect(self._download_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _download_finished(self):
        QMessageBox.information(self, "Sucesso", "Download concluído!")

    def _download_error(self, msg):
        QMessageBox.critical(self, "Erro", msg)
