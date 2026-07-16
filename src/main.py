import sys
from datetime import date
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pypalmsens as ps
from src.app_style import APP_STYLESHEET
from src.aurora_app.aurora_methods import (
    AURORA_ADDITIONAL_MEASUREMENT_OPTIONS,
    AURORA_DEVICE_MEASUREMENT_TYPES,
    AURORA_DEVICE_OPTIONS,
    AuroraExportSettings,
    build_aurora_stepwise_method,
    load_aurora_package,
)

from src.bdf_export import BdfExportError, bdf_optional_quantity_choices, export_measurement_to_bdf_files
from PySide6.QtCore import QObject, QSize, Signal, Slot, Qt, QThread, QProcess
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.graph import graph_panel
from src.method_config import METHOD_ORDER, METHOD_SPECS, build_method
from src.method_worker import measurement_worker
from src.temperature_chamber.temperature_controller import TemperatureProgress, TemperatureSettings
import src.device_helpers as pslib

PANEL_COLUMNS = 3
AURORA_APP_SUBDIRECTORY = "aurora_app"

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


class bdf_export_dialog(QDialog):
    def __init__(self, exportable_panels, parent=None):
        super().__init__(parent)
        self.file_type = "csv"
        self.setWindowTitle("Export BDF")
        self.resize(640, 480)
        self._checkboxes: list[tuple[QCheckBox, object]] = []
        self._quantity_checkboxes: list[tuple[QCheckBox, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        info_label = QLabel(
            "Select the channel measurements to export as BDF files. "
            "Only channels with loaded measurements are listed.",
            self,
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.output_dir_edit = QLineEdit(self)
        browse_button = QPushButton("Choose Folder", self)
        browse_button.clicked.connect(self.choose_output_dir)

        self.file_type_combo_box = QComboBox(self)
        self.file_type_combo_box.addItem("csv", "csv")
        self.file_type_combo_box.addItem("parquet", "parquet")

        self.cell_name_edit = QLineEdit(self)
        self.cell_name_edit.setPlaceholderText("e.g. A0001")

        self.cas_id_edit = QLineEdit(self)
        self.cas_id_edit.setPlaceholderText("e.g. nisu1374")

        self.export_separate_checkbox = QCheckBox("Export each measurement separately", self)
        self.export_separate_checkbox.setChecked(False)

        output_options = QWidget(self)
        output_options_layout = QGridLayout(output_options)
        output_options_layout.setContentsMargins(0, 0, 0, 0)
        output_options_layout.setHorizontalSpacing(8)
        output_options_layout.setVerticalSpacing(8)
        output_options_layout.addWidget(QLabel("Format", output_options), 0, 0)
        output_options_layout.addWidget(self.file_type_combo_box, 0, 1, 1, 2)
        output_options_layout.setColumnStretch(1, 1)
        layout.addWidget(output_options)

        naming_header = QLabel("Naming", self)
        layout.addWidget(naming_header)

        naming_frame = QFrame(self)
        naming_frame.setFrameShape(QFrame.Shape.StyledPanel)
        naming_frame.setFrameShadow(QFrame.Shadow.Plain)
        naming_layout = QGridLayout(naming_frame)
        naming_layout.setContentsMargins(10, 10, 10, 10)
        naming_layout.setHorizontalSpacing(8)
        naming_layout.setVerticalSpacing(8)
        naming_layout.addWidget(QLabel("Cell name", naming_frame), 0, 0)
        naming_layout.addWidget(self.cell_name_edit, 0, 1)
        naming_layout.addWidget(QLabel("CAS ID", naming_frame), 1, 0)
        naming_layout.addWidget(self.cas_id_edit, 1, 1)
        naming_layout.setColumnStretch(1, 1)
        layout.addWidget(naming_frame)

        folder_options = QWidget(self)
        folder_options_layout = QGridLayout(folder_options)
        folder_options_layout.setContentsMargins(0, 0, 0, 0)
        folder_options_layout.setHorizontalSpacing(8)
        folder_options_layout.setVerticalSpacing(8)
        folder_options_layout.addWidget(QLabel("Folder", folder_options), 0, 0)
        folder_options_layout.addWidget(self.output_dir_edit, 0, 1)
        folder_options_layout.addWidget(browse_button, 0, 2)
        folder_options_layout.addWidget(self.export_separate_checkbox, 1, 1, 1, 2)
        folder_options_layout.setColumnStretch(1, 1)
        layout.addWidget(folder_options)

        channel_header = QLabel("Channels", self)
        layout.addWidget(channel_header)

        self.checkbox_container = QWidget(self)
        self.checkbox_layout = QVBoxLayout(self.checkbox_container)
        self.checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.checkbox_layout.setSpacing(6)

        for panel in exportable_panels:
            checkbox = QCheckBox(panel.base_title, self.checkbox_container)
            checkbox.setChecked(False)
            self._checkboxes.append((checkbox, panel))
            self.checkbox_layout.addWidget(checkbox)

        self.checkbox_layout.addStretch(1)

        channel_scroll_area = QScrollArea(self)
        channel_scroll_area.setWidgetResizable(True)
        channel_scroll_area.setMinimumHeight(72)
        channel_scroll_area.setMaximumHeight(132)
        channel_scroll_area.setWidget(self.checkbox_container)
        layout.addWidget(channel_scroll_area)

        self.quantity_toggle_button = QToolButton(self)
        self.quantity_toggle_button.setCheckable(True)
        self.quantity_toggle_button.setChecked(False)
        self.quantity_toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.quantity_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.quantity_toggle_button.toggled.connect(self.set_quantity_options_visible)
        layout.addWidget(self.quantity_toggle_button)

        self.quantity_options_widget = QWidget(self)
        quantity_options_layout = QVBoxLayout(self.quantity_options_widget)
        quantity_options_layout.setContentsMargins(0, 0, 0, 0)
        quantity_options_layout.setSpacing(8)

        self.quantity_search_edit = QLineEdit(self)
        self.quantity_search_edit.setPlaceholderText("Search optional quantities")
        self.quantity_search_edit.setClearButtonEnabled(True)
        self.quantity_search_edit.textChanged.connect(self.filter_optional_quantities)
        quantity_options_layout.addWidget(self.quantity_search_edit)

        quantity_actions = QWidget(self)
        quantity_actions_layout = QHBoxLayout(quantity_actions)
        quantity_actions_layout.setContentsMargins(0, 0, 0, 0)
        quantity_actions_layout.setSpacing(8)

        select_all_button = QPushButton("Select All", self)
        select_all_button.clicked.connect(self.select_all_optional_quantities)
        clear_button = QPushButton("Clear", self)
        clear_button.clicked.connect(self.clear_optional_quantities)
        quantity_actions_layout.addWidget(select_all_button)
        quantity_actions_layout.addWidget(clear_button)
        quantity_actions_layout.addStretch(1)
        quantity_options_layout.addWidget(quantity_actions)

        self.quantity_container = QWidget(self)
        self.quantity_layout = QVBoxLayout(self.quantity_container)
        self.quantity_layout.setContentsMargins(0, 0, 0, 0)
        self.quantity_layout.setSpacing(4)

        for quantity_key, quantity_label in bdf_optional_quantity_choices():
            checkbox = QCheckBox(quantity_label, self.quantity_container)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.update_quantity_toggle_text)
            self._quantity_checkboxes.append((checkbox, quantity_key))
            self.quantity_layout.addWidget(checkbox)

        self.no_quantity_matches_label = QLabel("No matching quantities", self.quantity_container)
        self.no_quantity_matches_label.setVisible(False)
        self.quantity_layout.addWidget(self.no_quantity_matches_label)
        self.quantity_layout.addStretch(1)

        quantity_scroll_area = QScrollArea(self)
        quantity_scroll_area.setWidgetResizable(True)
        quantity_scroll_area.setMinimumHeight(280)
        quantity_scroll_area.setWidget(self.quantity_container)
        quantity_options_layout.addWidget(quantity_scroll_area, 1)
        self.quantity_options_widget.setVisible(False)
        layout.addWidget(self.quantity_options_widget)
        self.update_quantity_toggle_text()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        export_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if export_button is not None:
            export_button.setText("Export")
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def choose_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose export folder")
        if directory:
            self.output_dir_edit.setText(directory)
    
    def selected_panels(self):
        return [panel for checkbox, panel in self._checkboxes if checkbox.isChecked()]

    def selected_type(self):
        return self.file_type_combo_box.currentData()

    def export_separate_measurements(self):
        return self.export_separate_checkbox.isChecked()

    def cell_name(self):
        return self.cell_name_edit.text().strip() or "A0001"

    def cas_id(self):
        return self.cas_id_edit.text().strip()

    def selected_optional_quantity_keys(self):
        return {
            quantity_key
            for checkbox, quantity_key in self._quantity_checkboxes
            if checkbox.isChecked()
        }

    def filter_optional_quantities(self, search_text: str):
        normalized_search = search_text.strip().casefold()
        visible_count = 0
        for checkbox, quantity_key in self._quantity_checkboxes:
            searchable_text = f"{checkbox.text()} {quantity_key}".casefold()
            is_visible = not normalized_search or normalized_search in searchable_text
            checkbox.setVisible(is_visible)
            if is_visible:
                visible_count += 1
        self.no_quantity_matches_label.setVisible(visible_count == 0)

    def set_quantity_options_visible(self, is_visible: bool):
        self.quantity_options_widget.setVisible(is_visible)
        arrow_type = Qt.ArrowType.DownArrow if is_visible else Qt.ArrowType.RightArrow
        self.quantity_toggle_button.setArrowType(arrow_type)
        if is_visible:
            self.resize(self.width(), max(self.height(), 720))
        else:
            self.adjustSize()

    def select_all_optional_quantities(self):
        for checkbox, _ in self._quantity_checkboxes:
            checkbox.setChecked(True)
        self.update_quantity_toggle_text()

    def clear_optional_quantities(self):
        for checkbox, _ in self._quantity_checkboxes:
            checkbox.setChecked(False)
        self.update_quantity_toggle_text()

    def update_quantity_toggle_text(self):
        selected_count = len(self.selected_optional_quantity_keys())
        total_count = len(self._quantity_checkboxes)
        if selected_count == total_count:
            summary = "all selected"
        else:
            summary = f"{selected_count} selected"
        self.quantity_toggle_button.setText(f"Additional BDF quantities ({summary})")

    def output_directory(self) -> Path | None:
        raw_path = self.output_dir_edit.text().strip()
        if not raw_path:
            return None
        return Path(raw_path)

    def validate_and_accept(self):
        output_dir = self.output_directory()
        if output_dir is None:
            QMessageBox.warning(self, "Export error", "Choose an export folder.")
            return

        if not self.selected_panels():
            QMessageBox.warning(self, "Export error", "Select at least one channel to export.")
            return

        self.accept()


class method_configuration_dialog(QDialog):
    def __init__(self, title: str, instrument=None, parent=None):
        super().__init__(parent)
        self.setObjectName("methodConfigDialog")
        self.setWindowTitle(f"Run Measurement - {title}")
        self.resize(760, 620)
        self.setMinimumSize(560, 420)
        self.dialog_title = title
        self.method = None
        self.method_label = ""
        self.temperature_settings = None
        self.instrument = instrument
        self.imported_package = None
        self.imported_package_path: Path | None = None
        self.field_widgets: dict[str, QLineEdit] = {}
        self.additional_measurement_checks: dict[str, QCheckBox] = {}

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(16, 16, 16, 16)
        dialog_layout.setSpacing(12)

        self.scroll_content = QWidget(self)
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setHorizontalSpacing(12)
        self.form_layout.setVerticalSpacing(8)
        layout.addLayout(self.form_layout)

        self.run_mode_combo = QComboBox(self)
        self.run_mode_combo.addItem("PalmSens method", "native")
        self.run_mode_combo.addItem("Imported package", "aurora_package")
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

        self.package_widget = QFrame(self)
        self.package_widget.setObjectName("auroraOptionsCard")
        self.package_widget.setFrameShape(QFrame.Shape.StyledPanel)
        package_layout = QVBoxLayout(self.package_widget)
        package_layout.setContentsMargins(14, 14, 14, 14)
        package_layout.setSpacing(10)

        package_title = QLabel("Imported Package", self.package_widget)
        package_title.setObjectName("auroraCardTitle")
        package_layout.addWidget(package_title)

        self.package_info_label = QLabel("No package loaded.", self.package_widget)
        self.package_info_label.setWordWrap(True)
        package_layout.addWidget(self.package_info_label)

        self.load_package_button = QPushButton("Load Package", self.package_widget)
        self.load_package_button.clicked.connect(self.load_aurora_package_file)
        package_layout.addWidget(self.load_package_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.package_run_form = QFormLayout()
        self.package_run_form.setContentsMargins(0, 0, 0, 0)
        self.package_run_form.setHorizontalSpacing(12)
        self.package_run_form.setVerticalSpacing(8)
        package_layout.addLayout(self.package_run_form)

        self.aurora_sample_name_edit = QLineEdit("", self.package_widget)
        self.package_run_form.addRow("Sample name", self.aurora_sample_name_edit)

        self.aurora_capacity_edit = QLineEdit("", self.package_widget)
        self.package_run_form.addRow("Capacity (mAh)", self.aurora_capacity_edit)

        self.aurora_device_combo = QComboBox(self.package_widget)
        for label, value in AURORA_DEVICE_OPTIONS:
            self.aurora_device_combo.addItem(label, value)
        self.package_run_form.addRow("PalmSens target", self.aurora_device_combo)

        self.aurora_channel_label = QLabel(str(self.run_channel()), self.package_widget)
        self.package_run_form.addRow("Channel", self.aurora_channel_label)

        self.aurora_scan_step_edit = QLineEdit("", self.package_widget)
        self.package_run_form.addRow("Scan step voltage (V)", self.aurora_scan_step_edit)

        self.aurora_eis_dc_potential_edit = QLineEdit("0.0", self.package_widget)
        self.package_run_form.addRow("EIS DC potential (V)", self.aurora_eis_dc_potential_edit)

        self.aurora_eis_dc_current_edit = QLineEdit("0.0", self.package_widget)
        self.package_run_form.addRow("EIS DC current (mA)", self.aurora_eis_dc_current_edit)

        extra_measurements_label = QLabel("Extra measurements", self.package_widget)
        extra_measurements_label.setObjectName("auroraCardTitle")
        package_layout.addWidget(extra_measurements_label)

        self.additional_measurement_widget = QWidget(self.package_widget)
        self.additional_measurement_layout = QGridLayout(self.additional_measurement_widget)
        self.additional_measurement_layout.setContentsMargins(0, 0, 0, 0)
        self.additional_measurement_layout.setHorizontalSpacing(16)
        self.additional_measurement_layout.setVerticalSpacing(6)
        for index, (var_type, label) in enumerate(AURORA_ADDITIONAL_MEASUREMENT_OPTIONS):
            checkbox = QCheckBox(label, self.additional_measurement_widget)
            checkbox.setToolTip(f"Measure MethodSCRIPT variable type {var_type} with add_meas.")
            self.additional_measurement_checks[var_type] = checkbox
            self.additional_measurement_layout.addWidget(checkbox, index // 2, index % 2)
        package_layout.addWidget(self.additional_measurement_widget)

        temperature_title = QLabel("Temperature Chamber", self.package_widget)
        temperature_title.setObjectName("auroraCardTitle")
        package_layout.addWidget(temperature_title)

        self.temperature_enabled_checkbox = QCheckBox("Enable Arduino temperature chamber", self.package_widget)
        package_layout.addWidget(self.temperature_enabled_checkbox)

        self.temperature_form = QFormLayout()
        self.temperature_form.setContentsMargins(0, 0, 0, 0)
        self.temperature_form.setHorizontalSpacing(12)
        self.temperature_form.setVerticalSpacing(8)
        package_layout.addLayout(self.temperature_form)

        self.temperature_port_edit = QLineEdit("", self.package_widget)
        self.temperature_port_edit.setPlaceholderText("COM31 or blank for auto-detect")
        self.temperature_form.addRow("Serial port", self.temperature_port_edit)

        self.temperature_baud_edit = QLineEdit("9600", self.package_widget)
        self.temperature_form.addRow("Baud rate", self.temperature_baud_edit)

        self.temperature_tolerance_edit = QLineEdit("0.5", self.package_widget)
        self.temperature_form.addRow("Tolerance (degC)", self.temperature_tolerance_edit)

        self.temperature_poll_interval_edit = QLineEdit("1.0", self.package_widget)
        self.temperature_form.addRow("Poll interval (s)", self.temperature_poll_interval_edit)

        self.temperature_timeout_edit = QLineEdit("", self.package_widget)
        self.temperature_timeout_edit.setPlaceholderText("Blank = no timeout")
        self.temperature_form.addRow("Timeout (s)", self.temperature_timeout_edit)

        default_log_dir = Path(__file__).parent.parent / "out2" / "temp_logs"
        self.temperature_log_dir_edit = QLineEdit(str(default_log_dir), self.package_widget)
        self.temperature_form.addRow("Log directory", self.temperature_log_dir_edit)

        self.temperature_stop_on_abort_checkbox = QCheckBox("Stop chamber on abort", self.package_widget)
        self.temperature_stop_on_abort_checkbox.setChecked(True)
        package_layout.addWidget(self.temperature_stop_on_abort_checkbox)

        layout.addWidget(self.package_widget)

        self.script_help = QLabel(self)
        self.script_help.setObjectName("auroraHelpText")
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

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.scroll_content)
        dialog_layout.addWidget(self.scroll_area, 1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.run_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self.run_button is not None:
            self.run_button.setText("Run")
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        dialog_layout.addWidget(button_box)

        self.method_combo.currentIndexChanged.connect(self.rebuild_fields)
        self.run_mode_combo.currentIndexChanged.connect(self.rebuild_mode)
        self.aurora_device_combo.currentIndexChanged.connect(self.update_additional_measurements)
        self.temperature_enabled_checkbox.toggled.connect(self.update_temperature_fields)
        self.update_additional_measurements()
        self.update_temperature_fields()
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

    def run_channel(self) -> int:
        if self.instrument is not None and getattr(self.instrument, "channel", -1) > 0:
            return self.instrument.channel - 1
        return 0

    def update_additional_measurements(self):
        device_key = self.aurora_device_combo.currentData()
        supported = AURORA_DEVICE_MEASUREMENT_TYPES.get(device_key, set())
        for var_type, checkbox in self.additional_measurement_checks.items():
            enabled = var_type in supported
            checkbox.setEnabled(enabled)
            if not enabled:
                checkbox.setChecked(False)

    def selected_additional_measurements(self) -> tuple[str, ...]:
        return tuple(
            var_type
            for var_type, checkbox in self.additional_measurement_checks.items()
            if checkbox.isEnabled() and checkbox.isChecked()
        )

    def update_temperature_fields(self):
        enabled = self.temperature_enabled_checkbox.isChecked()
        for widget in (
            self.temperature_port_edit,
            self.temperature_baud_edit,
            self.temperature_tolerance_edit,
            self.temperature_poll_interval_edit,
            self.temperature_timeout_edit,
            self.temperature_log_dir_edit,
            self.temperature_stop_on_abort_checkbox,
        ):
            widget.setEnabled(enabled)

    def build_temperature_settings(self) -> TemperatureSettings | None:
        if not self.temperature_enabled_checkbox.isChecked():
            return None

        tolerance_c = self.parse_float(self.temperature_tolerance_edit, "Temperature tolerance")
        poll_interval_s = self.parse_float(self.temperature_poll_interval_edit, "Temperature poll interval")
        timeout_s = self.parse_optional_float(self.temperature_timeout_edit, "Temperature timeout")
        if tolerance_c <= 0:
            raise ValueError("Temperature tolerance must be greater than 0.")
        if poll_interval_s <= 0:
            raise ValueError("Temperature poll interval must be greater than 0.")
        if timeout_s is not None and timeout_s <= 0:
            raise ValueError("Temperature timeout must be greater than 0.")

        return TemperatureSettings(
            port=self.temperature_port_edit.text().strip() or None,
            baud_rate=self.parse_int(self.temperature_baud_edit, "Temperature baud rate"),
            tolerance_c=tolerance_c,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
            log_dir=self.temperature_log_dir_edit.text().strip() or None,
            stop_on_abort=self.temperature_stop_on_abort_checkbox.isChecked(),
        )

    def build_aurora_export_settings(self) -> AuroraExportSettings:
        return AuroraExportSettings(
            sample_name=self.aurora_sample_name_edit.text().strip() or None,
            capacity_mAh=self.parse_optional_float(self.aurora_capacity_edit, "Capacity (mAh)"),
            device_key=self.aurora_device_combo.currentData(),
            channel=self.run_channel(),
            scan_step_voltage_v=self.parse_optional_float(
                self.aurora_scan_step_edit,
                "Scan step voltage (V)",
            ),
            eis_dc_potential_v=self.parse_float(
                self.aurora_eis_dc_potential_edit,
                "EIS DC potential (V)",
            ),
            eis_dc_current_ma=self.parse_float(
                self.aurora_eis_dc_current_edit,
                "EIS DC current (mA)",
            ),
            additional_measurements=self.selected_additional_measurements(),
        )

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
        run_mode = self.selected_run_mode()
        native_mode = run_mode == "native"
        package_mode = run_mode == "aurora_package"
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

        self.package_widget.setVisible(package_mode)
        self.script_help.setVisible(package_mode or methodscript_mode)
        self.script_actions.setVisible(methodscript_mode)
        self.script_editor.setVisible(methodscript_mode)

        if package_mode:
            self.script_help.setText(
                "Load a `.psmethod` file exported from the standalone Aurora Method Builder. "
                "The package will be rendered for the current channel panel when you run it."
            )
        elif run_mode == "methodscript":
            self.script_help.setText(
                "Paste MethodSCRIPT directly or load an existing .mscr file, then run it with PyPalmSens."
            )
        else:
            self.script_help.clear()

    def validate_and_accept(self):
        try:
            run_mode = self.selected_run_mode()
            if run_mode == "native":
                self.method = build_method(self.selected_method_key(), self.raw_params())
                self.method_label = METHOD_SPECS[self.selected_method_key()].label
                self.temperature_settings = None
            else:
                self.method = self.build_script_method(run_mode)
                self.temperature_settings = (
                    self.build_temperature_settings()
                    if run_mode == "aurora_package"
                    else None
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return
        except RuntimeError as exc:
            QMessageBox.warning(self, "Setup error", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "Method error", str(exc))
            return

        self.accept()
                
    def build_script_method(self, run_mode: str):
        if run_mode == "methodscript":
            script_text = self.script_editor.toPlainText()
            if not script_text.strip():
                raise ValueError("script content is required.")
            self.method_label = "MethodSCRIPT"
            return ps.MethodScript(script=script_text)

        if run_mode != "aurora_package":
            raise ValueError("Unsupported script mode.")

        if self.imported_package is None:
            raise ValueError("Load an Aurora package before running it.")

        if not hasattr(ps, "MethodScript"):
            raise RuntimeError(
                "This PyPalmSens installation does not expose `MethodScript`. "
                "Update PyPalmSens before running imported  packages."
            )

        self.method_label = f"{self.imported_package.name} (step-wise)"
        return build_aurora_stepwise_method(
            self.imported_package,
            self.build_aurora_export_settings(),
        )

    def load_aurora_package_file(self):
        if self.selected_run_mode() != "aurora_package":
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Aurora Package",
            "",
            "Aurora Method Packages (*.psmethod);;JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self.imported_package = load_aurora_package(file_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Load failed",
                f"Could not load Aurora package:\n{exc}",
            )
            return

        self.imported_package_path = Path(file_path)
        self.package_info_label.setText(self.package_summary_text())

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

    def package_summary_text(self) -> str:
        if self.imported_package is None:
            return "No Aurora package loaded."

        source_name = self.imported_package_path.name if self.imported_package_path is not None else "Unknown"
        return (
            f"Package: {self.imported_package.name}\n"
            f"Source file: {source_name}\n"
            f"Run channel for this panel: {self.run_channel()}"
        )

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

        self.aurora_builder_action = QAction("Aurora Builder", self)
        self.aurora_builder_action.setStatusTip("Open the standalone Aurora method builder")
        self.aurora_builder_action.triggered.connect(self.open_aurora_builder)
        toolbar.addAction(self.aurora_builder_action)

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

        self.export_bdf_action = QAction("Export BDF", self)
        self.export_bdf_action.setStatusTip("Export selected channel measurements as BDF files")
        self.export_bdf_action.triggered.connect(self.export_bdf)
        toolbar.addAction(self.export_bdf_action)

        toolbar_spacer = QWidget(toolbar)
        toolbar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(toolbar_spacer)

        self.debug_device_checkbox = QCheckBox("Debug device", toolbar)
        self.debug_device_checkbox.setToolTip(
            "Use a mock 9-channel test device when scanning"
        )
        toolbar.addWidget(self.debug_device_checkbox)

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
            devices = pslib.find_devices(debug_mode=self.debug_device_checkbox.isChecked())
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

        if not self.device_manager.is_connected:
            return

        answer = QMessageBox.question(
            self,
            "Disconnect device?",
            "Are you sure you want to disconnect the device?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.device_manager.disconnect_device()

    def update_connection(self, is_connected: bool):
        self.disconnect_action.setEnabled(is_connected)

    def open_aurora_builder(self):
        project_dir = Path(__file__).parent.parent
        builder_module = f"src.{AURORA_APP_SUBDIRECTORY}.aurora_method_builder_app"
        builder_path = project_dir / "src" / AURORA_APP_SUBDIRECTORY / "aurora_method_builder_app.py"
        started = QProcess.startDetached(sys.executable, ["-m", builder_module], str(project_dir))
        if not started:
            QMessageBox.warning(
                self,
                "Launch failed",
                f"Could not start the Aurora builder:\n{builder_path}",
            )

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

    def export_bdf(self):
        exportable_panels = self._exportable_panels()
        if not exportable_panels:
            QMessageBox.warning(self, "Export error", "No channel measurements available to export.")
            return

        dialog = bdf_export_dialog(exportable_panels, self)
        if not dialog.exec():
            return

        output_dir = dialog.output_directory()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            written_files = []
            selected_panels = dialog.selected_panels()
            cell_name = dialog.cell_name()
            cas_id = dialog.cas_id()
            out_type = dialog.selected_type()
            used_sequence_numbers = set()
            for panel in selected_panels:
                sequence_number = self._next_bdf_sequence_number(
                    output_dir,
                    cell_name,
                    cas_id,
                    out_type,
                    used_sequence_numbers,
                )
                used_sequence_numbers.add(sequence_number)
                filename_stem = self._bdf_export_stem(cell_name, cas_id, sequence_number)
                written_files.extend(
                    export_measurement_to_bdf_files(
                        panel.graph.measurement,
                        output_dir,
                        filename_stem,
                        out_type,
                        dialog.export_separate_measurements(),
                        dialog.selected_optional_quantity_keys(),
                    )
                )
        except BdfExportError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"Failed to export BDF files:\n{exc}")
            return

        self.statusBar().showMessage(f"Exported {len(written_files)} BDF file(s).", 5000)
        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {len(written_files)} BDF file(s) to:\n{output_dir}",
        )

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
        self.start_measurement(panel, method, method_label, dialog.temperature_settings)

    def start_measurement(self, panel: graph_panel, method, method_label: str, temperature_settings=None):
        thread = QThread(self)
        worker = measurement_worker(
            panel.instrument,
            method,
            temperature_settings=temperature_settings,
        )
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
        worker.abort()

    def handle_worker_progress(self, worker, callback_data):
        panel = self.worker_panels.get(worker)
        if panel is None or panel not in self.panels:
            return
        if isinstance(callback_data, TemperatureProgress):
            panel.set_status_text(callback_data.message)
            self.statusBar().showMessage(f"{panel.base_title}: {callback_data.message}", 0)
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
        if panel in self.stopping_panels:
            self.stopping_panels.discard(panel)
            panel.graph.plot_measurement(measurement)
            panel.set_status_text(None)
            self.statusBar().showMessage(f"Stopped measurement on {panel.base_title}.", 5000)
            return

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

    def _exportable_panels(self):
        return [
            panel
            for panel in self.panels
            if panel.graph.measurement is not None
        ]

    @staticmethod
    def _sanitize_export_name(name: str) -> str:
        cleaned = "".join(character if character.isalnum() else "_" for character in name.strip())
        cleaned = cleaned.strip("_")
        return cleaned

    @classmethod
    def _bdf_export_stem(cls, cell_name: str, cas_id: str, sequence_number: int) -> str:
        sanitized_cell_name = cls._sanitize_export_name(cell_name)
        sanitized_cas_id = cls._sanitize_export_name(cas_id)
        export_date = date.today().strftime("%Y%m%d")
        if sanitized_cas_id:
            return f"UU_{sanitized_cell_name}_{sanitized_cas_id}_{export_date}_{sequence_number:04d}"
        return f"UU_{sanitized_cell_name}_{export_date}_{sequence_number:04d}"

    @classmethod
    def _next_bdf_sequence_number(
        cls,
        output_dir: Path,
        cell_name: str,
        cas_id: str,
        export_type: str,
        used_sequence_numbers: set[int],
    ) -> int:
        sequence_number = 1
        while sequence_number in used_sequence_numbers or cls._bdf_sequence_exists(
            output_dir,
            cell_name,
            cas_id,
            sequence_number,
            export_type,
        ):
            sequence_number += 1
        return sequence_number

    @classmethod
    def _bdf_sequence_exists(
        cls,
        output_dir: Path,
        cell_name: str,
        cas_id: str,
        sequence_number: int,
        export_type: str,
    ) -> bool:
        stem = cls._bdf_export_stem(cell_name, cas_id, sequence_number)
        return any(output_dir.glob(f"{stem}*.bdf.{export_type}"))

    def _panel_export_stem(self, panel: graph_panel) -> str:
        instrument = panel.instrument
        if instrument is not None and getattr(instrument, "channel", -1) > 0:
            return f"CH_{instrument.channel}"
        return self._sanitize_export_name(panel.base_title)

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
    app = QApplication()
    app.setStyleSheet(APP_STYLESHEET)
    window = main_window()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
