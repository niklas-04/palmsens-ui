from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app_style import APP_STYLESHEET
from aurora_builder import AuroraVisualBuilder
from aurora_methods import (
    AURORA_ADDITIONAL_MEASUREMENT_OPTIONS,
    AURORA_DEVICE_MEASUREMENT_TYPES,
    AURORA_DEVICE_OPTIONS,
    AuroraExportSettings,
    build_aurora_package,
    load_aurora_package,
)


class AuroraMethodEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.loaded_package_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.header_form = QFormLayout()
        self.header_form.setContentsMargins(0, 0, 0, 0)
        self.header_form.setHorizontalSpacing(12)
        self.header_form.setVerticalSpacing(8)
        layout.addLayout(self.header_form)

        self.method_name_edit = QLineEdit("Aurora Method", self)
        self.header_form.addRow("Method name", self.method_name_edit)

        self.run_mode_combo = QComboBox(self)
        self.run_mode_combo.addItem("Aurora Visual Builder", "aurora_visual")
        self.run_mode_combo.addItem("Aurora Unicycler JSON", "aurora_json")
        self.run_mode_combo.addItem("Aurora Unicycler Python", "aurora_python")
        self.header_form.addRow("Mode", self.run_mode_combo)

        self.aurora_options = QWidget(self)
        self.aurora_options_layout = QHBoxLayout(self.aurora_options)
        self.aurora_options_layout.setContentsMargins(0, 0, 0, 0)
        self.aurora_options_layout.setSpacing(12)

        device_card, device_card_layout = self.build_card("Device & Data")
        self.aurora_options_layout.addWidget(device_card, 3)

        device_form = QFormLayout()
        device_form.setContentsMargins(0, 0, 0, 0)
        device_form.setHorizontalSpacing(12)
        device_form.setVerticalSpacing(8)
        device_card_layout.addLayout(device_form)

        self.aurora_device_combo = QComboBox(self)
        for label, value in AURORA_DEVICE_OPTIONS:
            self.aurora_device_combo.addItem(label, value)
        device_form.addRow("PalmSens target", self.aurora_device_combo)

        extra_measurements_label = QLabel("Extra measurements", self)
        extra_measurements_label.setObjectName("auroraCardTitle")
        device_card_layout.addWidget(extra_measurements_label)

        self.additional_measurement_checks: dict[str, QCheckBox] = {}
        self.additional_measurement_widget = QWidget(self)
        self.additional_measurement_layout = QGridLayout(self.additional_measurement_widget)
        self.additional_measurement_layout.setContentsMargins(0, 0, 0, 0)
        self.additional_measurement_layout.setHorizontalSpacing(16)
        self.additional_measurement_layout.setVerticalSpacing(6)
        for index, (var_type, label) in enumerate(AURORA_ADDITIONAL_MEASUREMENT_OPTIONS):
            checkbox = QCheckBox(label, self.additional_measurement_widget)
            checkbox.setToolTip(f"Measure MethodSCRIPT variable type {var_type} with add_meas.")
            self.additional_measurement_checks[var_type] = checkbox
            self.additional_measurement_layout.addWidget(checkbox, index // 2, index % 2)
        device_card_layout.addWidget(self.additional_measurement_widget)

        run_card, run_card_layout = self.build_card("Run Settings")
        self.aurora_options_layout.addWidget(run_card, 2)

        run_columns = QHBoxLayout()
        run_columns.setContentsMargins(0, 0, 0, 0)
        run_columns.setSpacing(12)
        run_card_layout.addLayout(run_columns)

        run_left = QFormLayout()
        run_left.setContentsMargins(0, 0, 0, 0)
        run_left.setHorizontalSpacing(12)
        run_left.setVerticalSpacing(8)
        run_right = QFormLayout()
        run_right.setContentsMargins(0, 0, 0, 0)
        run_right.setHorizontalSpacing(12)
        run_right.setVerticalSpacing(8)
        run_columns.addLayout(run_left, 1)
        run_columns.addLayout(run_right, 1)

        self.sample_name_edit = QLineEdit("", self)
        run_left.addRow("Sample name", self.sample_name_edit)

        self.capacity_edit = QLineEdit("", self)
        run_left.addRow("Capacity (mAh)", self.capacity_edit)

        self.channel_edit = QLineEdit("0", self)
        run_left.addRow("PGStat channel", self.channel_edit)

        self.scan_step_edit = QLineEdit("", self)
        run_right.addRow("Scan step voltage (V)", self.scan_step_edit)

        self.eis_dc_potential_edit = QLineEdit("0.0", self)
        run_right.addRow("EIS DC potential (V)", self.eis_dc_potential_edit)

        self.eis_dc_current_edit = QLineEdit("0.0", self)
        run_right.addRow("EIS DC current (mA)", self.eis_dc_current_edit)

        self.aurora_options_host = QWidget(self)
        self.aurora_options_host_layout = QVBoxLayout(self.aurora_options_host)
        self.aurora_options_host_layout.setContentsMargins(0, 0, 0, 0)
        self.aurora_options_host_layout.addWidget(self.aurora_options)
        layout.addWidget(self.aurora_options_host)

        self.script_help = QLabel(self)
        self.script_help.setObjectName("auroraHelpText")
        self.script_help.setWordWrap(True)
        layout.addWidget(self.script_help)

        self.script_editor = QPlainTextEdit(self)
        self.script_editor.setMinimumHeight(320)
        self.script_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.script_editor, 1)

        self.visual_builder = AuroraVisualBuilder(self)
        layout.addWidget(self.visual_builder, 1)

        self.run_mode_combo.currentIndexChanged.connect(self.rebuild_mode)
        self.aurora_device_combo.currentIndexChanged.connect(self.update_additional_measurements)
        self.update_additional_measurements()
        self.rebuild_mode()

    def build_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame(self)
        card.setObjectName("auroraOptionsCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_label = QLabel(title, card)
        title_label.setObjectName("auroraCardTitle")
        layout.addWidget(title_label)

        return card, layout

    def selected_run_mode(self) -> str:
        return self.run_mode_combo.currentData()

    def update_additional_measurements(self):
        device_key = self.aurora_device_combo.currentData()
        supported = AURORA_DEVICE_MEASUREMENT_TYPES.get(device_key, set())
        for var_type, checkbox in self.additional_measurement_checks.items():
            enabled = var_type in supported
            checkbox.setEnabled(enabled)
            if not enabled:
                checkbox.setChecked(False)

    def set_aurora_options_parent(self, in_visual_builder: bool):
        if in_visual_builder:
            self.visual_builder.set_context_widget(self.aurora_options)
            self.aurora_options_host.setVisible(False)
            return

        self.visual_builder.set_context_widget(None)
        self.aurora_options_host_layout.addWidget(self.aurora_options)
        self.aurora_options_host.setVisible(True)

    def rebuild_mode(self):
        run_mode = self.selected_run_mode()
        visual_mode = run_mode == "aurora_visual"
        self.set_aurora_options_parent(visual_mode)
        self.visual_builder.setVisible(visual_mode)
        self.script_editor.setVisible(not visual_mode)
        self.script_help.setVisible(not visual_mode)

        if run_mode == "aurora_json" and not self.script_editor.toPlainText().strip():
            self.script_editor.setPlainText(self.default_aurora_json())
        elif run_mode == "aurora_python" and not self.script_editor.toPlainText().strip():
            self.script_editor.setPlainText(self.default_aurora_python())

        if run_mode == "aurora_json":
            self.script_help.setText("Edit an Aurora Unicycler protocol JSON object.")
        elif run_mode == "aurora_python":
            self.script_help.setText(
                "Edit a Python script that defines `protocol = CyclingProtocol(...)` "
                "or `build_protocol()`."
            )

    def selected_additional_measurements(self) -> tuple[str, ...]:
        return tuple(
            var_type
            for var_type, checkbox in self.additional_measurement_checks.items()
            if checkbox.isEnabled() and checkbox.isChecked()
        )

    def build_export_settings(self) -> AuroraExportSettings:
        return AuroraExportSettings(
            sample_name=self.sample_name_edit.text().strip() or None,
            capacity_mAh=self.parse_optional_float(self.capacity_edit, "Capacity (mAh)"),
            device_key=self.aurora_device_combo.currentData(),
            channel=self.parse_int(self.channel_edit, "PGStat channel"),
            scan_step_voltage_v=self.parse_optional_float(self.scan_step_edit, "Scan step voltage (V)"),
            eis_dc_potential_v=self.parse_float(self.eis_dc_potential_edit, "EIS DC potential (V)"),
            eis_dc_current_ma=self.parse_float(self.eis_dc_current_edit, "EIS DC current (mA)"),
            additional_measurements=self.selected_additional_measurements(),
        )

    def source_payload(self) -> dict | str:
        if self.selected_run_mode() == "aurora_visual":
            return self.visual_builder.raw_data()
        script_text = self.script_editor.toPlainText()
        if not script_text.strip():
            raise ValueError("Aurora source text is required.")
        return script_text

    def build_package(self):
        method_name = self.method_name_edit.text().strip() or "Aurora Method"
        return build_aurora_package(
            name=method_name,
            source_mode=self.selected_run_mode(),
            source_payload=self.source_payload(),
            settings=self.build_export_settings(),
        )

    def open_package_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Aurora Method Package",
            "",
            "Aurora Method Packages (*.psmethod);;JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            package = load_aurora_package(file_path)
        except Exception as exc:
            QMessageBox.warning(self, "Open failed", f"Could not open package:\n{exc}")
            return

        self.loaded_package_path = Path(file_path)
        self.load_package(package)

    def load_package(self, package):
        self.method_name_edit.setText(package.name)
        run_mode = package.source_mode
        index = self.run_mode_combo.findData(run_mode)
        if index < 0:
            raise ValueError(f"Unsupported saved run mode: {run_mode}")
        self.run_mode_combo.setCurrentIndex(index)

        self.sample_name_edit.setText(package.settings.sample_name or "")
        self.capacity_edit.setText(
            "" if package.settings.capacity_mAh is None else str(package.settings.capacity_mAh)
        )
        self.channel_edit.setText(str(package.settings.channel))
        self.scan_step_edit.setText(
            "" if package.settings.scan_step_voltage_v is None else str(package.settings.scan_step_voltage_v)
        )
        self.eis_dc_potential_edit.setText(str(package.settings.eis_dc_potential_v))
        self.eis_dc_current_edit.setText(str(package.settings.eis_dc_current_ma))

        device_index = self.aurora_device_combo.findData(package.settings.device_key)
        if device_index >= 0:
            self.aurora_device_combo.setCurrentIndex(device_index)

        for checkbox in self.additional_measurement_checks.values():
            checkbox.setChecked(False)
        for var_type in package.settings.additional_measurements:
            checkbox = self.additional_measurement_checks.get(var_type)
            if checkbox is not None and checkbox.isEnabled():
                checkbox.setChecked(True)

        if run_mode == "aurora_visual":
            if not isinstance(package.source_payload, dict):
                raise ValueError("Saved visual package payload is invalid.")
            self.visual_builder.load_protocol_data(package.source_payload)
        else:
            if not isinstance(package.source_payload, str):
                raise ValueError("Saved text package payload is invalid.")
            self.script_editor.setPlainText(package.source_payload)

    def save_package_file(self):
        try:
            package = self.build_package()
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return

        default_name = self.method_name_edit.text().strip() or "aurora_method"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Aurora Method Package",
            f"{default_name}.psmethod",
            "Aurora Method Packages (*.psmethod);;JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        if path.suffix == "":
            path = path.with_suffix(".psmethod")

        try:
            path.write_text(json.dumps(package.to_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", f"Could not save package:\n{exc}")
            return

        self.loaded_package_path = path
        QMessageBox.information(self, "Package saved", f"Saved Aurora package to:\n{path}")

    def export_methodscript_file(self):
        try:
            package = self.build_package()
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return

        default_name = self.method_name_edit.text().strip() or "aurora_method"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export MethodSCRIPT",
            f"{default_name}.mscr",
            "MethodSCRIPT Files (*.mscr);;Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        if path.suffix == "":
            path = path.with_suffix(".mscr")

        try:
            path.write_text(package.methodscript, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not export MethodSCRIPT:\n{exc}")
            return

        QMessageBox.information(self, "MethodSCRIPT exported", f"Exported MethodSCRIPT to:\n{path}")

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
        OpenCircuitVoltage(until_time_s=600),
        ConstantCurrent(rate_C=0.5, until_voltage_V=4.2, until_time_s=3 * 60 * 60),
        ConstantVoltage(voltage_V=4.2, until_rate_C=0.05, until_time_s=60 * 60),
        ConstantCurrent(rate_C=-0.5, until_voltage_V=3.0, until_time_s=3 * 60 * 60),
        Loop(loop_to="cycle", cycle_count=10),
    ],
)
"""


class AuroraMethodBuilderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aurora Method Builder")
        self.resize(1220, 900)

        toolbar = QToolBar("Builder Toolbar", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.editor = AuroraMethodEditor(self)
        self.setCentralWidget(self.editor)

        open_action = QAction("Open Package", self)
        open_action.triggered.connect(self.editor.open_package_file)
        toolbar.addAction(open_action)

        save_action = QAction("Save Package", self)
        save_action.triggered.connect(self.editor.save_package_file)
        toolbar.addAction(save_action)

        export_action = QAction("Export MethodSCRIPT", self)
        export_action.triggered.connect(self.editor.export_methodscript_file)
        toolbar.addAction(export_action)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = AuroraMethodBuilderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
