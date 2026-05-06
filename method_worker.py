
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

    def run(self):
        try:
            with ps.connect(self.instrument) as manager:
                self.manager = manager
                manager.validate_method(self.method)

                def on_data(data):
                    self.progress.emit(data)

                measurement = manager.measure(self.method, callback=on_data)
                self.finished.emit(measurement)
        except Exception as e:
            self.failed.emit(str(e))

    def abort(self):
        if self.manager is not None:
            self.manager.abort()


def collect_params(form_layout, field_names):
    params = {}
    for field in field_names:
        widget = form_layout[field]
        params[field] = widget.text().strip()
    return params