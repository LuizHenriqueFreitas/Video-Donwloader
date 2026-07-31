# ui/download_dialog.py

""" Fix trimmer ui just show when checkbox was clicked - hide by default
"""

""" There're some classes and functions that shouldn't be here, perhaps they should 
    be in their own files.

    We also have some strange logic implementated that needs to be reviewed, 
    understood, and perhaps replaced.
"""

""" Here you will find:
    - load video placeholder asset;
    - all related to this dialog threads set();

    - PlaylistLoadWorker class;
    - VideoInfoWorker Class;

    - DownloadDialog Class;
    - Download dialog UI implementation;
    - event ui changers:
        - url changes;
        - media format download changes;
        - simple / advanced mode changes;

    - playlist_id link extraction;
    - playlist link builder;
    - playlist or unique dialog;

    - load video info into UI;
    - start playlist worker;

    - on_video_loaded() ui print informations;

    - playlist handlers;

    - trimmer tool ui settings;

    - video quality and file size insert into ui information;

    - ui actions logic - like for ui buttons etc;
    - confirm donwload logic;
    
    - memory cleaning functions.
"""

import os
import requests
from uuid import uuid4

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QCheckBox,
    QScrollArea, QWidget,
)
from PySide6.QtCore import QTimer, QThread, QObject, Signal, Slot

from core.video_info import VideoInfo, pick_preview_url
from core.utils import (
    resource_path, cookies_exists, looks_like_url, is_youtube,
    is_youtube_playlist,
    file_conflict, resolve_unique_title, expected_output_path,
    safe_filename, invalid_filename_chars, is_valid_filename, get_temp_dir
)
from ui.components.thumbnail_widget import ThumbnailWidget
from models.download_item import DownloadItem
from storage.settings_store import SettingsStore

# load placeholder video image
PLACEHOLDER = resource_path("assets/placeholder.png")

""" Mantain all alive threads refence untill their end, without block the UI.
    that avoid freezing (thread.wait() on main thread) and crash "QThread
    destroyed while runnig" if dialog were closed.
"""
_LIVE_THREADS = set()

# add new to live_threads set
def _keep_thread(thread):
    _LIVE_THREADS.add(thread)
    thread.finished.connect(lambda: _LIVE_THREADS.discard(thread))


""" =================================
    PLAYLIST LOADER WORKER CLASS

    Probably is a good idea move that to a own separete file
  ================================= """
class PlaylistLoadWorker(QObject):
    """ Add request_id in the signals so that solt knew witch order response
        without need lambdas with captions (their could cause delivery problems
        with threads at pyside6 and QueueConnection)
    """
    finished = Signal(object, str)
    error = Signal(str, str)

    def __init__(self, url, request_id):
        super().__init__()
        self.url = url
        self.request_id = request_id

    def run(self):
        try:
            playlist = VideoInfo().extract_playlist(self.url)
            self.finished.emit(playlist, self.request_id)
        except Exception as e:
            self.error.emit(str(e), self.request_id)


""" ===========================
    VIDEO INFO WORKER

    Probably is a good idea move that to a own separete file
  ========================== """
class VideoInfoWorker(QObject):
    # info, thumb_path, request_id  (object permite None no thumb)
    finished = Signal(object, object, str)
    error = Signal(str, str)  # msg, request_id

    def __init__(self, url, temp_path, request_id):
        super().__init__()
        self.url = url
        self.temp_path = temp_path
        self.request_id = request_id

    def run(self):
        try:
            info = VideoInfo().extract(self.url)

            thumb_url = info.get("thumbnail")
            thumb_path = None

            if thumb_url:
                r = requests.get(thumb_url, timeout=10)
                thumb_path = self.temp_path
                with open(thumb_path, "wb") as f:
                    f.write(r.content)

            self.finished.emit(info, thumb_path, self.request_id)

        except Exception as e:
            self.error.emit(str(e), self.request_id)


""" ==========================
    DOWNLOAD DIAGLOG CLASS

    main class of this file
  ========================== """
# create a download settings window
class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Novo Download")
        self.setMinimumSize(560, 600)

        self.settings = SettingsStore()

        self.video_info = None
        self.download_item = None
        self.trimmer = None
        # items to download - default = 1
        self._results = []

        # requiriments controll
        self._current_request_id = None
        self._thread = None
        self._worker = None
        self._current_thumb_path = None
        self._loading_url = None

        # debounce
        self.load_timer = QTimer()
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self._load_video_info)

        self._setup_ui()


    """ ====================
        UI IMPLEMENTATION 
       =================== """
    def _setup_ui(self):
        # responsive window to work on small screens
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.main_layout = layout

        # URL input
        layout.addWidget(QLabel("URL do vídeo (YouTube, TikTok, Instagram, etc.):"))
        self.url_input = QLineEdit()
        self.url_input.textChanged.connect(self._on_url_changed)
        layout.addWidget(self.url_input)

        # advanced mode (trimmer) - hide untill get video data
        self.advanced_check = QCheckBox("Selecionar trecho do vídeo (modo avançado)")
        self.advanced_check.setChecked(self.settings.get_advanced_mode())
        self.advanced_check.toggled.connect(self._on_mode_toggled)
        self.advanced_check.hide()
        layout.addWidget(self.advanced_check)

        # Status
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Thumbnail - simple mode
        self.thumbnail = ThumbnailWidget(PLACEHOLDER)
        layout.addWidget(self.thumbnail)

        # trimmer container (advanced mode) - draw when load video data
        self.trimmer_container = QVBoxLayout()
        layout.addLayout(self.trimmer_container)

        # selector media extension + quality
        format_layout = QHBoxLayout()
        # that will need to be translated at location update
        format_layout.addWidget(QLabel("Formato:"))
        self.format_selector = QComboBox()
        # that will need to be translated at location update
        self.format_selector.addItems(["MP4", "MP3"])
        self.format_selector.currentTextChanged.connect(self._on_format_changed)
        format_layout.addWidget(self.format_selector)

        # that will need to be translated at location update
        format_layout.addWidget(QLabel("Qualidade:"))
        self.quality_selector = QComboBox()
        self.quality_selector.setEnabled(False)
        format_layout.addWidget(self.quality_selector)
        layout.addLayout(format_layout)

        # select final file folder
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

        # fila saved name - default is the original media title
        # that will need to be translated at location update
        layout.addWidget(QLabel("Nome do arquivo (opcional):"))
        self.filename_input = QLineEdit()
        self.filename_input.textChanged.connect(self._validate_filename_live)
        layout.addWidget(self.filename_input)

        # is that just a visual feedback to warning wrong file names
        self.filename_warning = QLabel("")
        self.filename_warning.setStyleSheet("color: #F44336; font-size: 11px;")
        self.filename_warning.hide()
        layout.addWidget(self.filename_warning)

        # make the windows responsive and scrollable
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # fixed bottom buttons on page footer
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 6, 10, 10)
        # that will need to be translated at location update
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        # that will need to be translated at location update
        self.ok_button = QPushButton("Adicionar")
        self.ok_button.clicked.connect(self._confirm)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        outer.addLayout(button_layout)

        self._update_mode_visibility()


    """ ========================
                EVENTS
      ======================== """
    # run when a new link is pasted
    def _on_url_changed(self):
        text = self.url_input.text().strip()
        # check if could be a url link
        if looks_like_url(text):
            # that will need to be translated at location update
            self.status_label.setText("Carregando informações...")
            self.load_timer.start(800)

    # run when user change the media format extension to download - between .mp4 and .mp3
    def _on_format_changed(self, value):
        # if mp4 selected show available resolutions to download
        if value.upper() == "MP4":
            self.quality_selector.setEnabled(True)
            if self.video_info:
                self._populate_quality_selector()
        else:
            self.quality_selector.clear()
            self.quality_selector.setEnabled(False)

    # run when activate or deactivate advanced mode
    def _on_mode_toggled(self, checked):
        self.settings.set_advanced_mode(checked)
        self._update_mode_visibility()
        if checked and self.video_info:
            self._build_trimmer()
        elif not checked:
            self._destroy_trimmer()

    # on advanced mode the trimmer tool replace the simple thumbnail
    def _update_mode_visibility(self):
        advanced = self.advanced_check.isChecked() and self.advanced_check.isVisible()
        self.thumbnail.setVisible(not advanced)
        if self.trimmer:
            self.trimmer.setVisible(advanced)


    """ ======================
          NAME VALIDATION
     ======================= """
    # check if saved file name is allowed
    def _validate_filename_live(self):
        name = self.filename_input.text()
        bad = invalid_filename_chars(name)
        if bad:
            self.filename_warning.setText(
                # that will need to be translated at location update
                "O nome do arquivo não pode conter: " + "  ".join(bad)
            )
            self.filename_warning.show()
            self.ok_button.setEnabled(False)
        else:
            self.filename_warning.hide()
            self.ok_button.setEnabled(True)


    """ ===================================
        PLAYLIST DETECTION BY URL

        that probably should be together playlist worker class
      ================================== """
    # extract playlist id from youtube video url (&list=...)
    # need to check queue reprodution links, maybe that logic doens't for that and need to be changed
    def _extract_playlist_id_from_video_url(self, url):
        import re
        match = re.search(r'[&?]list=([a-zA-Z0-9_-]+)', url)
        return match.group(1) if match else None

    # build complete playlist url from ID
    def _build_playlist_url_from_id(self, playlist_id):
        return f"https://www.youtube.com/playlist?list={playlist_id}"

    # question to user if want to download all the playlist or just the link one
    def _ask_single_or_playlist(self):
        msg = QMessageBox(self)
        # that will need to be translated at location update
        msg.setWindowTitle("Playlist detectada")
        msg.setIcon(QMessageBox.Question)
        # that will need to be translated at location update
        msg.setText(
            "🔗 **Playlist detectada!**\n\n"
            "A URL informada pertence a uma playlist do YouTube.\n\n"
            "O que você deseja baixar?"
        )

        # that will need to be translated at location update
        btn_video = msg.addButton("📹 Apenas este vídeo", QMessageBox.AcceptRole)
        btn_playlist = msg.addButton("📋 Toda a playlist", QMessageBox.AcceptRole)
        btn_cancel = msg.addButton("Cancelar", QMessageBox.RejectRole) # why is that off?
        msg.setDefaultButton(btn_video)
        
        msg.exec()

        # send response by clicked button
        clicked = msg.clickedButton()
        if clicked == btn_video:
            return "single"
        elif clicked == btn_playlist:
            return "playlist"
        else:
            return "cancel"


    """ ==========================
        LOADING - THREAD SAFE
      =========================== """
    # load video information to UI
    def _load_video_info(self):
        url = self.url_input.text().strip()
        if not url:
            return

        if not cookies_exists():
            # that will need to be translated at location update
            self.status_label.setText("⚠ Cookies não configurados")
            return

        # playlist url detection
        playlist_id = self._extract_playlist_id_from_video_url(url)
        if playlist_id and not is_youtube_playlist(url):
            playlist_url = self._build_playlist_url_from_id(playlist_id)
            choice = self._ask_single_or_playlist(url, playlist_url)
            
            if choice == "cancel":
                # that will need to be translated at location update
                self.status_label.setText("Cancelado pelo usuário")
                return
            elif choice == "playlist":
                # load entier playlist
                self._start_playlist_worker(playlist_url, str(uuid4()))
                return
            # choice == "single": continues to just one video normal download

        # abandon any pendent request
        # check if that is really the better way to do this
        self._abandon_thread()
        self._reset_video_state()
        
        request_id = str(uuid4())
        self._current_request_id = request_id
        self._loading_url = url

        # classic youtube playlist pipeline
        """ Probably is a good thing that be on a separeted file, like video info service
            or something like that, maybe together to videoInfoWorker class

            Because is that starting and setting a thread - i don't know enough about threading
            right now, but i suspect of that be exists here.
        """
        if is_youtube_playlist(url):
            # that will need to be translated at location update
            self.status_label.setText("Carregando playlist...")
            self._start_playlist_worker(url, request_id)
            return

        # delete previous thumbnail (if any) before requesting a new one,
        # otherwise every pasted URL leaves an orphaned .jpg behind
        self._delete_current_thumb()

        # unique video runtime
        temp_thumb = os.path.join(get_temp_dir(), f"{request_id}.jpg")
        self._current_thumb_path = temp_thumb

        # that will need to be translated at location update
        self.status_label.setText("Carregando...")

        self._thread = QThread()
        self._worker = VideoInfoWorker(url, temp_thumb, request_id)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_video_loaded)
        self._worker.error.connect(self._on_video_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        _keep_thread(self._thread)
        self._thread.start()

    """ Again, i supose that should be on another file, maybe playlist service, 
        maybe together to playlistWorker class, because that use threads for playlist 
        things.
    """
    # playlist worker threads iniciator
    def _start_playlist_worker(self, url, request_id):
        self._thread = QThread()
        self._worker = PlaylistLoadWorker(url, request_id)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        """ I will check this logic before translate that documentation commentaries
        """
        # Conexão direta ao slot (sem lambda): garante QueuedConnection correto
        # entre a thread do worker e a thread principal (UI).
        self._worker.finished.connect(self._on_playlist_loaded)
        self._worker.error.connect(self._on_playlist_error)
        self._worker.finished.connect(lambda *_: self._thread.quit())
        self._worker.error.connect(lambda *_: self._thread.quit())
        self._thread.finished.connect(self._thread.deleteLater)

        _keep_thread(self._thread)
        self._thread.start()

    # clean UI video information
    def _reset_video_state(self):
        self.video_info = None
        self._destroy_trimmer()
        self.advanced_check.hide()
        self._update_mode_visibility()


    """ =========================
        HANDLERS - MAIN THREAD
      ========================= """

    # set UI components when load a new video information
    @Slot(object, object, str)
    def _on_video_loaded(self, info, thumb_path, request_id):
        if request_id != self._current_request_id:
            return

        self.video_info = info

        if thumb_path:
            self.thumbnail.set_thumbnail(thumb_path)

        title = info.get("title", "")
        if title:
            # suggest a valid name to save
            self.filename_input.setText(safe_filename(title))

        self._populate_quality_selector()

        """ The advanced mode only is showed when is warranted a real time video preview
            so, that function is only availabe to youtube links, we choice that aproach 
            because made the application a lot more solid and simple to implement.
        """
        can_preview = is_youtube(self._loading_url) and bool(pick_preview_url(info))
        if can_preview:
            self.advanced_check.show()
            if self.advanced_check.isChecked():
                self._build_trimmer()
        else:
            self.advanced_check.setChecked(False)
            self.advanced_check.hide()
            self._destroy_trimmer()
        self._update_mode_visibility()

        # that will need to be translated at location update
        self.status_label.setText("✔ Informações carregadas")

    # UI feedback when was an error getting video informations
    @Slot(str, str)
    def _on_video_error(self, msg, request_id):
        if request_id != self._current_request_id:
            return
        self.status_label.setText(f"Erro: {msg}")


    """ ===========================
        PLAYLIST HANDLERS

        Agina, i supose that should be on a playlist things dedicated file
    ============================= """
    # UI feedback to load playlist process
    @Slot(object, str)
    def _on_playlist_loaded(self, playlist, request_id):
        if request_id != self._current_request_id:
            return

        if not playlist or not playlist.get("entries"):
            # that will need to be translated at location update
            self.status_label.setText("Nenhum vídeo encontrado na playlist.")
            return

        # that will need to be translated at location update
        self.status_label.setText(
            f"✔ Playlist carregada: {len(playlist['entries'])} vídeos"
        )

        from src.ui.playlist_dialog import PlaylistDialog
        dlg = PlaylistDialog(playlist, self)
        if dlg.exec():
            self._results = dlg.get_result()
            self.accept()

    @Slot(str, str)
    def _on_playlist_error(self, msg, request_id):
        if request_id != self._current_request_id:
            return
        # that will need to be translated at location update
        self.status_label.setText(f"Erro ao carregar playlist: {msg}")


    """ ==========================
        TRIMMER TOOL UI SETTINGS
      ========================== """

    # add trimm tool to UI
    def _build_trimmer(self):
        if not self.video_info:
            return

        # clean older trimmer if were one
        self._destroy_trimmer()

        # late import to isolate dependencies from QtMultimedia
        from src.ui.components.clip_trimmer import ClipTrimmer

        # that will need to be translated at location update
        duration = self.video_info.get("duration")
        self.trimmer = ClipTrimmer(duration, self._current_thumb_path)
        self.trimmer_container.addWidget(self.trimmer)

        preview_url = pick_preview_url(self.video_info)
        self.trimmer.load_preview(preview_url)

        self._update_mode_visibility()

    # delete and clean trimm tool from UI
    def _destroy_trimmer(self):
        if self.trimmer:
            try:
                self.trimmer.stop()
            except Exception:
                pass
            self.trimmer_container.removeWidget(self.trimmer)
            self.trimmer.deleteLater()
            self.trimmer = None


    """ ================================
        VIDEO QUALITY - WITH FILE SIZE
      ================================ """
    # insert quality informations to quality UI selector
    def _populate_quality_selector(self):
        if not self.video_info:
            return

        formats = self.video_info.get("formats", [])
        video_formats = [
            f for f in formats
            if f.get("height") and f.get("vcodec") != "none"
        ]

        unique_heights = {}
        for f in video_formats:
            height = f.get("height")
            if height not in unique_heights:
                unique_heights[height] = f
            else:
                if f.get("tbr", 0) > unique_heights[height].get("tbr", 0):
                    unique_heights[height] = f

        sorted_heights = sorted(unique_heights.keys(), reverse=True)

        self.quality_selector.clear()
        for height in sorted_heights:
            f = unique_heights[height]
            label = f"{height}p"
            filesize = f.get("filesize") or f.get("filesize_approx")
            # calculate storage size
            if filesize:
                size_mb = filesize / (1024 * 1024)
                if size_mb >= 1024:
                    label += f" ({size_mb/1024:.1f} GB)"
                else:
                    label += f" ({size_mb:.1f} MB)"
            else:
                # that will need to be translated at location update
                label += " (tamanho desconhecido)"

            quality_id = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
            self.quality_selector.addItem(label, (quality_id, filesize))

        self.quality_selector.setEnabled(len(sorted_heights) > 0)
        if not sorted_heights:
            # that will need to be translated at location update
            self.quality_selector.addItem("Nenhum formato disponível", (None, None))


    """ =====================
        UI ACTIONS FUNCTIONS
      ===================== """
    # choose folder logic
    def _choose_folder(self):
        # that will need to be translated at location update
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta")
        if folder:
            self.path_input.setText(folder)

    # confirm download setting to start download instantly
    def _confirm(self):
        url = self.url_input.text().strip()
        path = self.path_input.text().strip()

        # validate url and path data
        if not url or not path:
            # that will need to be translated at location update
            QMessageBox.warning(self, "Erro", "URL ou pasta inválida")
            return

        # validate video settings data
        if not self.video_info:
            # that will need to be translated at location update
            QMessageBox.warning(self, "Erro", "Carregue as informações do vídeo primeiro")
            return

        fmt = self.format_selector.currentText()
        filename = self.filename_input.text().strip()

        # validate saved file name
        if filename and not is_valid_filename(filename):
            bad = invalid_filename_chars(filename)
            # that will need to be translated at location update
            QMessageBox.warning(
                self, "Nome inválido",
                "O nome do arquivo não pode conter os caracteres:\n\n"
                + "   ".join(bad)
            )
            return

        selected_quality_id = None
        selected_filesize = None
        if fmt.upper() == "MP4":
            data = self.quality_selector.currentData()
            if data and isinstance(data, tuple):
                selected_quality_id, selected_filesize = data

        # advanced mode
        clip_start, clip_end = (None, None)
        if self.advanced_check.isChecked() and self.trimmer:
            clip_start, clip_end = self.trimmer.get_clip()

        # that will need to be translated at location update
        original_title = self.video_info.get("title", "Sem título")
        final_title = filename if filename else safe_filename(original_title)

        """ verify existent equal file on destination folder (offers 3 options)
            - replace existent file;
            - automaticaly rename, addindg numeration like: file_name(1).mp4, file_name(2).mp4, etc;
            - go back and manualy rename.
        """
        overwrite = False
        if file_conflict(path, final_title, fmt):
            existing = expected_output_path(path, final_title, fmt)
            box = QMessageBox(self)
            # that will need to be translated at location update
            box.setWindowTitle("Arquivo já existe")
            box.setIcon(QMessageBox.Warning)
            # that will need to be translated at location update
            box.setText(
                f"Já existe um arquivo com este nome e tipo:\n\n{existing}\n\n"
                f"O que deseja fazer?"
            )
            # that will need to be translated at location update
            overwrite_btn = box.addButton("Substituir arquivo", QMessageBox.AcceptRole)
            rename_btn = box.addButton("Renomear automaticamente", QMessageBox.AcceptRole)
            back_btn = box.addButton("Voltar e trocar o nome", QMessageBox.RejectRole)
            box.setDefaultButton(back_btn)
            box.exec()

            clicked = box.clickedButton()
            if clicked == overwrite_btn:
                overwrite = True
            elif clicked == rename_btn:
                final_title = resolve_unique_title(path, final_title, fmt)
            else:
                # just came back to download dialog and users can rename manualy
                return

        # instantiate final download item with selected data
        self.download_item = DownloadItem(
            url=url,
            title=final_title,
            original_title=original_title,
            format_type=fmt,
            quality=self.quality_selector.currentText(),
            quality_id=selected_quality_id,
            thumbnail=self._current_thumb_path,
            status="pending",
            output_path=path,
            filesize=selected_filesize,
            clip_start=clip_start,
            clip_end=clip_end,
            overwrite=overwrite,
        )
        self._results = [self.download_item]
        self.accept()

    # items to download list - just 1 for unique content, N to youtube playlists
    def get_results(self):
        return self._results

    # basicaly same thing of get_results - mantained just to avoid broke some old code
    # should be replaced and deleted someday
    def get_result(self):
        return self._results[0] if self._results else None


    """ ====================
        CLEANIG OPERATIONS
      ==================== """
    # left open threads runnig - i supose that is terrible way to do this
    # i will check better options before translate the documentation comments
    def _abandon_thread(self):
        """
        Desvincula a thread de carregamento atual sem bloquear a UI.
        A thread continua viva (registrada em _LIVE_THREADS) até terminar
        sozinha; seu resultado tardio é ignorado pelo request_id.
        """
        # invalida qualquer resultado em andamento
        self._current_request_id = None
        for attr in ("_thread", "_worker"):
            setattr(self, attr, None)

    # delete the current temp thumbnail file, if any
    def _delete_current_thumb(self):
        path = self._current_thumb_path
        self._current_thumb_path = None
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # run when closes trimmer tool
    # maybe that could be at a trimmer file
    def done(self, result):
        """ Terminate preview player in a non-bloking manner.
            loading threads end up alone on background, we don't use wait() at main thread.
        """
        self._destroy_trimmer()
        self._current_request_id = None
        """ Clean up the thumbnail only if the dialog is being cancelled/closed
            without a confirmed download (result == Accepted keeps the file,
            since DownloadItem.thumbnail still points to it for the history card)
        """
        if result != QDialog.Accepted:
            self._delete_current_thumb()
        super().done(result)