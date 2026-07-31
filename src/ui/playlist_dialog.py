# ui/playlist_dialog.py

""" Playlist download logic and guideline:
    When user want to made a playlist download, is possible 
    select wished videos, but all videos can only be download 
    on 1080p or best quality availabe (if doens't exist 1080p
    availabe). 
    
    That's a default and imutable setting. 

    Also the destine folder will be the same for all videos from
    that playlist.

    We decide to make the quality unique and apply to all playlist
    content witout user fine-tuning because the idea is build a 
    simpler, more stable version that meets most needs.
"""

""" Here you will find:
    - Playlist setting download dialog;
    - playlist videos thumbnail loader;
    - playlist dialog events function - like ui buttons;
    - playlists user warning text boxes;
    - playlist confirm download;
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QFileDialog, QMessageBox,
    QCheckBox)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QSize
from PySide6.QtGui import QPixmap

from src.models.download_item import DownloadItem
from src.core.utils import resolve_unique_title
from src.storage.settings_store import SettingsStore


# calculate video duration to show in UI
def _fmt_duration(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f" [{h}:{m:02d}:{s:02d}]"
    return f" [{m:02d}:{s:02d}]"


""" ==============================
    THUMBNAIL LOADER

    maybe that should be on a separete file
================================= """
# load the thumbnaol at a separete thread
class ThumbnailLoader(QObject):
    loaded = Signal(int, QPixmap)
    finished = Signal()

    def __init__(self, entries):
        super().__init__()
        self.entries = entries

    def run(self):
        for idx, entry in enumerate(self.entries):
            thumb_url = entry.get("thumbnail")
            if thumb_url:
                try:
                    r = requests.get(thumb_url, timeout=5)
                    if r.status_code == 200:
                        pixmap = QPixmap()
                        pixmap.loadFromData(r.content)
                        scaled = pixmap.scaled(80, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.loaded.emit(idx, scaled)
                except Exception:
                    pass
        self.finished.emit()


""" ==========================
        PLAYLIST DIALOG
  ========================= """
# show the playlist vídeos with checkboxest o user select wich one will be downloaded
# all videos select will share same format (.mp4 or .mp3) and save destine folder
class PlaylistDialog(QDialog):
    def __init__(self, playlist, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.entries = playlist.get("entries", [])
        self._items = []
        self.settings = SettingsStore()
        self._thumbnails = {}
        # that will need to be translated at location update
        self.setWindowTitle("Baixar playlist")
        self.setMinimumSize(700, 600)

        self._setup_ui()
        self._load_thumbnails()

    # UI implementation
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = self.playlist.get("title", "Playlist")
        # that will need to be translated at location update
        header = QLabel(f"Playlist: {title}  ({len(self.entries)} vídeos)")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # selection
        sel_bar = QHBoxLayout()
        # that will need to be translated at location update
        select_all = QPushButton("Selecionar todos")
        select_all.clicked.connect(lambda: self._set_all(True))
        # that will need to be translated at location update
        clear_all = QPushButton("Limpar seleção")
        clear_all.clicked.connect(lambda: self._set_all(False))
        sel_bar.addWidget(select_all)
        sel_bar.addWidget(clear_all)
        sel_bar.addStretch()
        layout.addLayout(sel_bar)

        # list with thumbnails
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(80, 60))
        for entry in self.entries:
            # that will need to be translated at location update
            label = (entry.get("title") or "(sem título)") + _fmt_duration(entry.get("duration"))
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        # format selection
        fmt_layout = QHBoxLayout()
        # that will need to be translated at location update
        fmt_layout.addWidget(QLabel("Formato:"))
        self.format_selector = QComboBox()
        # that will need to be translated at location update
        self.format_selector.addItems(["MP4", "MP3"])
        fmt_layout.addWidget(self.format_selector)
        fmt_layout.addStretch()
        layout.addLayout(fmt_layout)

        # quality warning
        # that will need to be translated at location update
        self.quality_warning = QLabel(
            "ℹ️ Os vídeos serão baixados na MELHOR QUALIDADE disponível (máx. 1080p) "
            "com os nomes originais do YouTube."
        )
        self.quality_warning.setStyleSheet("color: #666; font-size: 11px; padding: 5px; background: #f0f0f0; border-radius: 4px;")
        self.quality_warning.setWordWrap(True)
        layout.addWidget(self.quality_warning)

        # select destine folder
        # that will need to be translated at location update
        layout.addWidget(QLabel("Pasta de destino:"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        # that will need to be translated at location update
        path_button = QPushButton("Escolher pasta")
        path_button.clicked.connect(self._choose_folder)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(path_button)
        layout.addLayout(path_layout)

        # action buttons
        btns = QHBoxLayout()
        # that will need to be translated at location update
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        # that will need to be translated at location update
        ok = QPushButton("Baixar selecionados")
        ok.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    # load thumbnails on background
    def _load_thumbnails(self):
        self._thumb_thread = QThread()
        self._thumb_worker = ThumbnailLoader(self.entries)
        self._thumb_worker.moveToThread(self._thumb_thread)
        self._thumb_thread.started.connect(self._thumb_worker.run)
        self._thumb_worker.loaded.connect(self._on_thumb_loaded)
        self._thumb_worker.finished.connect(self._thumb_thread.quit)
        self._thumb_thread.finished.connect(self._thumb_thread.deleteLater)
        self._thumb_thread.start()

    # add thumbnail to list when load finished
    def _on_thumb_loaded(self, index, pixmap):
        if index < self.list_widget.count():
            item = self.list_widget.item(index)
            item.setIcon(pixmap)

    # select all button - set all itens as checked
    def _set_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    # choose folder button
    def _choose_folder(self):
        # that will need to be translated at location update
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta")
        if folder:
            self.path_input.setText(folder)

    # show quality warning to user - allow deactivate the warning by checkbox
    def _show_playlist_warning(self):
        if self.settings.get_skip_playlist_warning():
            return True

        msg = QMessageBox(self)
        # that will need to be translated at location update
        msg.setWindowTitle("Download da playlist")
        msg.setIcon(QMessageBox.Information)
        # that will need to be translated at location update
        msg.setText(
            "📋 **Atenção ao baixar a playlist**\n\n"
            "• Todos os vídeos serão baixados na **melhor qualidade disponível até 1080p**\n"
            "• Os nomes originais do YouTube serão preservados\n"
            "• Vídeos em 4K/8K serão convertidos para 1080p para economizar espaço\n\n"
            "Deseja continuar?"
        )

        # that will need to be translated at location update
        dont_ask = QCheckBox("Não mostrar esta mensagem novamente")
        msg.setCheckBox(dont_ask)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        
        result = msg.exec()
        
        if dont_ask.isChecked():
            self.settings.set_skip_playlist_warning(True)
        
        return result == QMessageBox.Yes

    # confirm playlist download order
    def _confirm(self):
        folder = self.path_input.text().strip()
        if not folder:
            # that will need to be translated at location update
            QMessageBox.warning(self, "Erro", "Escolha a pasta de destino.")
            return

        fmt = self.format_selector.currentText()
        selected = []
        # add each selected video url to a list
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.Checked:
                entry = it.data(Qt.UserRole)
                if entry.get("url"):
                    selected.append(entry)

        # check if leastways one was selected
        if not selected:
            # that will need to be translated at location update
            QMessageBox.warning(self, "Erro", "Selecione ao menos um vídeo.")
            return

        # show quality warning
        if not self._show_playlist_warning():
            return
        
        used_titles = set()
        items = []
        for entry in selected:
            # that will need to be translated at location update
            base_title = entry.get("title") or "video"
            title = resolve_unique_title(folder, base_title, fmt)
            while title in used_titles:
                title = resolve_unique_title(folder, title + " ", fmt)
            used_titles.add(title)

            quality_id = None
            if fmt == "MP4":
                quality_id = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

            # add videos to be downloaded by items list
            items.append(DownloadItem(
                url=entry["url"],
                title=title,
                original_title=base_title,
                format_type=fmt,
                # that will need to be translated at location update
                quality="Melhor qualidade (até 1080p)",
                quality_id=quality_id,
                thumbnail=entry.get("thumbnail"),
                status="pending",
                output_path=folder,
            ))

        self._items = items
        self.accept()

    # return the selected videos from playlist to be downloaded
    def get_result(self):
        return self._items