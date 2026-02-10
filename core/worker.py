# core/worker.py

from PySide6.QtCore import QObject, Signal
from core.downloader import Downloader


class DownloadWorker(QObject):
    progress = Signal(int)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        url,
        format_type,
        quality,
        output_path,
        filename,
    ):
        super().__init__()

        self.url = url
        self.format_type = format_type
        self.quality = quality
        self.output_path = output_path
        self.filename = filename

    def run(self):
        try:
            downloader = Downloader(progress_callback=self._on_progress)

            downloader.download(
                url=self.url,
                format_type=self.format_type,
                quality=self.quality,
                output_path=self.output_path,
                filename=self.filename,
            )

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, percent):
        self.progress.emit(int(percent))
