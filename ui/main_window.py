from core.downloader import Downloader
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Video Downloader")
        self.setMinimumSize(500, 300)

        self._setup_ui()

    def _setup_ui(self):
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # URL
        main_layout.addWidget(QLabel("URL do vídeo:"))
        self.url_input = QLineEdit()
        main_layout.addWidget(self.url_input)

        # Formato
        main_layout.addWidget(QLabel("Formato:"))
        self.format_selector = QComboBox()
        self.format_selector.addItems(["MP4", "MP3"])
        main_layout.addWidget(self.format_selector)

        # Pasta de destino
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_button = QPushButton("Escolher pasta")

        self.path_button.clicked.connect(self._choose_folder)

        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.path_button)

        main_layout.addWidget(QLabel("Pasta de destino:"))
        main_layout.addLayout(path_layout)

        # Nome do arquivo
        main_layout.addWidget(QLabel("Nome do arquivo:"))
        self.filename_input = QLineEdit()
        main_layout.addWidget(self.filename_input)

        # Botão de download
        self.download_button = QPushButton("Baixar")
        self.download_button.clicked.connect(self._on_download_clicked)
        main_layout.addWidget(self.download_button)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta")
        if folder:
            self.path_input.setText(folder)

    def _on_download_clicked(self):
        url = self.url_input.text().strip()
        format_selected = self.format_selector.currentText()
        path = self.path_input.text().strip()
        filename = self.filename_input.text().strip()

        downloader = Downloader()

        try:
            downloader.download(
                url = url,
                format_type = format_selected,
                output_path = path,
                filename = filename,
            )

            QMessageBox.information(
                self,
                "Sucesso",
                "Download concluído!",
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro",
                str(e),
            )

#        QMessageBox.information(
#            self,
#            "Debug",
#            f"URL: {url}\nFormato: {format_selected}\nPasta: {path}\nNome: {filename}",
#        )
