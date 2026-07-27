# ui/main_window.py

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
    check_and_update, check_app_update, get_installed_version_ytdlp, APP_VERSION,
)

from ui.components.download_card import DownloadCard
from ui.download_dialog import DownloadDialog

from core.utils import get_cookies_path, cookies_exists, secure_cookies_file
from storage.settings_store import SettingsStore, ALLOWED_HISTORY_COUNTS


# ==========================
# WORKER: busca atualizações (yt-dlp + release do app no GitHub)
# ==========================
class UpdateCheckWorker(QObject):
    finished = Signal(str, bool, object)  # ytdlp_msg, app_update_disponivel, versao

    def run(self):
        try:
            _ok, ytdlp_msg = check_and_update()
        except Exception as e:
            ytdlp_msg = f"Erro ao atualizar yt-dlp: {e}"
        available, latest = check_app_update()
        self.finished.emit(ytdlp_msg, available, latest)


# ==========================
# MAIN WINDOW
# ==========================
class MainWindow(QMainWindow):
    # sinais para atualização da UI a partir das threads de download
    sig_progress = Signal(str, int)
    sig_finished = Signal(object)
    sig_error = Signal(object, str)
    sig_cancelled = Signal(object)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Video Downloader")
        self.setMinimumSize(900, 600)

        self.controller = DownloadController()
        self.download_service = DownloadService()
        self.settings = SettingsStore()

        self.cards = {}
        # itens aguardando cancelamento para depois serem removidos da UI
        self._pending_removal = set()

        # conecta sinais de download (entregues na thread de UI via QueuedConnection)
        self.sig_progress.connect(self._on_progress_ui)
        self.sig_finished.connect(self._on_download_finished)
        self.sig_error.connect(self._on_download_error)
        self.sig_cancelled.connect(self._on_download_cancelled)

        self._setup_ui()
        self._render_history()
        self._load_version()
        self._update_cookie_ui()

    # -------------------------
    # FECHAMENTO LIMPO
    # -------------------------
    def closeEvent(self, event):
        # encerra downloads ativos para não destruir QThreads em execução
        try:
            self.download_service.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

    # -------------------------
    # UI
    # -------------------------
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        # TOP BAR
        top_bar = QHBoxLayout()

        self.new_button = QPushButton("+ Colar link")
        self.new_button.clicked.connect(self._open_download_dialog)

        self.update_button = QPushButton("Buscar atualizações")
        self.update_button.clicked.connect(self._check_updates)

        self.import_cookies_btn = QPushButton("Importar cookies")
        self.import_cookies_btn.clicked.connect(self._import_cookies)

        self.remove_cookies_btn = QPushButton("Remover cookies")
        self.remove_cookies_btn.clicked.connect(self._remove_cookies)

        self.cookies_status_label = QLabel("Cookies: ...")

        # seletor de quantidade do histórico
        self.history_label = QLabel("Histórico:")
        self.history_count_selector = QComboBox()
        for n in ALLOWED_HISTORY_COUNTS:
            self.history_count_selector.addItem(str(n), n)
        current = self.settings.get_history_count()
        idx = self.history_count_selector.findData(current)
        if idx >= 0:
            self.history_count_selector.setCurrentIndex(idx)
        self.history_count_selector.currentIndexChanged.connect(self._on_history_count_changed)

        self.version_label = QPushButton("yt-dlp: ...")
        self.version_label.setEnabled(False)

        top_bar.addWidget(self.new_button)
        top_bar.addWidget(self.update_button)
        top_bar.addWidget(self.import_cookies_btn)
        top_bar.addWidget(self.remove_cookies_btn)
        top_bar.addWidget(self.cookies_status_label)
        top_bar.addStretch()
        top_bar.addWidget(self.history_label)
        top_bar.addWidget(self.history_count_selector)
        top_bar.addWidget(self.version_label)

        layout.addLayout(top_bar)

        # SCROLL AREA PARA CARDS
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.container_layout = QVBoxLayout()
        self.container.setLayout(self.container_layout)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

    # -------------------------
    # VERSION & UPDATE
    # -------------------------
    def _load_version(self):
        version = get_installed_version_ytdlp()
        self.version_label.setText(f"yt-dlp: {version}")

    def _check_updates(self):
        # roda em thread para não congelar a UI (download do yt-dlp + API GitHub)
        self.update_button.setEnabled(False)
        self.update_button.setText("Buscando...")

        self._upd_thread = QThread()
        self._upd_worker = UpdateCheckWorker()
        self._upd_worker.moveToThread(self._upd_thread)
        self._upd_thread.started.connect(self._upd_worker.run)
        self._upd_worker.finished.connect(self._on_updates_checked)
        self._upd_worker.finished.connect(self._upd_thread.quit)
        self._upd_thread.finished.connect(self._upd_thread.deleteLater)
        self._upd_thread.start()

    @Slot(str, bool, object)
    def _on_updates_checked(self, ytdlp_msg, app_update_available, latest_version):
        self.update_button.setEnabled(True)
        self.update_button.setText("Buscar atualizações")
        self._load_version()

        if app_update_available and latest_version:
            self._safe_message(
                "Atualização disponível",
                f"Nova versão ({latest_version}) disponível para download. "
                f"Atualize para novos recursos e correções.\n\n"
                f"yt-dlp: {ytdlp_msg}",
            )
        else:
            self._safe_message(
                "Atualizações",
                f"yt-dlp: {ytdlp_msg}\n\n"
                f"O app já está na versão mais recente (v{APP_VERSION}).",
            )

    # -------------------------
    # HISTORY
    # -------------------------
    def _on_history_count_changed(self):
        count = self.history_count_selector.currentData()
        if count in ALLOWED_HISTORY_COUNTS:
            self.settings.set_history_count(count)
            self._render_history()

    def _render_history(self):
        """(Re)desenha a lista de cards respeitando a quantidade escolhida."""
        # limpa cards atuais
        while self.container_layout.count():
            child = self.container_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()
        self.cards = {}

        count = self.settings.get_history_count()
        items = self.controller.get_history()[:count]
        # do mais antigo para o mais recente, pois insertWidget(0) inverte
        for item in reversed(items):
            self._add_card(item, start_download=False)

    # -------------------------
    # COOKIES
    # -------------------------
    def _update_cookie_ui(self):
        if cookies_exists():
            self.cookies_status_label.setText("Cookies: OK")
            self.cookies_status_label.setStyleSheet("color: #4CAF50;")
            self.remove_cookies_btn.setEnabled(True)
        else:
            self.cookies_status_label.setText("Cookies: NÃO CONFIGURADO")
            self.cookies_status_label.setStyleSheet("color: #F44336;")
            self.remove_cookies_btn.setEnabled(False)

    def _import_cookies(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar cookies.txt",
            "",
            "Text Files (*.txt)"
        )
        if not file:
            return

        try:
            os.makedirs("data", exist_ok=True)
            shutil.copy(file, get_cookies_path())
            secure_cookies_file(get_cookies_path())   # aplica permissões
            self._safe_message("Sucesso", "Cookies importados com segurança!")
            self._update_cookie_ui()
        except Exception as e:
            self._safe_error("Erro", str(e))

    def _remove_cookies(self):
        try:
            path = get_cookies_path()
            if os.path.exists(path):
                os.remove(path)
                self._safe_message("Removido", "Cookies removidos.")
            else:
                self._safe_message("Info", "Nenhum cookie encontrado.")
            self._update_cookie_ui()
        except Exception as e:
            self._safe_error("Erro", str(e))

    # -------------------------
    # CARDS
    # -------------------------
    def _add_card(self, item, start_download=True):
        card = DownloadCard(item)
        self.cards[item.id] = card
        self.container_layout.insertWidget(0, card)

        # botões sempre disponíveis no card
        card.on_copy = lambda _i=item: self._copy_link(_i)
        card.on_retry = lambda _i=item, _c=card: self._retry_download(_i, _c)
        card.on_remove = lambda _i=item, _c=card: self._remove_from_history(_i, _c)

        if start_download:
            self._start_download(item, card)

    # -------------------------
    # DOWNLOAD DIALOG
    # -------------------------
    def _open_download_dialog(self):
        if not cookies_exists():
            self._safe_error(
                "Cookies necessários",
                "Você precisa importar o arquivo cookies.txt antes de baixar vídeos."
            )
            return

        dialog = DownloadDialog(self)
        if dialog.exec():
            # pode retornar 1 item (vídeo único) ou N (playlist do YouTube)
            for item in dialog.get_results():
                self.controller.add_item(item)
                self._add_card(item, start_download=True)

    # -------------------------
    # COPIAR LINK / TENTAR NOVAMENTE
    # -------------------------
    def _copy_link(self, item):
        url = getattr(item, "url", "") or ""
        if url:
            QApplication.clipboard().setText(url)

    def _retry_download(self, item, card):
        item.status = "pending"
        item.file_path = None
        self._start_download(item, card)
        self.controller.update_item(item)

    def _remove_from_history(self, item, card):
        if not self.settings.get_skip_remove_confirm():
            box = QMessageBox(self)
            box.setWindowTitle("Remover do histórico")
            box.setIcon(QMessageBox.Question)
            box.setText(
                f'Remover "{item.original_title}" da lista?\n\n'
                f'(O arquivo já baixado NÃO será apagado do disco.)'
            )
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)

            from PySide6.QtWidgets import QCheckBox
            dont_ask = QCheckBox("Não exibir este aviso novamente")
            box.setCheckBox(dont_ask)

            reply = box.exec()
            if dont_ask.isChecked():
                self.settings.set_skip_remove_confirm(True)
            if reply != QMessageBox.Yes:
                return

        # Verifica se está ativo (baixando ou na fila)
        is_active = (
            item.id in self.download_service.workers or
            any(d["item"].id == item.id for d in self.download_service.queue)
        )

        if is_active:
            # Marca para remoção após o cancelamento ser confirmado pelo sinal
            self._pending_removal.add(item.id)
            self.download_service.cancel_download(item.id)
            # O card será removido em _on_download_cancelled quando o sinal chegar
        else:
            # Download já terminou (completed/error/cancelled): remove imediatamente
            self.controller.remove_item(item)
            self.cards.pop(item.id, None)
            self.container_layout.removeWidget(card)
            card.deleteLater()

    # -------------------------
    # START DOWNLOAD (FILA ÚNICA, MÁX 3)
    # -------------------------
    def _start_download(self, item, card):
        # entra na fila; o card vira "downloading" no primeiro progresso real
        card.update_status("queued")

        self.download_service.start_download(
            item,
            on_progress=lambda v, _id=item.id: self.sig_progress.emit(_id, int(v)),
            on_finished=lambda i: self.sig_finished.emit(i),
            on_error=lambda i, m: self.sig_error.emit(i, m),
            on_cancel=lambda i: self.sig_cancelled.emit(i),
        )

        # cancelamento
        card.on_cancel = lambda: self.download_service.cancel_download(item.id)

    # -------------------------
    # CALLBACKS (SLOTS NA THREAD DE UI)
    # -------------------------
    @Slot(str, int)
    def _on_progress_ui(self, item_id, percent):
        card = self.cards.get(item_id)
        if not card:
            return
        card.mark_downloading()   # garante a barra visível (idempotente)
        card.update_progress(percent)

    def _on_download_finished(self, item):
        card = self.cards.get(item.id)
        if card:
            card.update_status("completed")
        self.controller.update_item(item)

    def _on_download_error(self, item, msg):
        card = self.cards.get(item.id)
        if card:
            card.update_status("error")
        self.controller.update_item(item)
        self._safe_error("Erro", msg)

    def _on_download_cancelled(self, item):
        if item.id in self._pending_removal:
            # Remoção solicitada pelo usuário: apaga card e histórico agora
            self._pending_removal.discard(item.id)
            card = self.cards.pop(item.id, None)
            self.controller.remove_item(item)
            if card:
                self.container_layout.removeWidget(card)
                card.deleteLater()
        else:
            # Cancelamento normal (botão Cancelar do card)
            card = self.cards.get(item.id)
            if card:
                card.update_status("cancelled")
            self.controller.update_item(item)

    # -------------------------
    # SAFE UI
    # -------------------------
    def _safe_message(self, title, msg):
        if QThread.currentThread() == self.thread():
            QMessageBox.information(self, title, msg)
        else:
            QMetaObject.invokeMethod(self, "_show_message_box",
                                    Qt.QueuedConnection,
                                    Q_ARG(str, title),
                                    Q_ARG(str, msg),
                                    Q_ARG(int, QMessageBox.Information))

    def _safe_error(self, title, msg):
        if QThread.currentThread() == self.thread():
            QMessageBox.critical(self, title, msg)
        else:
            QMetaObject.invokeMethod(self, "_show_message_box",
                                    Qt.QueuedConnection,
                                    Q_ARG(str, title),
                                    Q_ARG(str, msg),
                                    Q_ARG(int, QMessageBox.Critical))

    @Slot(str, str, int)
    def _show_message_box(self, title, msg, icon):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.setIcon(icon)
        box.exec()