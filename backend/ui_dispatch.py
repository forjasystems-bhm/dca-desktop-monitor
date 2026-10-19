"""Main-thread Tk mailbox. Workers only write to a Python queue."""
import logging
import queue
import threading

logger = logging.getLogger(__name__)

class UiDispatcher:
    def __init__(self, widget):
        self.widget = widget
        self.owner = threading.get_ident()
        self.queue = queue.Queue()
        self.closed = False
        self.running = False
        self.pending = None
        self.token = widget.after(10, self._drain)
        widget.bind('<Destroy>', self._destroyed, add='+')

    def _destroyed(self, event):
        if event.widget is self.widget:
            self.close()

    def post(self, callback):
        if self.closed:
            return False
        self.queue.put(callback)
        return True

    def _drain(self):
        assert threading.get_ident() == self.owner
        self.token = None
        if self.closed:
            return
        # Bound each drain so a busy producer cannot starve the event loop.
        for _ in range(100):
            try:
                callback = self.queue.get_nowait()
            except queue.Empty:
                break
            if not self.closed:
                try:
                    callback()
                except Exception:
                    logger.exception('Falha em callback da interface')
                    raise  # Tk report_callback_exception remains observable.
        if not self.closed:
            self.token = self.widget.after(10, self._drain)

    def run(self, target):
        """Serialize work for a view; coalesce repeated refresh into one rerun."""
        assert threading.get_ident() == self.owner
        if self.closed:
            return
        if self.running:
            self.pending = target
            return
        self.running = True
        def worker():
            try:
                target()
            except Exception as exc:
                logger.exception('Falha em tarefa da interface')
                self.post(lambda error=exc: self.widget.report_callback_exception(
                    type(error), error, error.__traceback__))
            finally:
                self.post(self._finished)
        threading.Thread(target=worker, daemon=True).start()

    def _finished(self):
        self.running = False
        target, self.pending = self.pending, None
        if target is not None:
            self.run(target)

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True
        self.pending = None
        if self.token is not None:
            self.widget.after_cancel(self.token)
            self.token = None
        while True:
            try: self.queue.get_nowait()
            except queue.Empty: break
