# Translate and revise

"""
Testes para services/download_service.py (DownloadService)

Estratégia: QThread e DownloadWorker são substituídos por duplos de teste
síncronos (FakeThread / FakeWorker) que implementam a mesma interface de
sinais (connect/emit) usada pelo código real, mas executam tudo de forma
determinística, sem threads de verdade. Isso evita testes lentos/flaky e
permite disparar manualmente os sinais (finished/error/cancelled/progress)
para simular o que aconteceria em segundo plano.

Cobrem:
    - start_download() / fila com limite de downloads simultâneos (max_downloads)
    - processamento da fila quando um download termina/erra/cancela
    - handlers (_handle_finished/_handle_error/_handle_cancel) e resiliência
      a exceções lançadas pelos callbacks do consumidor
    - cancel_download() nos dois cenários: em execução vs. ainda na fila
    - shutdown(): limpeza da fila, cancelamento de workers ativos, quit/wait
      das threads, e tolerância a exceções durante o processo
    - reentrância do RLock quando um worker "termina" de forma síncrona
      dentro da própria chamada de start_download
"""

import pytest

from services import download_service as ds
from services.download_service import DownloadService


# ---------------------------------------------------------------------------
# Duplos de teste (fakes) para QThread e DownloadWorker
# ---------------------------------------------------------------------------

class FakeSignal:
    """Substitui um Signal do Qt: connect/emit síncronos e diretos."""
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class FakeThread:
    """Substitui QThread: start() dispara 'started' na hora (sem thread real)."""
    def __init__(self):
        self.started = FakeSignal()
        self.finished = FakeSignal()
        self.quit_called = False
        self.wait_called_with = None
        self.delete_later_called = False

    def start(self):
        self.started.emit()

    def quit(self):
        self.quit_called = True
        self.finished.emit()

    def wait(self, timeout=None):
        self.wait_called_with = timeout
        return True

    def deleteLater(self):
        self.delete_later_called = True


class FakeWorker:
    """Substitui DownloadWorker: run()/cancel() controláveis pelo teste."""
    def __init__(self, item, run_behavior=None):
        self.item = item
        self.progress = FakeSignal()
        self.finished = FakeSignal()
        self.error = FakeSignal()
        self.cancelled = FakeSignal()
        self.run_called = False
        self.cancel_called = False
        self.cancel_raises = None
        self._run_behavior = run_behavior
        self.moveToThread_called_with = None
        self.delete_later_called = False

    def moveToThread(self, thread):
        self.moveToThread_called_with = thread

    def run(self):
        self.run_called = True
        if self._run_behavior:
            self._run_behavior(self)

    def cancel(self):
        self.cancel_called = True
        if self.cancel_raises:
            raise self.cancel_raises

    def deleteLater(self):
        self.delete_later_called = True


class FakeWorkerFactory:
    """Substitui a classe DownloadWorker: cria FakeWorker por item.id e
    permite registrar um comportamento customizado para run()."""
    def __init__(self):
        self.created = {}
        self.behaviors = {}

    def register_behavior(self, item_id, behavior):
        self.behaviors[item_id] = behavior

    def __call__(self, item):
        worker = FakeWorker(item, self.behaviors.get(item.id))
        self.created[item.id] = worker
        return worker


class FakeItem:
    def __init__(self, item_id, **kwargs):
        self.id = item_id
        self.status = kwargs.get("status", "queued")
        self.title = kwargs.get("title", f"item-{item_id}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def worker_factory(monkeypatch):
    factory = FakeWorkerFactory()
    monkeypatch.setattr(ds, "QThread", FakeThread)
    monkeypatch.setattr(ds, "DownloadWorker", factory)
    return factory


@pytest.fixture
def service(worker_factory):
    return DownloadService()


def make_callbacks():
    """Retorna callbacks de teste que registram suas chamadas em listas."""
    calls = {"progress": [], "finished": [], "error": [], "cancel": []}

    def on_progress(p):
        calls["progress"].append(p)

    def on_finished(item):
        calls["finished"].append(item)

    def on_error(item, msg):
        calls["error"].append((item, msg))

    def on_cancel(item):
        calls["cancel"].append(item)

    return calls, on_progress, on_finished, on_error, on_cancel


# ---------------------------------------------------------------------------
# start_download / fila básica
# ---------------------------------------------------------------------------

class TestStartDownload:

    def test_starts_thread_immediately_when_under_limit(self, service, worker_factory):
        item = FakeItem(1)
        calls, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        assert worker.run_called is True
        assert worker.moveToThread_called_with is service.threads[1]
        assert service.running == 1
        assert 1 in service.threads
        assert 1 in service.workers
        assert len(service.queue) == 0

    def test_respects_max_downloads_limit(self, service, worker_factory):
        for i in range(1, 5):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)

        # apenas 3 downloads simultâneos, o 4º fica na fila
        assert service.running == 3
        assert len(service.queue) == 1
        assert set(service.threads.keys()) == {1, 2, 3}
        assert 4 not in worker_factory.created  # thread/worker ainda não criados

    def test_queue_holds_full_registration_data(self, service, worker_factory):
        for i in range(1, 5):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)

        queued_entry = service.queue[0]
        assert queued_entry["item"].id == 4
        assert callable(queued_entry["on_progress"])
        assert callable(queued_entry["on_finished"])

    def test_progress_signal_forwarded_to_callback(self, service, worker_factory):
        item = FakeItem(1)
        calls, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.progress.emit(42)
        assert calls["progress"] == [42]


# ---------------------------------------------------------------------------
# Conclusão de download (finished) e avanço da fila
# ---------------------------------------------------------------------------

class TestFinishedFlow:

    def test_finished_invokes_callback_and_frees_slot(self, service, worker_factory):
        item = FakeItem(1)
        calls, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.finished.emit(item)

        assert calls["finished"] == [item]
        assert service.running == 0
        assert 1 not in service.threads
        assert 1 not in service.workers

    def test_finished_quits_thread_and_cleans_references(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        thread = service.threads[1]
        worker = worker_factory.created[1]
        worker.finished.emit(item)

        assert thread.quit_called is True
        assert thread.delete_later_called is True
        assert worker.delete_later_called is True

    def test_finished_processes_next_queued_item(self, service, worker_factory):
        items = [FakeItem(i) for i in range(1, 5)]
        all_calls = []
        for item in items:
            calls, *cbs = make_callbacks()
            all_calls.append(calls)
            service.start_download(item, *cbs)

        assert len(service.queue) == 1  # item 4 esperando

        worker1 = worker_factory.created[1]
        worker1.finished.emit(items[0])

        # item 4 deve ter sido promovido e seu worker iniciado
        assert len(service.queue) == 0
        assert 4 in worker_factory.created
        assert worker_factory.created[4].run_called is True
        assert service.running == 3
        assert set(service.threads.keys()) == {2, 3, 4}

    def test_callback_exception_does_not_prevent_finalization(self, service, worker_factory, capsys):
        item = FakeItem(1)

        def raising_on_finished(item):
            raise RuntimeError("callback quebrado")

        service.start_download(item, lambda p: None, raising_on_finished, lambda i, m: None, lambda i: None)

        worker = worker_factory.created[1]
        worker.finished.emit(item)

        # mesmo com exceção no callback, o slot deve ser liberado
        assert service.running == 0
        assert 1 not in service.workers
        captured = capsys.readouterr()
        assert "Erro no callback finished" in captured.out


# ---------------------------------------------------------------------------
# Fluxo de erro
# ---------------------------------------------------------------------------

class TestErrorFlow:

    def test_error_invokes_callback_with_message_and_frees_slot(self, service, worker_factory):
        item = FakeItem(1)
        calls, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.error.emit(item, "algo deu errado")

        assert calls["error"] == [(item, "algo deu errado")]
        assert service.running == 0
        assert 1 not in service.workers

    def test_error_quits_thread(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        thread = service.threads[1]
        worker = worker_factory.created[1]
        worker.error.emit(item, "falhou")

        assert thread.quit_called is True

    def test_error_callback_exception_still_finalizes(self, service, worker_factory, capsys):
        item = FakeItem(1)

        def raising_on_error(item, msg):
            raise ValueError("boom")

        service.start_download(item, lambda p: None, lambda i: None, raising_on_error, lambda i: None)
        worker = worker_factory.created[1]
        worker.error.emit(item, "falhou")

        assert service.running == 0
        captured = capsys.readouterr()
        assert "Erro no callback error" in captured.out


# ---------------------------------------------------------------------------
# Fluxo de cancelamento via sinal do worker (download já em execução)
# ---------------------------------------------------------------------------

class TestCancelledSignalFlow:

    def test_cancelled_signal_invokes_callback_and_frees_slot(self, service, worker_factory):
        item = FakeItem(1)
        calls, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.cancelled.emit(item)

        assert calls["cancel"] == [item]
        assert service.running == 0
        assert 1 not in service.workers

    def test_cancelled_signal_callback_exception_still_finalizes(self, service, worker_factory, capsys):
        item = FakeItem(1)

        def raising_on_cancel(item):
            raise RuntimeError("callback cancel quebrado")

        service.start_download(item, lambda p: None, lambda i: None, lambda i, m: None, raising_on_cancel)
        worker = worker_factory.created[1]
        worker.cancelled.emit(item)

        assert service.running == 0
        captured = capsys.readouterr()
        assert "Erro no callback cancel" in captured.out


# ---------------------------------------------------------------------------
# cancel_download()
# ---------------------------------------------------------------------------

class TestCancelDownload:

    def test_cancel_running_download_calls_worker_cancel(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        service.cancel_download(1)

        worker = worker_factory.created[1]
        assert worker.cancel_called is True
        # cancelar não finaliza por conta própria: isso só acontece quando o
        # worker realmente emitir o sinal "cancelled"
        assert service.running == 1
        assert 1 in service.workers

    def test_cancel_running_download_swallows_worker_exception(self, service, worker_factory, capsys):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.cancel_raises = RuntimeError("cancel falhou")

        service.cancel_download(1)  # não deve propagar exceção

        captured = capsys.readouterr()
        assert "Erro ao cancelar" in captured.out

    def test_cancel_queued_download_removes_from_queue_and_notifies(self, service, worker_factory):
        items = [FakeItem(i) for i in range(1, 5)]
        all_calls = []
        for item in items:
            calls, *cbs = make_callbacks()
            all_calls.append(calls)
            service.start_download(item, *cbs)

        # item 4 está na fila (não iniciado)
        assert len(service.queue) == 1

        service.cancel_download(4)

        assert len(service.queue) == 0
        assert items[3].status == "cancelled"
        assert all_calls[3]["cancel"] == [items[3]]
        # cancelar um item da fila não deve afetar o contador de execução
        assert service.running == 3

    def test_cancel_queued_download_callback_exception_is_caught(self, service, worker_factory, capsys):
        items = [FakeItem(i) for i in range(1, 5)]
        for i, item in enumerate(items):
            if i == 3:
                def raising_on_cancel(item):
                    raise RuntimeError("callback fila quebrado")
                service.start_download(item, lambda p: None, lambda i: None,
                                        lambda i, m: None, raising_on_cancel)
            else:
                _, *cbs = make_callbacks()
                service.start_download(item, *cbs)

        service.cancel_download(4)  # não deve propagar

        captured = capsys.readouterr()
        assert "Erro no callback cancel (fila)" in captured.out

    def test_cancel_unknown_item_id_is_noop(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        # não deve lançar exceção nem alterar o estado
        service.cancel_download(999)

        assert service.running == 1
        assert len(service.queue) == 0


# ---------------------------------------------------------------------------
# shutdown()
# ---------------------------------------------------------------------------

class TestShutdown:

    def test_shutdown_clears_queue(self, service, worker_factory):
        for i in range(1, 5):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)

        assert len(service.queue) == 1
        service.shutdown()
        assert len(service.queue) == 0

    def test_shutdown_cancels_all_active_workers(self, service, worker_factory):
        for i in range(1, 4):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)

        service.shutdown()

        for i in range(1, 4):
            assert worker_factory.created[i].cancel_called is True

    def test_shutdown_quits_and_waits_all_threads(self, service, worker_factory):
        threads = []
        for i in range(1, 4):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)
            threads.append(service.threads[i])

        service.shutdown(timeout_ms=1234)

        for t in threads:
            assert t.quit_called is True
            assert t.wait_called_with == 1234

    def test_shutdown_thread_finished_signal_cleans_up_references(self, service, worker_factory):
        for i in range(1, 4):
            item = FakeItem(i)
            _, *cbs = make_callbacks()
            service.start_download(item, *cbs)

        service.shutdown()

        # nosso FakeThread.quit() dispara 'finished' sincronamente, então a
        # limpeza via _on_thread_finished deve ter ocorrido
        assert service.threads == {}
        assert service.workers == {}

    def test_shutdown_swallows_cancel_exceptions(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        worker = worker_factory.created[1]
        worker.cancel_raises = RuntimeError("boom")

        # não deve propagar, mesmo com cancel() falhando internamente
        service.shutdown()

    def test_shutdown_swallows_thread_quit_exceptions(self, service, worker_factory):
        item = FakeItem(1)
        _, *cbs = make_callbacks()
        service.start_download(item, *cbs)

        thread = service.threads[1]

        def raise_on_quit():
            raise RuntimeError("quit falhou")

        thread.quit = raise_on_quit

        # não deve propagar exceção
        service.shutdown()

    def test_shutdown_with_no_active_downloads_does_nothing_harmful(self, service, worker_factory):
        # nenhum download iniciado
        service.shutdown()
        assert service.queue == service.queue  # apenas garante que não lança


# ---------------------------------------------------------------------------
# Reentrância do RLock (worker "terminando" de forma síncrona)
# ---------------------------------------------------------------------------

class TestLockReentrancy:

    def test_worker_finishing_synchronously_during_start_does_not_deadlock(self, service, worker_factory):
        """Se o worker.run() (chamado sincronamente por thread.start()) emitir
        'finished' imediatamente -- como pode acontecer em testes ou em downloads
        instantâneos -- o RLock reentrante deve permitir que _finalize_download
        e _process_queue rodem sem travar."""
        item1 = FakeItem(1)

        def immediately_finish(worker):
            worker.finished.emit(worker.item)

        worker_factory.register_behavior(1, immediately_finish)

        calls, *cbs = make_callbacks()
        # não deve travar (deadlock) nem lançar exceção
        service.start_download(item1, *cbs)

        assert calls["finished"] == [item1]
        assert service.running == 0
        assert 1 not in service.workers

    def test_chain_of_synchronous_completions_processes_full_queue(self, service, worker_factory):
        """Todos os itens 'terminam' instantaneamente ao rodar; mesmo assim a
        fila inteira deve ser processada sem estouro de pilha nem deadlock."""
        items = [FakeItem(i) for i in range(1, 6)]

        def immediately_finish(worker):
            worker.finished.emit(worker.item)

        for item in items:
            worker_factory.register_behavior(item.id, immediately_finish)

        all_calls = []
        for item in items:
            calls, *cbs = make_callbacks()
            all_calls.append(calls)
            service.start_download(item, *cbs)

        assert service.running == 0
        assert len(service.queue) == 0
        for calls, item in zip(all_calls, items):
            assert calls["finished"] == [item]