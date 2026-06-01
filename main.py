import importlib
import json
from pathlib import Path
import sys

import pypalmsens as ps
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
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
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


AURORA_VENDOR_ROOT = Path(__file__).resolve().parent / "aurora-unicycler"
AURORA_DEVICE_OPTIONS = (
    ("EmStat4 HR", "emstat4_hr"),
    ("EmStat4 LR", "emstat4_lr"),
    ("Nexus", "nexus"),
)


def load_aurora_unicycler():
    aurora_package_root = AURORA_VENDOR_ROOT / "aurora_unicycler"
    if aurora_package_root.exists():
        vendor_path = str(AURORA_VENDOR_ROOT)
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)

    try:
        aurora_unicycler = importlib.import_module("aurora_unicycler")
        palmsens_module = importlib.import_module("aurora_unicycler.palmsens")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Aurora Unicycler is not available. Install `aurora-unicycler` or keep the vendored "
            "`aurora-unicycler/` directory next to `main.py`."
        ) from exc

    return aurora_unicycler, palmsens_module.PalmSensDevice


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
    def __init__(self, title: str, instrument=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Run Measurement - {title}")
        self.resize(760, 720)
        self.dialog_title = title
        self.method = None
        self.method_label = ""
        self.instrument = instrument
        self.field_widgets: dict[str, QLineEdit] = {}
        self.script_drafts = {
            "aurora_json": self.default_aurora_json(),
            "aurora_python": self.default_aurora_python(),
        }
        self._active_script_mode = None

        layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        layout.addLayout(self.form_layout)

        self.run_mode_combo = QComboBox(self)
        self.run_mode_combo.addItem("PalmSens method", "native")
        self.run_mode_combo.addItem("Aurora Unicycler JSON", "aurora_json")
        self.run_mode_combo.addItem("Aurora Unicycler Python", "aurora_python")
        self.run_mode_combo.addItem("MethodScript", "methodscript")
        self.form_layout.addRow("Run type", self.run_mode_combo)

        self.method_combo = QComboBox(self)
        for method_key in METHOD_ORDER:
            spec = METHOD_SPECS[method_key]
            self.method_combo.addItem(spec.label, method_key)
        self.method_combo_label = QLabel("Method", self)
        self.form_layout.addRow(self.method_combo_label, self.method_combo)

        self.field_form = QFormLayout()
        layout.addLayout(self.field_form)

        self.aurora_options = QWidget(self)
        self.aurora_options_form = QFormLayout(self.aurora_options)
        self.aurora_options_form.setContentsMargins(0, 0, 0, 0)

        self.aurora_device_combo = QComboBox(self)
        for label, value in AURORA_DEVICE_OPTIONS:
            self.aurora_device_combo.addItem(label, value)
        self.aurora_options_form.addRow("PalmSens target", self.aurora_device_combo)

        self.sample_name_edit = QLineEdit(title, self)
        self.aurora_options_form.addRow("Sample name", self.sample_name_edit)

        self.capacity_edit = QLineEdit("", self)
        self.aurora_options_form.addRow("Capacity (mAh)", self.capacity_edit)

        channel_default = "0"
        if instrument is not None and getattr(instrument, "channel", -1) > 0:
            channel_default = str(instrument.channel - 1)
        self.channel_edit = QLineEdit(channel_default, self)
        self.aurora_options_form.addRow("PGStat channel", self.channel_edit)

        self.scan_step_edit = QLineEdit("", self)
        self.aurora_options_form.addRow("Scan step voltage (V)", self.scan_step_edit)

        self.eis_dc_potential_edit = QLineEdit("0.0", self)
        self.aurora_options_form.addRow("EIS DC potential (V)", self.eis_dc_potential_edit)

        self.eis_dc_current_edit = QLineEdit("0.0", self)
        self.aurora_options_form.addRow("EIS DC current (mA)", self.eis_dc_current_edit)

        layout.addWidget(self.aurora_options)

        self.script_help = QLabel(self)
        self.script_help.setWordWrap(True)
        layout.addWidget(self.script_help)

        self.script_actions = QWidget(self)
        self.script_actions_layout = QVBoxLayout(self.script_actions)
        self.script_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.script_actions_layout.setSpacing(0)
        self.load_methodscript_button = QPushButton("Load MethodSCRIPT", self.script_actions)
        self.load_methodscript_button.clicked.connect(self.load_methodscript)
        self.script_actions_layout.addWidget(self.load_methodscript_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.script_actions)

        self.script_editor = QPlainTextEdit(self)
        self.script_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.script_editor.setMinimumHeight(320)
        layout.addWidget(self.script_editor, 1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.run_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self.run_button is not None:
            self.run_button.setText("Run")
        self.save_script_button = button_box.addButton("Save MethodSCRIPT", QDialogButtonBox.ButtonRole.ActionRole)
        self.save_script_button.clicked.connect(self.save_methodscript)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.method_combo.currentIndexChanged.connect(self.rebuild_fields)
        self.run_mode_combo.currentIndexChanged.connect(self.rebuild_mode)
        self.rebuild_fields()
        self.rebuild_mode()

    def selected_method_key(self) -> str:
        return self.method_combo.currentData()

    def selected_run_mode(self) -> str:
        return self.run_mode_combo.currentData()

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

    def rebuild_mode(self):
        previous_mode = self._active_script_mode
        if previous_mode in self.script_drafts:
            self.script_drafts[previous_mode] = self.script_editor.toPlainText()

        run_mode = self.selected_run_mode()
        native_mode = run_mode == "native"
        methodscript_mode = run_mode == "methodscript"

        self.method_combo_label.setVisible(native_mode)
        self.method_combo.setVisible(native_mode)
        for widget in self.field_widgets.values():
            widget.setVisible(native_mode)
        for row_index in range(self.field_form.rowCount()):
            label_item = self.field_form.itemAt(row_index, QFormLayout.ItemRole.LabelRole)
            field_item = self.field_form.itemAt(row_index, QFormLayout.ItemRole.FieldRole)
            if label_item is not None and label_item.widget() is not None:
                label_item.widget().setVisible(native_mode)
            if field_item is not None and field_item.widget() is not None:
                field_item.widget().setVisible(native_mode)

        self.aurora_options.setVisible(not (native_mode or methodscript_mode))
        self.script_help.setVisible(not native_mode)
        self.script_actions.setVisible(methodscript_mode)
        self.script_editor.setVisible(not native_mode)

        if run_mode in self.script_drafts:
            self.script_editor.setPlainText(self.script_drafts[run_mode])
            self._active_script_mode = run_mode
        else:
            self._active_script_mode = None

        if run_mode == "aurora_json":
            self.script_help.setText(
                "Paste an Aurora Unicycler protocol JSON object. The app will validate it, "
                "convert it to PalmSens MethodSCRIPT, then run it with PyPalmSens."
            )
        elif run_mode == "aurora_python":
            self.script_help.setText(
                "Paste a Python script that defines `protocol = CyclingProtocol(...)` or a "
                "`build_protocol()` function returning one. The script runs locally inside the app."
            )
        elif run_mode == "methodscript":
            self.script_help.setText(
                "Paste MethodSCRIPT directly or load an existing .mscr file, then run it with PyPalmSens."
            )

        self.save_script_button.setVisible(run_mode in {"aurora_json", "aurora_python"})

    def validate_and_accept(self):
        try:
            run_mode = self.selected_run_mode()
            if run_mode == "native":
                self.method = build_method(self.selected_method_key(), self.raw_params())
                self.method_label = METHOD_SPECS[self.selected_method_key()].label
            else:
                self.method = self.build_script_method(run_mode)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return
        except RuntimeError as exc:
            QMessageBox.warning(self, "Aurora setup error", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "Aurora conversion error", str(exc))
            return

        self.accept()
                
    def build_script_method(self, run_mode: str):
        methodscript = self.generate_methodscript(run_mode)
        if run_mode == "methodscript":
            self.method_label = "MethodSCRIPT"
        else:
            if not hasattr(ps, "MethodScript"):
                raise RuntimeError(
                    "This PyPalmSens installation does not expose `MethodScript`. "
                    "Update PyPalmSens before running Aurora-generated scripts."
                )

            self.method_label = f"Aurora Unicycler ({self.aurora_device_combo.currentText()})"
        return ps.MethodScript(script=methodscript)

    def generate_methodscript(self, run_mode: str) -> str:
        script_text = self.script_editor.toPlainText()
        if not script_text.strip():
            raise ValueError("script content is required.")

        if run_mode == "methodscript":
            return script_text

        if run_mode not in {"aurora_json", "aurora_python"}:
            raise ValueError("MethodSCRIPT export is only available for Aurora modes.")

        aurora_unicycler, palm_sens_device_enum = load_aurora_unicycler()
        protocol = self.build_aurora_protocol(aurora_unicycler, palm_sens_device_enum, run_mode, script_text)

        capacity_mAh = self.parse_optional_float(self.capacity_edit, "Capacity (mAh)")
        channel = self.parse_int(self.channel_edit, "PGStat channel")
        scan_step_voltage_v = self.parse_optional_float(self.scan_step_edit, "Scan step voltage (V)")
        eis_dc_potential_v = self.parse_float(self.eis_dc_potential_edit, "EIS DC potential (V)")
        eis_dc_current_ma = self.parse_float(self.eis_dc_current_edit, "EIS DC current (mA)")

        sample_name = self.sample_name_edit.text().strip() or None
        device_key = self.aurora_device_combo.currentData()
        return protocol.to_palmsens_methodscript(
            sample_name=sample_name,
            capacity_mAh=capacity_mAh,
            device=palm_sens_device_enum(device_key),
            channel=channel,
            scan_step_voltage_V=scan_step_voltage_v,
            eis_dc_potential_V=eis_dc_potential_v,
            eis_dc_current_mA=eis_dc_current_ma,
        )

    def save_methodscript(self):
        run_mode = self.selected_run_mode()
        if run_mode not in {"aurora_json", "aurora_python"}:
            QMessageBox.information(
                self,
                "Save unavailable",
                "MethodSCRIPT saving is currently only available for the Aurora modes.",
            )
            return

        try:
            methodscript = self.generate_methodscript(run_mode)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return
        except RuntimeError as exc:
            QMessageBox.warning(self, "Aurora setup error", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "Aurora conversion error", str(exc))
            return

        sample_name = self.sample_name_edit.text().strip()
        default_name = sample_name or self.dialog_title.replace(" ", "_")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save MethodSCRIPT",
            f"{default_name}.mscr",
            "MethodSCRIPT Files (*.mscr);;Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        if path.suffix == "":
            path = path.with_suffix(".mscr")

        try:
            path.write_text(methodscript, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Save failed",
                f"Could not save MethodSCRIPT:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "MethodSCRIPT saved",
            f"Saved MethodSCRIPT to:\n{path}",
        )

    def load_methodscript(self):
        if self.selected_run_mode() != "methodscript":
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load MethodSCRIPT",
            "",
            "MethodSCRIPT Files (*.mscr);;Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            script_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Load failed",
                f"Could not load MethodSCRIPT:\n{exc}",
            )
            return

        self.script_editor.setPlainText(script_text)

    @staticmethod
    def build_aurora_protocol(aurora_unicycler, palm_sens_device_enum, run_mode: str, script_text: str):
        # Path 1: JSON
        if run_mode == "aurora_json":
            try:
                protocol_data = json.loads(script_text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid Aurora JSON: {exc.msg}") from exc
            return aurora_unicycler.CyclingProtocol.from_dict(protocol_data)

        # Path 2: Python
        execution_scope = {
            "__builtins__": __builtins__,
            "CyclingProtocol": aurora_unicycler.CyclingProtocol,
            "ConstantCurrent": aurora_unicycler.ConstantCurrent,
            "ConstantVoltage": aurora_unicycler.ConstantVoltage,
            "ImpedanceSpectroscopy": aurora_unicycler.ImpedanceSpectroscopy,
            "Loop": aurora_unicycler.Loop,
            "OpenCircuitVoltage": aurora_unicycler.OpenCircuitVoltage,
            "PalmSensDevice": palm_sens_device_enum,
            "RecordParams": aurora_unicycler.RecordParams,
            "SafetyParams": aurora_unicycler.SafetyParams,
            "SampleParams": aurora_unicycler.SampleParams,
            "Tag": aurora_unicycler.Tag,
            "VoltageScan": aurora_unicycler.VoltageScan,
        }
        exec(script_text, execution_scope, execution_scope)

        protocol = execution_scope.get("protocol")
        if protocol is None:
            build_protocol = execution_scope.get("build_protocol")
            if callable(build_protocol):
                protocol = build_protocol()

        if protocol is None:
            raise ValueError(
                "Aurora Python scripts must define `protocol = CyclingProtocol(...)` "
                "or `build_protocol()`."
            )

        if not isinstance(protocol, aurora_unicycler.CyclingProtocol):
            raise ValueError("Aurora Python script did not produce a CyclingProtocol.")

        return protocol

    # Start of parsing helpers
    @staticmethod
    def parse_float(widget: QLineEdit, label: str) -> float:
        raw_value = widget.text().strip()
        if not raw_value:
            raise ValueError(f"{label} is required.")
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {label}: {raw_value}") from exc

    @staticmethod
    def parse_optional_float(widget: QLineEdit, label: str) -> float | None:
        raw_value = widget.text().strip()
        if not raw_value:
            return None
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {label}: {raw_value}") from exc

    @staticmethod
    def parse_int(widget: QLineEdit, label: str) -> int:
        raw_value = widget.text().strip()
        if not raw_value:
            raise ValueError(f"{label} is required.")
        try:
            return int(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {label}: {raw_value}") from exc
    # End of parsing helpers

    @staticmethod
    def default_aurora_json() -> str:
        return json.dumps(
            {
                "record": {"time_s": 10, "voltage_V": 0.01},
                "safety": {"max_voltage_V": 4.3, "min_voltage_V": 2.5},
                "method": [
                    {"step": "tag", "tag": "cycle"},
                    {"step": "constant_current", "rate_C": 0.5, "until_voltage_V": 4.2},
                    {"step": "constant_voltage", "voltage_V": 4.2, "until_rate_C": 0.05},
                    {"step": "constant_current", "rate_C": -0.5, "until_voltage_V": 3.0},
                    {"step": "loop", "loop_to": "cycle", "cycle_count": 10},
                ],
            },
            indent=2,
        )

    @staticmethod
    def default_aurora_python() -> str:
        return """protocol = CyclingProtocol(
    record=RecordParams(time_s=10, voltage_V=0.01),
    safety=SafetyParams(max_voltage_V=4.3, min_voltage_V=2.5),
    method=[
        Tag(tag="cycle"),
        ConstantCurrent(rate_C=0.5, until_voltage_V=4.2, until_time_s=3 * 60 * 60),
        ConstantVoltage(voltage_V=4.2, until_rate_C=0.05, until_time_s=60 * 60),
        ConstantCurrent(rate_C=-0.5, until_voltage_V=3.0, until_time_s=3 * 60 * 60),
        Loop(loop_to="cycle", cycle_count=10),
    ],
)
"""


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
        self.expanded_panel: graph_panel | None = None
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

        self.session_menu = QMenu("Session", self)
        self.open_action = QAction("Load session", self)
        self.open_action.triggered.connect(self.open_session)
        self.session_menu.addAction(self.open_action)

        self.save_action = QAction("Save session", self)
        self.save_action.triggered.connect(self.save_session)
        self.session_menu.addAction(self.save_action)

        self.session_button = QToolButton(self)
        self.session_button.setText("Session")
        self.session_button.setMenu(self.session_menu)
        self.session_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(self.session_button)

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
        if self.active_runs:
            QMessageBox.warning(
                self,
                "Measurement running",
                "Stop the active measurement before opening a session.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            "",
            "Session Files (*.pssession)",
        )
        if not file_path:
            return

        measurements = pslib.load_session(file_path)
        if not self.panels:
            QMessageBox.warning(
                self,
                "No channels available",
                "Connect to a device before opening a session.",
            )
            return

        if len(measurements) > len(self.panels):
            QMessageBox.warning(
                self,
                "Too many measurements",
                (
                    f"The session contains {len(measurements)} measurements, but only "
                    f"{len(self.panels)} channel panels are available. Only the first "
                    f"{len(self.panels)} measurements will be loaded."
                ),
            )

        for index, measurement in enumerate(measurements[: len(self.panels)]):
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
        panel.expand_requested.connect(
            lambda is_expanded, panel=panel: self.set_panel_expanded(panel, is_expanded)
        )
        self.panels.append(panel)
        self.refresh_panel_grid()
        return panel

    def set_panel_expanded(self, panel: graph_panel, is_expanded: bool):
        if panel not in self.panels:
            return

        if is_expanded:
            previous_panel = self.expanded_panel
            self.expanded_panel = panel
            if previous_panel is not None and previous_panel is not panel:
                previous_panel.set_expanded(False)
        elif self.expanded_panel is panel:
            self.expanded_panel = None

        self.refresh_panel_grid()

    def refresh_panel_grid(self):
        for panel in self.panels:
            self.panel_layout.removeWidget(panel)

        if self.expanded_panel is not None and self.expanded_panel in self.panels:
            for panel in self.panels:
                is_expanded = panel is self.expanded_panel
                panel.set_expanded(is_expanded)
                panel.setVisible(is_expanded)

            self.panel_layout.addWidget(self.expanded_panel, 0, 0, 1, PANEL_COLUMNS)
            return

        for index, panel in enumerate(self.panels):
            panel.set_expanded(False)
            panel.show()
            row = index // PANEL_COLUMNS
            column = index % PANEL_COLUMNS
            self.panel_layout.addWidget(panel, row, column)
        for column in range(PANEL_COLUMNS):
            self.panel_layout.setColumnStretch(column, 1)

    def clear_panels(self):
        self.expanded_panel = None
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

        dialog = method_configuration_dialog(panel.base_title, instrument=panel.instrument, parent=self)
        if not dialog.exec():
            return

        method = dialog.method
        method_label = dialog.method_label
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
