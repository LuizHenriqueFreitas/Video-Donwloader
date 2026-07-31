# services/download_service.py

""" Here yoou will find:
    - Thread managemant by donwload;
    - Queue management;
    - Start_Download() public api;
    - Download handlers by erros;
    - Download Security implementation to correct close process in case of 
      crash, close app or just cancel a download;
    - get api worker queue data.
"""

from collections import deque
from threading import RLock
from PySide6.QtCore import QThread
from ui.workers.download_worker import DownloadWorker

""" About Logic implemented:

    It manages a single download queue with a limit on simultaneous
    executions (max. 3); remaining tasks wait in the queue.

    Completion handlers are connected as functions (direct connection)
    running within the worker thread itself—allowing the thread to
    terminate cleanly. UI safety is ensured by the consumer
    (MainWindow), whose callbacks merely emit marshaled signals to the
    main thread.

    Since `start_download` (main thread) and the completion handlers
    (worker thread) modify `queue` and `running`, all state mutations
    are protected by an RLock—preventing race conditions that previously
    left items stuck in the queue.

    The API (start_download / queue / running / max_downloads / workers /
    threads / cancel_download) is kept stable for testing purposes.
"""

# main class of this file
class DownloadService:

    # incializer function
    def __init__(self):
        self.threads = {}
        self.workers = {}

        self.queue = deque()

        self.running = 0
        self.max_downloads = 3

        self._lock = RLock()


    """ ========================
          PULIC API FUNCTINO
       ======================= """

    # called to start a new download
    def start_download(self, item, on_progress, on_finished, on_error, on_cancel):
        with self._lock:
            # add new item to download queue
            self.queue.append({
                "item": item,
                "on_progress": on_progress,
                "on_finished": on_finished,
                "on_error": on_error,
                "on_cancel": on_cancel,
            })
            self._process_queue()


    """ ===========================
        QUEUE MANAGEMANT FUNCTION
      =========================== """

    # keep queue process running
    # this function create a new thread to each download on queue
    def _process_queue(self):
        with self._lock:
            while self.running < self.max_downloads and self.queue:
                data = self.queue.popleft()
                item = data["item"]

                self.running += 1
                self._start_thread(
                    item,
                    data["on_progress"],
                    data["on_finished"],
                    data["on_error"],
                    data["on_cancel"],
                )


    """ =========================
        THREAD STARTER FUNCTION
      ======================== """

    # start a thread to manage the download
    def _start_thread(self, item, on_progress, on_finished, on_error, on_cancel):

        # instanciate a QtCore thread
        thread = QThread()
        # instanciate a downloader_worker
        worker = DownloadWorker(item)

        # move worker to the new thread
        worker.moveToThread(thread)

        # configure item by id
        self.threads[item.id] = thread
        self.workers[item.id] = worker

        # start tharead
        thread.started.connect(worker.run_download)

        # conncet worker progress signal to on_progress local var
        worker.progress.connect(on_progress)

        # connect worker finish signal with finish handler
        worker.finished.connect(
            lambda emitted_item: self._handle_finished(emitted_item, on_finished)
        )
        # connect worker error signal with error handler
        worker.error.connect(
            lambda emitted_item, msg: self._handle_error(emitted_item, on_error, msg)
        )
        # connect worker cancelled signal with cancelled handler
        worker.cancelled.connect(
            lambda emitted_item: self._handle_cancel(emitted_item, on_cancel)
        )

        # terminate the thread when the download finishes, get error or was cancelled
        worker.finished.connect(lambda *_: thread.quit())
        worker.error.connect(lambda *_: thread.quit())
        worker.cancelled.connect(lambda *_: thread.quit())

        # final cleanup of references when the thread actually terminates.
        thread.finished.connect(lambda: self._on_thread_finished(item.id))
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # thread start function
        thread.start()


    """ ==========================
                HANDLERS
      ========================== """

    # called when worker returns finished signal
    def _handle_finished(self, item, callback):
        try:
            callback(item)
        except Exception as e:
            # debug message
            print(f"Erro no callback finished: {e}")
        finally:
            self._finalize_download(item.id)

    # called when worker returns error signal
    def _handle_error(self, item, callback, msg):
        try:
            callback(item, msg)
        except Exception as e:
            # debug message
            print(f"Erro no callback error: {e}")
        finally:
            self._finalize_download(item.id)

    # called when worker returns cancelled signal
    def _handle_cancel(self, item, callback):
        try:
            callback(item)
        except Exception as e:
            # debug message
            print(f"Erro no callback cancel: {e}")
        finally:
            self._finalize_download(item.id)


    """ ==========================
            FINALIZATION
     ========================== """

    # frees up the slot and processes the next one in the queue
    # usefull to force quit, like cancelled or error exceptions
    def _finalize_download(self, item_id):
        with self._lock:
            if self.running > 0:
                self.running -= 1
            self._process_queue()

    # Remove references only after the thread has actually finished.
    def _on_thread_finished(self, item_id):
        with self._lock:
            self.threads.pop(item_id, None)
            self.workers.pop(item_id, None)


    """ ==========================
            APP SHUTDOWN
      ========================== """

    # cancels everything and waits for the threads to finish, so the app closes without the
    # 'QThread: Destroyed while thread is still running' warning..
    def shutdown(self, timeout_ms=4000):
        with self._lock:
            # clear the queue
            self.queue.clear()
            # get active workers
            active_ids = list(self.workers.keys())
            # get active theads
            threads = list(self.threads.values())

        # cancel donwload for each worker
        for item_id in active_ids:
            try:
                self.cancel_download(item_id)  
            except Exception:
                pass

        # quit each remaining thread
        for thread in threads:
            try:
                thread.quit()
                thread.wait(timeout_ms)
            except Exception:
                pass


    """ =============================
        STATUS QUERY (THAREAD-SAFE)
      ============================ """
    # api to secure main_window acess to workers/queue
    def is_active(self, item_id):
        with self._lock:
            # return true if the item is runnig now or waiting on the queue
            if item_id in self.workers:
                return True
            return any(data["item"].id == item_id for data in self.queue)


    """ ==========================
                CANCELING
      ========================== """
    # cancel a Donwload thread in 2 scenaries
    def cancel_download(self, item_id):

        # 1) if is the donwload on execution
        with self._lock:
            worker = self.workers.get(item_id)

        # cancel worker by item_id
        if worker:
            try:
                worker.cancel()
            except Exception as e:
                print(f"Erro ao cancelar: {e}")
            return

        # 2) Still in the queue: removes it and notifies the UI
        # there's no thread to quit yet
        cancelled_item = None
        on_cancel = None
        with self._lock:
            for i, data in enumerate(self.queue):
                if data["item"].id == item_id:
                    del self.queue[i]
                    cancelled_item = data["item"]
                    cancelled_item.status = "cancelled"
                    on_cancel = data["on_cancel"]
                    break

        if cancelled_item is not None and on_cancel is not None:
            try:
                on_cancel(cancelled_item)
            except Exception as e:
                print(f"Erro no callback cancel (fila): {e}")
