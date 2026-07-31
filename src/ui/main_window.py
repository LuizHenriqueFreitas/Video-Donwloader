# ui/main_window.py

""" WARNING! There's a lot of fucntions not implemented correct
    That need to be verified soon as possible.
"""

""" That is the main window file, implement GUI using Pyside6 and QtWidgets frameworks

    Here you will find:
    - Update_worker class -> probably is a good idea move to another place;
    - GUI to backend connectors and triggers.
        - there's a lot of functions, but simplified: GUI integrating backend. 
"""

import os
import shutil

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QFileDialog, QLabel,
    QComboBox, QApplication,
)
from PySide6.QtCore import Qt, QMetaObject, QObject, QThread, Signal, Q_ARG, Slot

from controllers.download_controller import DownloadController
from services.download_service import DownloadService
from services.updater import (
    check_and_update_ytdlp, 
    check_app_update, 
    get_installed_version_ytdlp, 
    APP_VERSION,
)

from ui.components.download_card import DownloadCard
from ui.download_dialog import DownloadDialog

from core.utils import get_cookies_path, cookies_exists, secure_cookies_file, clear_temp_dir
from storage.settings_store import SettingsStore, ALLOWED_HISTORY_COUNTS



""" ========================
    YT-DLP WORKER UPDATER
    
    Should be good move this to a separete file
  ======================= """
#check yt-dlp version
class UpdateCheckWorker(QObject):
    finished = Signal(str, bool, object)

    def run(self):
        try:
            _ok, ytdlp_msg = check_and_update_ytdlp()
        except Exception as e:
            # that will need to be translated on location update
            ytdlp_msg = f"Erro ao atualizar yt-dlp: {e}"
        available, latest = check_app_update()
        self.finished.emit(ytdlp_msg, available, latest)


""" ==================================
    MAIN WINDOW CLASS IMPLEMENTATION
  ================================= """
# main window class
class MainWindow(QMainWindow):
    # UI update signals from download threads
    sig_progress = Signal(str, int)
    sig_finished = Signal(object)
    sig_error = Signal(object, str)
    sig_cancelled = Signal(object)

    def __init__(self):
        super().__init__()

        # set window title and size
        self.setWindowTitle("GET MEDIA FREE")
        self.setMinimumSize(900, 600)

        # instantiate operational classes
        self.controller = DownloadController()
        self.download_service = DownloadService()
        self.settings = SettingsStore()

        # history video cards
        self.cards = {}
        # items waithing cancell process to be removed from UI
        self._pending_removal = set()

        # connect download signals by QueuedConnection to UI thread
        self.sig_progress.connect(self._on_progress_ui)
        self.sig_finished.connect(self._on_download_finished)
        self.sig_error.connect(self._on_download_error)
        self.sig_cancelled.connect(self._on_download_cancelled)

        self._setup_ui()
        self._render_history()
        self._load_ytdlp_version()
        self._update_cookie_ui()

        # safety net: wipe leftover temp thumbnails from a previous run
        # (crash, force-quit, dialog closed in an unexpected way)
        try:
            clear_temp_dir()
        except Exception:
            pass


    """ ========================
        APP SHUTDOWN PROTOCOL
      ======================== """
    # certify close all process correct in case close window
    def closeEvent(self, event):
        # end all active downloads correctly and safely
        try:
            self.download_service.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


    """ =======================
          MAIN WINDOW UI
      ===================== """

    """ All the "Front end" code is on that function,
        is here where the gadgets were drawned into screen.
        Obvius using another functinos, but is here where the
        app layout is defined by code.
    """
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        # top bar
        top_bar = QHBoxLayout()

        """ Below there's all top bar components declaration,
            like butons and feedback labels.
        """
        # new download button
        self.new_button = QPushButton("+ Colar link") # that will need to be translated on location update
        self.new_button.clicked.connect(self._open_download_dialog)

        # check updates button
        self.update_button = QPushButton("Buscar atualizações") # that will need to be translated on location update
        self.update_button.clicked.connect(self._check_updates)

        # import cookies button
        self.import_cookies_btn = QPushButton("Importar cookies") # that will need to be translated on location update
        self.import_cookies_btn.clicked.connect(self._import_cookies)

        # remove cookies button
        self.remove_cookies_btn = QPushButton("Remover cookies") # that will need to be translated on location update
        self.remove_cookies_btn.clicked.connect(self._remove_cookies)

        # cookies status feedback
        self.cookies_status_label = QLabel("Cookies: ...") # that will need to be translated on location update

        # history limit selector
        self.history_label = QLabel("Histórico:") # that will need to be translated on location update
        self.history_count_selector = QComboBox()
        for n in ALLOWED_HISTORY_COUNTS:
            self.history_count_selector.addItem(str(n), n)
        current = self.settings.get_history_count()
        idx = self.history_count_selector.findData(current)
        if idx >= 0:
            self.history_count_selector.setCurrentIndex(idx)
        self.history_count_selector.currentIndexChanged.connect(self._on_history_count_changed)

        # clear all history button
        self.clear_history_btn = QPushButton("Limpar histórico") # that will need to be translated on location update
        self.clear_history_btn.clicked.connect(self._clear_history)

        # yt-dlp version label
        self.version_label = QPushButton("yt-dlp: ...")
        self.version_label.setEnabled(False)

        # adding components into top_bar
        top_bar.addWidget(self.new_button)
        top_bar.addWidget(self.update_button)
        top_bar.addWidget(self.import_cookies_btn)
        top_bar.addWidget(self.remove_cookies_btn)
        top_bar.addWidget(self.clear_history_btn)
        top_bar.addWidget(self.cookies_status_label)
        top_bar.addStretch()
        top_bar.addWidget(self.history_label)
        top_bar.addWidget(self.history_count_selector)
        top_bar.addWidget(self.version_label)

        # adding top_bar to layout
        layout.addLayout(top_bar)

        # scroll area to history cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.container_layout = QVBoxLayout()
        self.container.setLayout(self.container_layout)

        self.scroll.setWidget(self.container)

        # adding scroll zone to layout
        layout.addWidget(self.scroll)


    """ ===================
        VERSION & UPDATE

        maybe should be good move this to updater_worker - this file doesn't exist yet
      =================== """
    
    # load actual yt-dlp installed version
    def _load_ytdlp_version(self):
        version = get_installed_version_ytdlp()
        self.version_label.setText(f"yt-dlp: {version}")

    # check for lastest yt-dlp releases
    def _check_updates(self):
        self.update_button.setEnabled(False)
        # that will need to be translated on location update
        self.update_button.setText("Buscando...")

        # that process runs in a thread to don't freze the UI
        self._upd_thread = QThread()
        self._upd_worker = UpdateCheckWorker()
        self._upd_worker.moveToThread(self._upd_thread)
        self._upd_thread.started.connect(self._upd_worker.run)
        self._upd_worker.finished.connect(self._on_updates_checked)
        self._upd_worker.finished.connect(self._upd_thread.quit)
        self._upd_thread.finished.connect(self._upd_thread.deleteLater)
        self._upd_thread.start()

    # return correct message after check update options available - create a UI component
    @Slot(str, bool, object)
    def _on_updates_checked(self, ytdlp_msg, app_update_available, latest_version):
        self.update_button.setEnabled(True)
        # that will need to be translated on location update
        self.update_button.setText("Buscar atualizações")
        self._load_ytdlp_version()

        if app_update_available and latest_version:
            # that will need to be translated on location update
            self._safe_message(
                "Atualização disponível",
                f"Nova versão ({latest_version}) disponível para download. "
                f"Atualize para novos recursos e correções.\n\n"
                f"yt-dlp: {ytdlp_msg}",
            )
        else:
            # that will need to be translated on location update
            self._safe_message(
                "Atualizações",
                f"yt-dlp: {ytdlp_msg}\n\n"
                f"O app já está na versão mais recente (v{APP_VERSION}).",
            )


    """ ====================
            HISTORY
      ================== """

    # runs where has a history limit change
    def _on_history_count_changed(self):
        count = self.history_count_selector.currentData()
        if count in ALLOWED_HISTORY_COUNTS:
            self.settings.set_history_count(count)
            self._render_history()

    # ask confirmation and wipe the entire download history
    def _clear_history(self):
        box = QMessageBox(self)
        # that need to be translated on location update
        box.setWindowTitle("Limpar histórico")
        box.setIcon(QMessageBox.Question)
        box.setText(
            "Todo o histórico de downloads será apagado, mas os vídeos "
            "continuam em seu computador, se quiser deletá-los faça manualmente."
        )
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)

        reply = box.exec()
        if reply != QMessageBox.Ok:
            return

        self.controller.clear_history()
        self._render_history()

    # draw history items
    def _render_history(self):
        # clean list
        while self.container_layout.count():
            child = self.container_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()
        self.cards = {}

        count = self.settings.get_history_count()
        items = self.controller.get_history()[:count]
        # from older to yunger because insertWidget(0) will inverte order
        for item in reversed(items):
            self._add_card(item, start_download=False)


    """ ====================
        COOKIES FEEDBACK
      =================== """

    # update UI cookies visual feedback
    def _update_cookie_ui(self):
        if cookies_exists():
            # that will need to be translated on location update
            self.cookies_status_label.setText("Cookies: OK")
            self.cookies_status_label.setStyleSheet("color: #4CAF50;")
            self.remove_cookies_btn.setEnabled(True)
        else:
            # that will need to be translated on location update
            self.cookies_status_label.setText("Cookies: NÃO CONFIGURADO")
            self.cookies_status_label.setStyleSheet("color: #F44336;")
            self.remove_cookies_btn.setEnabled(False)

    # import cookies function
    def _import_cookies(self):
        # that will need to be translated on location update
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar cookies.txt",
            "",
            "Text Files (*.txt)"
        )
        if not file:
            return

        try:
            shutil.copy(file, get_cookies_path())
            # apply permissions
            secure_cookies_file(get_cookies_path())
            # that will need to be translated on location update
            self._safe_message("Sucesso", "Cookies importados com segurança!")
            self._update_cookie_ui()
        except Exception as e:
            self._safe_error("Erro", str(e))

    # remove cookies function
    def _remove_cookies(self):
        try:
            path = get_cookies_path()
            if os.path.exists(path):
                os.remove(path)
                # that will need to be translated on location update
                self._safe_message("Removido", "Cookies removidos.")
            else:
                # that will need to be translated on location update
                self._safe_message("Info", "Nenhum cookie encontrado.")
            self._update_cookie_ui()
        except Exception as e:
            self._safe_error("Erro", str(e))


    """ =================
        HISTORY CARDS
      ================ """

    # add history cards to UI
    def _add_card(self, item, start_download=True):
        card = DownloadCard(item)
        self.cards[item.id] = card
        self.container_layout.insertWidget(0, card)

        # buttons available on all cards
        card.on_copy = lambda _i=item: self._copy_link(_i)
        card.on_retry = lambda _i=item, _c=card: self._retry_download(_i, _c)
        card.on_remove = lambda _i=item, _c=card: self._remove_from_history(_i, _c)

        # call the start_download UI feedback by default
        if start_download:
            self._start_download(item, card)


    """ =====================
        DOWNLOAD DIALOG
      ==================== """
    
    # call download_dialog class
    def _open_download_dialog(self):
        # block if hasn't cookie file
        if not cookies_exists():
            # that need to be translated on location update
            self._safe_error(
                "Cookies necessários",
                "Você precisa importar o arquivo cookies.txt antes de baixar vídeos."
            )
            return

        dialog = DownloadDialog(self)
        if dialog.exec():
            # can return 1 item or N (in case is a youtube playlist)
            for item in dialog.get_results():
                self.controller.add_item(item)
                self._add_card(item, start_download=True)


    """ =======================
        COPY LINK / TRY AGAIN
      ====================== """

    # copy original video link UI button function
    def _copy_link(self, item):
        url = getattr(item, "url", "") or ""
        if url:
            QApplication.clipboard().setText(url)

    # if was ocurred error or cancelled, is that the retry UI button function
    def _retry_download(self, item, card):
        item.status = "pending"
        item.file_path = None
        self._start_download(item, card)
        self.controller.update_item(item)

    # function to UI remove from story button
    def _remove_from_history(self, item, card):
        # show remove warning
        if not self.settings.get_skip_remove_confirm():
            box = QMessageBox(self)
            # that need to be translated on location update
            box.setWindowTitle("Remover do histórico")
            box.setIcon(QMessageBox.Question)
            # that need to be translated on location update
            box.setText(
                f'Remover "{item.original_title}" da lista?\n\n'
                f'(O arquivo já baixado NÃO será apagado do disco.)'
            )
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)

            from PySide6.QtWidgets import QCheckBox
            # that need to be translated on location update
            dont_ask = QCheckBox("Não exibir este aviso novamente")
            box.setCheckBox(dont_ask)

            reply = box.exec()
            if dont_ask.isChecked():
                self.settings.set_skip_remove_confirm(True)
            if reply != QMessageBox.Yes:
                return 

        # check if is active on queue or downloading
        is_active = self.download_service.is_active(item.id)

        if is_active:
            # set remotion to after emit cancell signal 
            self._pending_removal.add(item.id)
            self.download_service.cancel_download(item.id)
            # the ui card will be removed by _on_download_cancelled function when signal arrives
        else:
            # if the download is not finished (complete/error/cancelled): remove imediatly
            self.controller.remove_item(item)
            self.cards.pop(item.id, None)
            self.container_layout.removeWidget(card)
            card.deleteLater()


    """ ===========================
        STAR DOWNLOAD UNIQUE QUEUE
      ========================== """
    def _start_download(self, item, card):
        # etry queue - card status "downloading" when really start download (beacause maybe need to wait other downloads)
        card.update_status("queued")

        self.download_service.start_download(
            item,
            on_progress=lambda v, _id=item.id: self.sig_progress.emit(_id, int(v)),
            on_finished=lambda i: self.sig_finished.emit(i),
            on_error=lambda i, m: self.sig_error.emit(i, m),
            on_cancel=lambda i: self.sig_cancelled.emit(i),
        )

        # cacelling download
        card.on_cancel = lambda: self.download_service.cancel_download(item.id)
        

    """ ===============================
        CALLBACKS OF UI THREAD SLOTS
      ============================== """
    # creat ui componet of download loading bar
    @Slot(str, int)
    def _on_progress_ui(self, item_id, percent):
        card = self.cards.get(item_id)
        if not card:
            return
        card.mark_downloading()
        card.update_progress(percent)

    # set donwload finished to UI feedback
    def _on_download_finished(self, item):
        card = self.cards.get(item.id)
        if card:
            card.update_status("completed")
        self.controller.update_item(item)

    # set download error to UI feedback
    def _on_download_error(self, item, msg):
        card = self.cards.get(item.id)
        if card:
            card.update_status("error")
        self.controller.update_item(item)
        self._safe_error("Erro", msg)

    # set download cancelled to UI feedback
    def _on_download_cancelled(self, item):
        if item.id in self._pending_removal:
            # when was cancelled faster tha ui - remove card and history relacionated data
            self._pending_removal.discard(item.id)
            card = self.cards.pop(item.id, None)
            self.controller.remove_item(item)
            if card:
                self.container_layout.removeWidget(card)
                card.deleteLater()
        else:
            # canceled by ui cancell button
            card = self.cards.get(item.id)
            if card:
                card.update_status("cancelled")
            self.controller.update_item(item)


    """ =====================
        SAFER UI FALLBACKS
      ==================== """
    
    # template friendly message text box
    def _safe_message(self, title, msg):
        if QThread.currentThread() == self.thread():
            QMessageBox.information(self, title, msg)
        else:
            QMetaObject.invokeMethod(self, "_show_message_box",
                                    Qt.QueuedConnection,
                                    Q_ARG(str, title),
                                    Q_ARG(str, msg),
                                    Q_ARG(int, QMessageBox.Information))

    # template friendly error text box
    def _safe_error(self, title, msg):
        if QThread.currentThread() == self.thread():
            QMessageBox.critical(self, title, msg)
        else:
            QMetaObject.invokeMethod(self, "_show_message_box",
                                    Qt.QueuedConnection,
                                    Q_ARG(str, title),
                                    Q_ARG(str, msg),
                                    Q_ARG(int, QMessageBox.Critical))

    # set UI text box component
    @Slot(str, str, int)
    def _show_message_box(self, title, msg, icon):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.setIcon(icon)
        box.exec()