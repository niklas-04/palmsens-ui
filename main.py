import sys

from PySide6.QtCore import QObject, QSize, Signal, Slot, QMetaObject, Qt, QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from graph import graph_panel
from method_config import METHOD_ORDER, METHOD_SPECS, build_method
from method_worker import measurement_worker
import ps_helpers as pslib

PANEL_COLUMNS = 3


APP_STYLESHEET = """
QMainWindow {
    background: #f4f6f8;
}

QToolBar#mainToolbar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #d8dee6;
    spacing: 6px;
    padding: 8px 10px;
}

QToolBar#mainToolbar QToolButton,
QToolBar#graphToolbar QToolButton,
QPushButton {
    background: #ffffff;
    border: 1px solid #c7d0da;
    border-radius: 5px;
    color: #243241;
    padding: 6px 10px;
}

QToolBar#mainToolbar QToolButton:hover,
QToolBar#graphToolbar QToolButton:hover,
QPushButton:hover {
    background: #eef4fa;
    border-color: #8ca3ba;
}

QToolBar#mainToolbar QToolButton:pressed,
QToolBar#graphToolbar QToolButton:pressed,
QPushButton:pressed {
    background: #dce8f3;
}

QToolButton:disabled {
    color: #8a96a3;
    background: #f5f7f9;
    border-color: #d8dee6;
}

QWidget#panelContainer {
    background: #f4f6f8;
}

QFrame#graphPanel {
    background: #ffffff;
    border: 1px solid #d8dee6;
    border-radius: 8px;
}

QLabel#graphPanelTitle {
    color: #1f2a36;
    font-size: 14px;
    font-weight: 700;
}

QToolBar#graphToolbar {
    background: transparent;
    border: 0;
    spacing: 4px;
}

QScrollArea#panelScrollArea {
    background: #f4f6f8;
    border: 0;
}

QLabel#connectionIndicator {
    font-weight: 600;
    padding: 2px 8px;
}

QListWidget,
QComboBox,
QLineEdit {
    background: #ffffff;
    border: 1px solid #c7d0da;
    border-radius: 5px;
    padding: 4px;
    selection-background-color: #2f6f9f;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d8dee6;
}
"""


class connection_indicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("connectionIndicator")
        self.set_status(False)

    # Enheten är egentligen inte ansluten tills mätningar, kanske ändra?
    def set_status(self, is_connected: bool, dev: pslib.discovered_device | None = None):
        if is_connected and dev is not None:
            self.setText(f"Connected to {dev.name}")
            self.setStyleSheet("color: green;")
            return

        self.setText("Disconnected")
        self.setStyleSheet("color: red;")


class device_selection_dialog(QDialog):
    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Device")

        layout = QVBoxLayout(self)
        self.device_list = list_choices()
        self.device_list.set_choice(devices)
        layout.addWidget(self.device_list)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.select_device)
        layout.addWidget(self.connect_button)

        self.selected_device = None

    def select_device(self):
        dev = self.device_list.get_selected_choice()
        if dev is None:
            return

        self.selected_device = dev
        self.accept()


class method_configuration_dialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Run Measurement - {title}")
        self.method = None
        self.field_widgets: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        self.method_combo = QComboBox(self)
        for method_key in METHOD_ORDER:
            spec = METHOD_SPECS[method_key]
            self.method_combo.addItem(spec.label, method_key)
        form_layout.addRow("Method", self.method_combo)

        self.field_form = QFormLayout()
        layout.addLayout(self.field_form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.method_combo.currentIndexChanged.connect(self.rebuild_fields)
        self.rebuild_fields()

    def selected_method_key(self) -> str:
        return self.method_combo.currentData()

    def raw_params(self) -> dict[str, str]:
        return {
            field_key: widget.text().strip()
            for field_key, widget in self.field_widgets.items()
        }

    def rebuild_fields(self):
        while self.field_form.rowCount():
            self.field_form.removeRow(0)

        self.field_widgets.clear()
        spec = METHOD_SPECS[self.selected_method_key()]
        for field in spec.fields:
            widget = QLineEdit(field.default, self)
            self.field_widgets[field.key] = widget
            self.field_form.addRow(field.label, widget)

    def validate_and_accept(self):
        try:
            self.method = build_method(self.selected_method_key(), self.raw_params())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return

        self.accept()


class list_choices(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget)
        self.choices = []

    def set_choice(self, choices):
        self.choices = choices
        self.list_widget.clear()

        for dev in choices:
            self.list_widget.addItem(str(dev.name))

    def get_selected_choice(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.choices):
            return self.choices[row]
        return None


class device_manager(QObject):
    connected = Signal(object)
    disconnected = Signal()
    connection_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.device = None

    def connect_device(self, dev: pslib.discovered_device):
        if self.is_connected:
            return

        self.device = dev
        self.is_connected = True
        self.connected.emit(dev)
        self.connection_changed.emit(True)

    def disconnect_device(self):
        if not self.is_connected or self.device is None:
            return

        self.is_connected = False
        self.device = None
        self.disconnected.emit()
        self.connection_changed.emit(False)


class main_window(QMainWindow):
    worker_progress = Signal(object, object)
    worker_finished = Signal(object, object)
    worker_failed = Signal(object, str)
    worker_thread_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self.panels: list[graph_panel] = []
        self.active_runs: dict[graph_panel, tuple[QThread, measurement_worker]] = {}
        self.stopping_panels: set[graph_panel] = set()
        self.worker_panels: dict[measurement_worker, graph_panel] = {}
        self.worker_method_labels: dict[measurement_worker, str] = {}
        self.thread_panels: dict[QThread, graph_panel] = {}

        self.setWindowTitle("Palmsens demo")
        self.resize(1200, 760)
        self.setMinimumSize(900, 600)

        self.device_manager = device_manager()

        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        scan_action = QAction("Connect", self)
        scan_action.setStatusTip("Scan for available devices")
        scan_action.triggered.connect(self.scan_devices)
        toolbar.addAction(scan_action)

        self.disconnect_action = QAction("Disconnect", self)
        self.disconnect_action.setStatusTip("Disconnect from device")
        self.disconnect_action.setEnabled(False)
        self.disconnect_action.triggered.connect(self.request_disconnect)
        toolbar.addAction(self.disconnect_action)

        self.open_action = QAction("Open session", self)
        self.open_action.triggered.connect(self.open_session)
        toolbar.addAction(self.open_action)

        self.save_action = QAction("Save session", self)
        self.save_action.triggered.connect(self.save_session)
        toolbar.addAction(self.save_action)

        self.add_panel_action = QAction("Add panel", self)
        self.add_panel_action.triggered.connect(self.add_panel)
        toolbar.addAction(self.add_panel_action)

        self.connection_indicator = connection_indicator()
        self.statusBar().addPermanentWidget(self.connection_indicator)

        self.device_manager.connected.connect(self.on_connect)
        self.device_manager.disconnected.connect(self.on_disconnect)
        self.device_manager.connection_changed.connect(self.update_connection)
        self.worker_progress.connect(self.handle_worker_progress)
        self.worker_finished.connect(self.handle_worker_finished)
        self.worker_failed.connect(self.handle_worker_failed)
        self.worker_thread_finished.connect(self.handle_worker_thread_finished)

        self.panel_conainer = QWidget()
        self.panel_conainer.setObjectName("panelContainer")
        self.panel_layout = QGridLayout(self.panel_conainer)
        self.panel_layout.setContentsMargins(18, 18, 18, 18)
        self.panel_layout.setHorizontalSpacing(16)
        self.panel_layout.setVerticalSpacing(16)

        self.panel_scroll_area = QScrollArea()
        self.panel_scroll_area.setObjectName("panelScrollArea")
        self.panel_scroll_area.setWidgetResizable(True)
        self.panel_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_scroll_area.setWidget(self.panel_conainer)
        self.setCentralWidget(self.panel_scroll_area)

    def scan_devices(self):
        if self.device_manager.is_connected:
            QMessageBox.information(
                self,
                "Already connected",
                "Disconnect the current device before connecting another one.",
            )
            return

        try:
            devices = pslib.find_devices()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Scan failed",
                f"Device discovery failed:\n{exc}",
            )
            return

        if not devices:
            QMessageBox.warning(self, "Scan complete", "No devices found")
            return

        selected = None
        dialog = device_selection_dialog(devices, self)
        if dialog.exec():
            selected = dialog.selected_device
        if selected is not None:
            self.device_manager.connect_device(selected)

    def request_disconnect(self):
        if self.active_runs:
            QMessageBox.warning(
                self,
                "Measurement running",
                "Stop the active measurement before disconnecting the device.",
            )
            return

        self.device_manager.disconnect_device()

    def update_connection(self, is_connected: bool):
        self.disconnect_action.setEnabled(is_connected)

    def on_connect(self, dev):
        self.connection_indicator.set_status(True, dev)
        for instrument in dev.channels:
            self.add_panel(self._panel_title(instrument), instrument=instrument)

    def on_disconnect(self):
        self.connection_indicator.set_status(False)
        self.clear_panels()

    def open_session(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            "",
            "Session Files (*.pssession)",
        )
        if not file_path:
            return

        measurements = pslib.load_session(file_path)
        missing_panel_count = len(measurements) - len(self.panels)
        for _ in range(max(0, missing_panel_count)):
            self.add_panel()

        for index, measurement in enumerate(measurements):
            self.panels[index].graph.plot_measurement(measurement)
            self.panels[index].set_status_text(None)

    def save_session(self):
        measurements = self._measurements()
        if not measurements:
            QMessageBox.warning(self, "Save error", "No measurements to save")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save session",
            "",
            "Session Files (*.pssession)",
        )
        if not file_path:
            return

        pslib.save_session(file_path, measurements)

    def add_panel(self, title=None, instrument=None):
        if title is None:
            title = f"Panel {len(self.panels) + 1}"

        panel = graph_panel(title, instrument=instrument)
        panel.run_requested.connect(lambda panel=panel: self.run_measurement(panel))
        panel.stop_requested.connect(lambda panel=panel: self.stop_measurement(panel))
        panel.remove_requested.connect(lambda panel=panel: self.remove_panel(panel))
        self.panels.append(panel)
        self.refresh_panel_grid()
        return panel

    def remove_panel(self, panel):
        if panel not in self.panels:
            return
        if panel in self.active_runs:
            QMessageBox.warning(
                self,
                "Measurement running",
                "Stop the active measurement before removing this panel.",
            )
            return

        self.panel_layout.removeWidget(panel)
        self.panels.remove(panel)
        panel.deleteLater()
        self.refresh_panel_grid()

    def refresh_panel_grid(self):
        for index, panel in enumerate(self.panels):
            row = index // PANEL_COLUMNS
            column = index % PANEL_COLUMNS
            self.panel_layout.addWidget(panel, row, column)
        for column in range(PANEL_COLUMNS):
            self.panel_layout.setColumnStretch(column, 1)

    def clear_panels(self):
        for panel in list(self.panels):
            self.panel_layout.removeWidget(panel)
            self.panels.remove(panel)
            panel.deleteLater()

    def run_measurement(self, panel: graph_panel):
        if panel.instrument is None:
            QMessageBox.warning(
                self,
                "No channel assigned",
                "Connect to a device and use one of its channel panels to run a measurement.",
            )
            return

        if panel in self.active_runs:
            return

        dialog = method_configuration_dialog(panel.base_title, self)
        if not dialog.exec():
            return

        method = dialog.method
        method_label = METHOD_SPECS[dialog.selected_method_key()].label
        self.start_measurement(panel, method, method_label)

    def start_measurement(self, panel: graph_panel, method, method_label: str):
        thread = QThread(self)
        worker = measurement_worker(panel.instrument, method)
        worker.moveToThread(thread)
        self.worker_panels[worker] = panel
        self.worker_method_labels[worker] = method_label
        self.thread_panels[thread] = panel

        thread.started.connect(worker.run)
        worker.progress.connect(lambda data, worker=worker: self.worker_progress.emit(worker, data))
        worker.finished.connect(lambda measurement, worker=worker: self.worker_finished.emit(worker, measurement))
        worker.failed.connect(lambda error, worker=worker: self.worker_failed.emit(worker, error))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self.worker_thread_finished.emit(thread))

        self.active_runs[panel] = (thread, worker)
        panel.set_running(True)
        panel.set_status_text("Running")
        self.statusBar().showMessage(f"Running {method_label} on {panel.base_title}...", 0)
        thread.start()

    def stop_measurement(self, panel: graph_panel):
        run_context = self.active_runs.get(panel)
        if run_context is None:
            return

        _, worker = run_context
        self.stopping_panels.add(panel)
        panel.set_status_text("Stopping")
        self.statusBar().showMessage(f"Stopping measurement on {panel.base_title}...", 0)
        QMetaObject.invokeMethod(worker, "abort", Qt.ConnectionType.QueuedConnection)

    def handle_worker_progress(self, worker, callback_data):
        panel = self.worker_panels.get(worker)
        if panel is None or panel not in self.panels:
            return
        panel.graph.plot_live_data(callback_data)

    def handle_worker_finished(self, worker, measurement):
        panel = self.worker_panels.get(worker)
        if panel is None:
            return
        method_label = self.worker_method_labels.get(worker, "Measurement")
        self.on_measurement_finished(panel, method_label, measurement)

    def handle_worker_failed(self, worker, error: str):
        panel = self.worker_panels.get(worker)
        if panel is None:
            return
        self.on_measurement_failed(panel, error)

    def handle_worker_thread_finished(self, thread):
        panel = self.thread_panels.pop(thread, None)
        if panel is None:
            return
        self.cleanup_run(panel)

        worker_to_remove = None
        for worker, worker_panel in self.worker_panels.items():
            if worker_panel is panel:
                worker_to_remove = worker
                break

        if worker_to_remove is not None:
            self.worker_panels.pop(worker_to_remove, None)
            self.worker_method_labels.pop(worker_to_remove, None)

    def on_measurement_finished(self, panel: graph_panel, method_label: str, measurement):
        self.stopping_panels.discard(panel)
        panel.graph.plot_measurement(measurement)
        panel.set_status_text(None)
        self.statusBar().showMessage(
            f"Completed {method_label} on {panel.base_title}.",
            5000,
        )

    def on_measurement_failed(self, panel: graph_panel, error: str):
        panel.set_status_text(None)
        if panel in self.stopping_panels:
            self.stopping_panels.discard(panel)
            self.statusBar().showMessage(f"Stopped measurement on {panel.base_title}.", 5000)
            return

        self.statusBar().showMessage(f"Measurement failed on {panel.base_title}.", 5000)
        QMessageBox.critical(
            self,
            "Measurement failed",
            f"{panel.base_title} failed:\n{error}",
        )

    def cleanup_run(self, panel: graph_panel):
        self.active_runs.pop(panel, None)
        self.stopping_panels.discard(panel)
        if panel in self.panels:
            panel.set_running(False)

    def _measurements(self):
        return [
            panel.graph.measurement
            for panel in self.panels
            if panel.graph.measurement is not None
        ]

    @staticmethod
    def _panel_title(instrument):
        if getattr(instrument, "channel", -1) > 0: # Kolla om multichannel
            return f"CH {instrument.channel}"
        return instrument.name

    def closeEvent(self, event):
        if self.active_runs:
            QMessageBox.warning(
                self,
                "Measurement running",
                "Stop the active measurement before closing the application.",
            )
            event.ignore()
            return

        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = main_window()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
