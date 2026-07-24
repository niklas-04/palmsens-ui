from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from src.aurora_app.aurora_builder import NoScrollComboBox
from src.aurora_app.aurora_methods import (
    AURORA_ADDITIONAL_MEASUREMENT_DESCRIPTIONS,
    AURORA_ADDITIONAL_MEASUREMENT_OPTIONS,
    AURORA_DEVICE_MEASUREMENT_TYPES,
    AURORA_DEVICE_OPTIONS,
    AuroraExportSettings,
)


class AuroraMethodScriptExportDialog(QDialog):
    """Collect the values needed to convert an Aurora package to MethodSCRIPT."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export to MethodSCRIPT")
        self.resize(560, 520)
        self.export_settings: AuroraExportSettings | None = None

        layout = QVBoxLayout(self)

        help_label = QLabel(
            "Capacity is required for methods that use C-rate steps. "
            "Other blank values use the package or exporter defaults.",
            self,
        )
        help_label.setObjectName("auroraHelpText")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        form = QFormLayout()
        layout.addLayout(form)

        self.sample_name_edit = QLineEdit(self)
        form.addRow("Sample name", self.sample_name_edit)

        self.capacity_edit = QLineEdit(self)
        form.addRow("Capacity (mAh)", self.capacity_edit)

        self.device_combo = NoScrollComboBox(self)
        for label, value in AURORA_DEVICE_OPTIONS:
            self.device_combo.addItem(label, value)
        form.addRow("PalmSens target", self.device_combo)

        self.scan_step_edit = QLineEdit(self)
        form.addRow("Scan step voltage (V)", self.scan_step_edit)

        self.eis_dc_potential_edit = QLineEdit("0.0", self)
        form.addRow("EIS DC potential (V)", self.eis_dc_potential_edit)

        self.eis_dc_current_edit = QLineEdit("0.0", self)
        form.addRow("EIS DC current (mA)", self.eis_dc_current_edit)

        extra_measurements_label = QLabel("Extra measurements", self)
        extra_measurements_label.setObjectName("auroraCardTitle")
        layout.addWidget(extra_measurements_label)

        extra_measurements_widget = QWidget(self)
        extra_measurements_layout = QGridLayout(extra_measurements_widget)
        extra_measurements_layout.setContentsMargins(0, 0, 0, 0)
        self.additional_measurement_checks: dict[str, QCheckBox] = {}
        for index, (var_type, label) in enumerate(
            AURORA_ADDITIONAL_MEASUREMENT_OPTIONS
        ):
            checkbox = QCheckBox(label, extra_measurements_widget)
            description = AURORA_ADDITIONAL_MEASUREMENT_DESCRIPTIONS[var_type]
            checkbox.setToolTip(
                f"{description}\nMethodSCRIPT variable type: {var_type} "
                "(added with add_meas)."
            )
            self.additional_measurement_checks[var_type] = checkbox
            extra_measurements_layout.addWidget(checkbox, index // 2, index % 2)
        layout.addWidget(extra_measurements_widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.device_combo.currentIndexChanged.connect(
            self._update_additional_measurements
        )
        self._update_additional_measurements()

    def accept(self) -> None:
        try:
            self.export_settings = self.build_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid export settings", str(exc))
            return
        super().accept()

    def build_settings(self) -> AuroraExportSettings:
        return AuroraExportSettings(
            sample_name=self.sample_name_edit.text().strip() or None,
            capacity_mAh=self._optional_float(self.capacity_edit, "Capacity (mAh)"),
            device_key=self.device_combo.currentData(),
            channel=0,
            scan_step_voltage_v=self._optional_float(
                self.scan_step_edit,
                "Scan step voltage (V)",
            ),
            eis_dc_potential_v=self._float(
                self.eis_dc_potential_edit,
                "EIS DC potential (V)",
            ),
            eis_dc_current_ma=self._float(
                self.eis_dc_current_edit,
                "EIS DC current (mA)",
            ),
            additional_measurements=tuple(
                var_type
                for var_type, checkbox in self.additional_measurement_checks.items()
                if checkbox.isEnabled() and checkbox.isChecked()
            ),
        )

    def _update_additional_measurements(self) -> None:
        supported = AURORA_DEVICE_MEASUREMENT_TYPES.get(
            self.device_combo.currentData(), set()
        )
        for var_type, checkbox in self.additional_measurement_checks.items():
            checkbox.setEnabled(var_type in supported)
            if not checkbox.isEnabled():
                checkbox.setChecked(False)

    @staticmethod
    def _float(widget: QLineEdit, label: str) -> float:
        value = AuroraMethodScriptExportDialog._optional_float(widget, label)
        if value is None:
            raise ValueError(f"{label} is required.")
        return value

    @staticmethod
    def _optional_float(widget: QLineEdit, label: str) -> float | None:
        raw_value = widget.text().strip()
        if not raw_value:
            return None
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {label}: {raw_value}") from exc
