
import asyncio
import threading

from PySide6.QtCore import QObject, Signal, Slot
import pypalmsens as ps


class measurement_worker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, instrument, method):
        super().__init__()
        self.instrument = instrument
        self.method = method
        self.manager = None
        self.loop = None
        self.abort_requested = False
        self._state_lock = threading.Lock()

    @Slot()
    def run(self):
        try:
            measurement = asyncio.run(self._measure())
            self.finished.emit(measurement)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            with self._state_lock:
                self.manager = None
                self.loop = None

    async def _measure(self):
        async with await ps.connect_async(instrument=self.instrument) as manager:
            with self._state_lock:
                self.manager = manager
                self.loop = asyncio.get_running_loop()
                abort_requested = self.abort_requested

            manager.validate_method(self.method)

            if abort_requested:
                await manager.abort()
                raise RuntimeError("Measurement aborted")

            def on_data(data):
                self.progress.emit(data)

            return await manager.measure(self.method, callback=on_data)

    @Slot()
    def abort(self):
        with self._state_lock:
            self.abort_requested = True
            manager = self.manager
            loop = self.loop

        if manager is not None and loop is not None:
            asyncio.run_coroutine_threadsafe(manager.abort(), loop)


def collect_params(form_layout, field_names):
    params = {}
    for field in field_names:
        widget = form_layout[field]
        params[field] = widget.text().strip()
    return params
