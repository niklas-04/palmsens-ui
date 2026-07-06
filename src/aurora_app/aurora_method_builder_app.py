from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.app_style import APP_STYLESHEET
from src.aurora_app.aurora_builder import AuroraVisualBuilder
from src.aurora_app.aurora_methods import (
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
        self.rebuild_mode()

    def selected_run_mode(self) -> str:
        return self.run_mode_combo.currentData()

    def rebuild_mode(self):
        run_mode = self.selected_run_mode()
        visual_mode = run_mode == "aurora_visual"
        self.visual_builder.set_context_widget(None)
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


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = AuroraMethodBuilderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
