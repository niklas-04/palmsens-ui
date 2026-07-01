from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import aurora_unicycler
from aurora_unicycler._core import Temperature
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


Parser = Callable[[Any], Any]
SummaryBuilder = Callable[[dict[str, Any]], str]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_required_float(raw_value: Any) -> float:
    value = _as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return float(value)


def parse_optional_float(raw_value: Any) -> float | None:
    value = _as_text(raw_value)
    if not value:
        return None
    return float(value)


def parse_required_int(raw_value: Any) -> int:
    value = _as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return int(value)


def parse_required_text(raw_value: Any) -> str:
    value = _as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return value


def parse_optional_c_rate(raw_value: Any) -> str | None:
    value = _as_text(raw_value)
    return value or None


def parse_bool(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value

    value = _as_text(raw_value).casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Invalid boolean value: {raw_value}")


@dataclass(frozen=True)
class BuilderFieldSpec:
    key: str
    label: str
    default: Any
    parser: Parser
    widget_kind: str = "line"

    def parse(self, raw_value: Any) -> Any:
        try:
            return self.parser(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {self.label}: {raw_value}") from exc


@dataclass(frozen=True)
class BuilderStepSpec:
    key: str
    label: str
    fields: tuple[BuilderFieldSpec, ...]
    builder: Callable[[dict[str, Any]], object]
    summary_builder: SummaryBuilder


RECORD_FIELDS: tuple[BuilderFieldSpec, ...] = (
    BuilderFieldSpec("time_s", "Record interval time (s)", "10", parse_required_float),
    BuilderFieldSpec("voltage_V", "Record voltage delta (V)", "0.01", parse_optional_float),
    BuilderFieldSpec("current_mA", "Record current delta (mA)", "", parse_optional_float),
)

SAFETY_FIELDS: tuple[BuilderFieldSpec, ...] = (
    BuilderFieldSpec("max_voltage_V", "Max voltage (V)", "4.3", parse_optional_float),
    BuilderFieldSpec("min_voltage_V", "Min voltage (V)", "2.5", parse_optional_float),
    BuilderFieldSpec("max_current_mA", "Max current (mA)", "", parse_optional_float),
    BuilderFieldSpec("min_current_mA", "Min current (mA)", "", parse_optional_float),
    BuilderFieldSpec("max_capacity_mAh", "Max capacity (mAh)", "", parse_optional_float),
    BuilderFieldSpec("delay_s", "Safety delay (s)", "", parse_optional_float),
)


def _summary_from_parts(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _current_step_target_summary(params: dict[str, Any]) -> str:
    if params.get("rate_C"):
        return f"{params['rate_C']} C"
    if params.get("current_mA"):
        return f"{params['current_mA']} mA"
    return ""


STEP_SPECS: dict[str, BuilderStepSpec] = {
    "tag": BuilderStepSpec(
        key="tag",
        label="Tag",
        fields=(
            BuilderFieldSpec("tag", "Tag name", "cycle", parse_required_text),
        ),
        builder=lambda params: aurora_unicycler.Tag(tag=params["tag"]),
        summary_builder=lambda params: _summary_from_parts(params.get("tag", "")),
    ),
    "open_circuit_voltage": BuilderStepSpec(
        key="open_circuit_voltage",
        label="Open Circuit Voltage",
        fields=(
            BuilderFieldSpec("until_time_s", "Duration (s)", "600", parse_required_float),
        ),
        builder=lambda params: aurora_unicycler.OpenCircuitVoltage(**params),
        summary_builder=lambda params: _summary_from_parts(f"{params.get('until_time_s', '')} s"),
    ),
    "wait": BuilderStepSpec(
        key="wait",
        label="Wait",
        fields=(
            BuilderFieldSpec("until_time_s", "Duration (s)", "60", parse_required_float),
        ),
        builder=lambda params: aurora_unicycler.Wait(**params),
        summary_builder=lambda params: _summary_from_parts(f"{params.get('until_time_s', '')} s"),
    ),
    "temperature": BuilderStepSpec(
        key="temperature",
        label="Temperature",
        fields=(
            BuilderFieldSpec("until_temp_c", "Target temperature (degC)", "25", parse_required_float),
            BuilderFieldSpec("wait_after_s", "Wait after target (s)", "60", parse_required_float),
            BuilderFieldSpec("ramp_rate", "Ramp rate (degC/min)", "0.35", parse_required_float),
        ),
        builder=lambda params: Temperature(**params),
        summary_builder=lambda params: _summary_from_parts(
            f"{params.get('until_temp_c', '')} degC",
            f"{params.get('ramp_rate', '')} degC/min" if params.get("ramp_rate") else "",
            f"wait {params.get('wait_after_s', '')} s" if params.get("wait_after_s") else "",
            "INTE IMPLEMENTERAD",
        ),
    ),
    "constant_current": BuilderStepSpec(
        key="constant_current",
        label="Constant Current",
        fields=(
            BuilderFieldSpec("rate_C", "Rate (C)", "0.5", parse_optional_c_rate),
            BuilderFieldSpec("current_mA", "Current (mA)", "", parse_optional_float),
            BuilderFieldSpec("until_time_s", "Max time (s)", "10800", parse_optional_float),
            BuilderFieldSpec("until_voltage_V", "Stop at voltage (V)", "4.2", parse_optional_float),
        ),
        builder=lambda params: aurora_unicycler.ConstantCurrent(**params),
        summary_builder=lambda params: _summary_from_parts(
            _current_step_target_summary(params),
            f"until {params.get('until_voltage_V', '')} V" if params.get("until_voltage_V") else "",
            f"max {params.get('until_time_s', '')} s" if params.get("until_time_s") else "",
        ),
    ),
    "constant_voltage": BuilderStepSpec(
        key="constant_voltage",
        label="Constant Voltage",
        fields=(
            BuilderFieldSpec("voltage_V", "Voltage (V)", "4.2", parse_required_float),
            BuilderFieldSpec("until_time_s", "Max time (s)", "3600", parse_optional_float),
            BuilderFieldSpec("until_rate_C", "Stop at rate (C)", "0.05", parse_optional_c_rate),
            BuilderFieldSpec("until_current_mA", "Stop at current (mA)", "", parse_optional_float),
        ),
        builder=lambda params: aurora_unicycler.ConstantVoltage(**params),
        summary_builder=lambda params: _summary_from_parts(
            f"{params.get('voltage_V', '')} V",
            f"until {params.get('until_rate_C', '')} C" if params.get("until_rate_C") else "",
            f"until {params.get('until_current_mA', '')} mA" if params.get("until_current_mA") else "",
            f"max {params.get('until_time_s', '')} s" if params.get("until_time_s") else "",
        ),
    ),
    "voltage_scan": BuilderStepSpec(
        key="voltage_scan",
        label="Voltage Scan",
        fields=(
            BuilderFieldSpec("start_voltage_V", "Start voltage (V)", "3.0", parse_required_float),
            BuilderFieldSpec("end_voltage_V", "End voltage (V)", "4.2", parse_required_float),
            BuilderFieldSpec("scan_rate_mV_per_s", "Scan rate (mV/s)", "10", parse_required_float),
        ),
        builder=lambda params: aurora_unicycler.VoltageScan(**params),
        summary_builder=lambda params: _summary_from_parts(
            f"{params.get('start_voltage_V', '')} -> {params.get('end_voltage_V', '')} V",
            f"{params.get('scan_rate_mV_per_s', '')} mV/s",
        ),
    ),
    "impedance_spectroscopy": BuilderStepSpec(
        key="impedance_spectroscopy",
        label="Impedance Spectroscopy",
        fields=(
            BuilderFieldSpec("amplitude_V", "Amplitude (V)", "0.01", parse_optional_float),
            BuilderFieldSpec("amplitude_mA", "Amplitude (mA)", "", parse_optional_float),
            BuilderFieldSpec("start_frequency_Hz", "Start frequency (Hz)", "10000", parse_required_float),
            BuilderFieldSpec("end_frequency_Hz", "End frequency (Hz)", "0.1", parse_required_float),
            BuilderFieldSpec("points_per_decade", "Points per decade", "10", parse_required_int),
            BuilderFieldSpec("measures_per_point", "Measures per point", "1", parse_required_int),
            BuilderFieldSpec(
                "drift_correction",
                "Drift correction",
                False,
                parse_bool,
                widget_kind="bool",
            ),
        ),
        builder=lambda params: aurora_unicycler.ImpedanceSpectroscopy(**params),
        summary_builder=lambda params: _summary_from_parts(
            f"{params.get('start_frequency_Hz', '')} -> {params.get('end_frequency_Hz', '')} Hz",
            f"{params.get('amplitude_V', '')} V" if params.get("amplitude_V") else "",
            f"{params.get('amplitude_mA', '')} mA" if params.get("amplitude_mA") else "",
        ),
    ),
}

STEP_ORDER = (
    "tag",
    "open_circuit_voltage",
    "wait",
    "temperature",
    "constant_current",
    "constant_voltage",
    "voltage_scan",
    "impedance_spectroscopy",
    "loop",
)


def default_visual_builder_data() -> dict[str, Any]:
    return {
        "record": {"time_s": "10", "voltage_V": "0.01", "current_mA": ""},
        "safety": {
            "max_voltage_V": "4.3",
            "min_voltage_V": "2.5",
            "max_current_mA": "",
            "min_current_mA": "",
            "max_capacity_mAh": "",
            "delay_s": "",
        },
        "method": [],
    }


def default_protocol_data() -> dict[str, Any]:
    return {
        **default_visual_builder_data(),
        "method": [
            {"step": "tag", "tag": "cycle"},
            {
                "step": "constant_current",
                "rate_C": "0.5",
                "current_mA": "",
                "until_time_s": "10800",
                "until_voltage_V": "4.2",
            },
            {
                "step": "constant_voltage",
                "voltage_V": "4.2",
                "until_time_s": "3600",
                "until_rate_C": "0.05",
                "until_current_mA": "",
            },
            {
                "step": "constant_current",
                "rate_C": "-0.5",
                "current_mA": "",
                "until_time_s": "10800",
                "until_voltage_V": "3.0",
            },
            {
                "step": "loop",
                "loop_to_mode": "tag",
                "loop_to_tag": "cycle",
                "loop_to_step": "",
                "cycle_count": "10",
            },
        ],
    }


def _parse_fields(field_specs: tuple[BuilderFieldSpec, ...], raw_values: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for field in field_specs:
        parsed[field.key] = field.parse(raw_values.get(field.key, field.default))
    return parsed


def _clean_none_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def build_protocol_from_visual_data(protocol_data: dict[str, Any]) -> aurora_unicycler.CyclingProtocol:
    record = aurora_unicycler.RecordParams(
        **_clean_none_values(_parse_fields(RECORD_FIELDS, protocol_data.get("record", {})))
    )
    safety = aurora_unicycler.SafetyParams(
        **_clean_none_values(_parse_fields(SAFETY_FIELDS, protocol_data.get("safety", {})))
    )

    method_steps = []
    for index, raw_step in enumerate(protocol_data.get("method", []), start=1):
        step_type = raw_step.get("step")
        if step_type == "loop":
            try:
                cycle_count = parse_required_int(raw_step.get("cycle_count", ""))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid value for Loop cycle count at step {index}: {raw_step.get('cycle_count', '')}"
                ) from exc
            loop_mode = _as_text(raw_step.get("loop_to_mode", "tag")) or "tag"
            if loop_mode == "step":
                try:
                    loop_to = parse_required_int(raw_step.get("loop_to_step", ""))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid value for Loop step target at step {index}: {raw_step.get('loop_to_step', '')}"
                    ) from exc
            else:
                loop_to = _as_text(raw_step.get("loop_to_tag", ""))
                if not loop_to:
                    raise ValueError(f"Loop target tag is required for step {index}.")
            method_steps.append(
                aurora_unicycler.Loop(loop_to=loop_to, cycle_count=cycle_count)
            )
            continue

        spec = STEP_SPECS.get(step_type)
        if spec is None:
            raise ValueError(f"Unsupported Aurora step type: {step_type}")
        params = _clean_none_values(_parse_fields(spec.fields, raw_step))
        method_steps.append(spec.builder(params))

    if not method_steps:
        raise ValueError("Add at least one Aurora step to the sequence.")

    return aurora_unicycler.CyclingProtocol(
        record=record,
        safety=safety,
        method=method_steps,
    )


class AuroraStepCard(QFrame):
    changed = Signal()
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    remove_requested = Signal(object)
    expanded_requested = Signal(object)

    def __init__(self, step_type: str, raw_values: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.step_type = step_type
        self.field_widgets: dict[str, QWidget] = {}
        self.field_labels: dict[QWidget, QLabel] = {}
        self.field_position = 0
        self._expanded = True
        self.setObjectName("auroraStepCard")
        self.setProperty("stepType", step_type)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        layout.addLayout(header_layout)

        self.index_label = QLabel(self)
        self.index_label.setObjectName("auroraStepIndex")
        header_layout.addWidget(self.index_label, 0)

        self.title_label = QLabel(self)
        self.title_label.setObjectName("auroraStepTitle")
        header_layout.addWidget(self.title_label, 0)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("auroraStepSummary")
        self.summary_label.setWordWrap(False)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header_layout.addWidget(self.summary_label, 1)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)
        header_layout.addLayout(button_layout)

        self.move_up_button = QPushButton("Up", self)
        self.move_up_button.setObjectName("auroraStepAction")
        self.move_up_button.setFixedWidth(44)
        self.move_up_button.clicked.connect(lambda: self.move_up_requested.emit(self))
        button_layout.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("Down", self)
        self.move_down_button.setObjectName("auroraStepAction")
        self.move_down_button.setFixedWidth(58)
        self.move_down_button.clicked.connect(lambda: self.move_down_requested.emit(self))
        button_layout.addWidget(self.move_down_button)

        self.remove_button = QPushButton("Remove", self)
        self.remove_button.setObjectName("auroraStepAction")
        self.remove_button.setFixedWidth(72)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        button_layout.addWidget(self.remove_button)

        self.toggle_button = QPushButton(self)
        self.toggle_button.setObjectName("auroraStepAction")
        self.toggle_button.setText("Hide")
        self.toggle_button.setFixedWidth(48)
        self.toggle_button.clicked.connect(lambda: self.expanded_requested.emit(self))
        button_layout.addWidget(self.toggle_button)

        self.form_widget = QWidget(self)
        self.form_layout = QGridLayout(self.form_widget)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setHorizontalSpacing(8)
        self.form_layout.setVerticalSpacing(4)
        layout.addWidget(self.form_widget)

        if self.step_type == "loop":
            self._build_loop_fields(raw_values or {})
        else:
            self._build_generic_fields(raw_values or {})

        self.update_header(0)

    def _build_generic_fields(self, raw_values: dict[str, Any]):
        spec = STEP_SPECS[self.step_type]
        for field in spec.fields:
            if field.widget_kind == "bool":
                widget = QComboBox(self)
                widget.addItem("No", False)
                widget.addItem("Yes", True)
                raw_value = raw_values.get(field.key, field.default)
                widget.setCurrentIndex(1 if parse_bool(raw_value) else 0)
                widget.currentIndexChanged.connect(self._on_field_changed)
            else:
                widget = QLineEdit(_as_text(raw_values.get(field.key, field.default)), self)
                widget.textChanged.connect(self._on_field_changed)
            self.field_widgets[field.key] = widget
            self._add_compact_field(field.label, widget)

    def _build_loop_fields(self, raw_values: dict[str, Any]):
        self.loop_target_mode = QComboBox(self)
        self.loop_target_mode.addItem("Tag", "tag")
        self.loop_target_mode.addItem("Step number", "step")
        raw_mode = _as_text(raw_values.get("loop_to_mode", "tag")) or "tag"
        self.loop_target_mode.setCurrentIndex(1 if raw_mode == "step" else 0)
        self.loop_target_mode.currentIndexChanged.connect(self._on_loop_mode_changed)
        self.loop_target_mode.currentIndexChanged.connect(self._on_field_changed)
        self._add_compact_field("Loop target", self.loop_target_mode)

        self.loop_target_tag = QComboBox(self)
        self.loop_target_tag.setEditable(True)
        self.loop_target_tag.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        initial_tag = _as_text(raw_values.get("loop_to_tag", ""))
        if initial_tag:
            self.loop_target_tag.addItem(initial_tag, initial_tag)
            self.loop_target_tag.setCurrentIndex(0)
            self.loop_target_tag.setEditText(initial_tag)
        self.loop_target_tag.currentTextChanged.connect(self._on_field_changed)
        self._add_compact_field("Tag target", self.loop_target_tag)

        self.loop_target_step = QLineEdit(_as_text(raw_values.get("loop_to_step", "")), self)
        self.loop_target_step.textChanged.connect(self._on_field_changed)
        self._add_compact_field("Step target", self.loop_target_step)

        self.loop_cycle_count = QLineEdit(_as_text(raw_values.get("cycle_count", "10")), self)
        self.loop_cycle_count.textChanged.connect(self._on_field_changed)
        self._add_compact_field("Cycle count", self.loop_cycle_count)

        self._on_loop_mode_changed()

    def _add_compact_field(self, label_text: str, widget: QWidget):
        label = QLabel(label_text, self.form_widget)
        label.setObjectName("auroraCompactFieldLabel")
        column_pair = self.field_position % 2
        row = self.field_position // 2
        label_column = column_pair * 2
        field_column = label_column + 1
        self.form_layout.addWidget(label, row, label_column)
        self.form_layout.addWidget(widget, row, field_column)
        self.form_layout.setColumnStretch(field_column, 1)
        self.field_labels[widget] = label
        self.field_position += 1

    def _on_loop_mode_changed(self):
        use_tag = self.loop_target_mode.currentData() == "tag"
        self.loop_target_tag.setVisible(use_tag)
        self.loop_target_step.setVisible(not use_tag)
        tag_label = self.field_labels.get(self.loop_target_tag)
        step_label = self.field_labels.get(self.loop_target_step)
        if tag_label is not None:
            tag_label.setVisible(use_tag)
        if step_label is not None:
            step_label.setVisible(not use_tag)

    def _on_field_changed(self, *_args):
        self.changed.emit()

    def set_tag_options(self, tags: list[str]):
        if self.step_type != "loop":
            return

        current_text = self.loop_target_tag.currentText().strip()
        self.loop_target_tag.blockSignals(True)
        self.loop_target_tag.clear()
        for tag in tags:
            self.loop_target_tag.addItem(tag, tag)
        if current_text and current_text not in tags:
            self.loop_target_tag.addItem(current_text, current_text)
        if current_text:
            self.loop_target_tag.setEditText(current_text)
        elif self.loop_target_tag.count():
            self.loop_target_tag.setCurrentIndex(0)
        self.loop_target_tag.blockSignals(False)

    def raw_values(self) -> dict[str, Any]:
        if self.step_type == "loop":
            return {
                "step": "loop",
                "loop_to_mode": self.loop_target_mode.currentData(),
                "loop_to_tag": self.loop_target_tag.currentText().strip(),
                "loop_to_step": self.loop_target_step.text().strip(),
                "cycle_count": self.loop_cycle_count.text().strip(),
            }

        values = {"step": self.step_type}
        for field in STEP_SPECS[self.step_type].fields:
            widget = self.field_widgets[field.key]
            if field.widget_kind == "bool":
                values[field.key] = widget.currentData()
            else:
                values[field.key] = widget.text().strip()
        return values

    def update_header(self, index: int):
        label = "Loop" if self.step_type == "loop" else STEP_SPECS[self.step_type].label
        self.index_label.setText(f"{index + 1}")
        self.title_label.setText(label)
        self.summary_label.setText(self.summary_text())

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self.form_widget.setVisible(expanded)
        self.toggle_button.setText("Hide" if expanded else "Edit")

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def summary_text(self) -> str:
        values = self.raw_values()
        if self.step_type == "loop":
            target = (
                values.get("loop_to_tag", "")
                if values.get("loop_to_mode") == "tag"
                else values.get("loop_to_step", "")
            )
            if not target:
                return "Set a loop target and cycle count."
            return _summary_from_parts(
                f"to {values.get('loop_to_mode')} {target}",
                f"x{values.get('cycle_count', '')}",
            )

        summary = STEP_SPECS[self.step_type].summary_builder(values).strip()
        return summary or "Configure this Aurora step."


class AuroraVisualBuilder(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step_cards: list[AuroraStepCard] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)

        self.sequence_frame = QFrame(self)
        self.sequence_frame.setObjectName("auroraSection")
        self.sequence_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sequence_layout = QVBoxLayout(self.sequence_frame)
        sequence_layout.setContentsMargins(14, 14, 14, 14)
        sequence_layout.setSpacing(10)

        sequence_header = QHBoxLayout()
        sequence_header.setContentsMargins(0, 0, 0, 0)
        sequence_header.setSpacing(8)
        sequence_layout.addLayout(sequence_header)

        sequence_label = QLabel("Sequence", self.sequence_frame)
        sequence_label.setObjectName("auroraSectionTitle")
        sequence_header.addWidget(sequence_label, 1)

        self.sequence_meta_label = QLabel(self.sequence_frame)
        self.sequence_meta_label.setObjectName("auroraSequenceMeta")
        sequence_header.addWidget(self.sequence_meta_label)

        self.step_type_combo = QComboBox(self.sequence_frame)
        for step_key in STEP_ORDER:
            label = "Loop" if step_key == "loop" else STEP_SPECS[step_key].label
            self.step_type_combo.addItem(label, step_key)
        sequence_header.addWidget(self.step_type_combo)

        self.add_step_button = QPushButton("Add Step", self.sequence_frame)
        self.add_step_button.setObjectName("auroraAddStepButton")
        self.add_step_button.clicked.connect(self.add_selected_step)
        sequence_header.addWidget(self.add_step_button)

        self.focus_sequence_button = QPushButton("Focus", self.sequence_frame)
        self.focus_sequence_button.setObjectName("auroraAddStepButton")
        self.focus_sequence_button.setCheckable(True)
        self.focus_sequence_button.toggled.connect(self.set_sequence_focus)
        sequence_header.addWidget(self.focus_sequence_button)

        self.steps_scroll = QScrollArea(self.sequence_frame)
        self.steps_scroll.setObjectName("auroraStepsScroll")
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sequence_layout.addWidget(self.steps_scroll, 1)

        self.steps_container = QWidget(self.steps_scroll)
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(10)
        self.steps_layout.addStretch(1)
        self.steps_scroll.setWidget(self.steps_container)

        self.splitter.addWidget(self.sequence_frame)

        self.options_column = QWidget(self)
        options_layout = QVBoxLayout(self.options_column)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(12)

        self.context_widget_holder = QWidget(self.options_column)
        self.context_widget_layout = QVBoxLayout(self.context_widget_holder)
        self.context_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.context_widget_layout.setSpacing(0)
        options_layout.addWidget(self.context_widget_holder)

        self.record_frame = self._build_section(
            "Recording",
            RECORD_FIELDS,
        )
        self.safety_frame = self._build_section(
            "Safety",
            SAFETY_FIELDS,
        )
        options_layout.addWidget(self.record_frame)
        options_layout.addWidget(self.safety_frame)
        options_layout.addStretch(1)
        self.splitter.addWidget(self.options_column)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.load_protocol_data(default_visual_builder_data())

    def set_sequence_focus(self, focused: bool):
        self.options_column.setVisible(not focused)
        self.focus_sequence_button.setText("Show Settings" if focused else "Focus")
        if focused:
            self.splitter.setSizes([1, 0])
        else:
            self.splitter.setSizes([3, 2])

    def _build_section(
        self,
        title: str,
        field_specs: tuple[BuilderFieldSpec, ...],
    ) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("auroraSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        label = QLabel(title, frame)
        label.setObjectName("auroraSectionTitle")
        layout.addWidget(label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        for field in field_specs:
            if field.widget_kind == "bool":
                widget = QComboBox(frame)
                widget.addItem("No", False)
                widget.addItem("Yes", True)
                widget.setCurrentIndex(1 if parse_bool(field.default) else 0)
                widget.currentIndexChanged.connect(self.changed.emit)
            else:
                widget = QLineEdit(_as_text(field.default), frame)
                widget.textChanged.connect(self.changed.emit)
            form.addRow(field.label, widget)
            setattr(self, f"{field.key}_widget", widget)

        return frame

    def raw_data(self) -> dict[str, Any]:
        record = self._raw_section(RECORD_FIELDS)
        safety = self._raw_section(SAFETY_FIELDS)
        method = [card.raw_values() for card in self.step_cards]
        return {"record": record, "safety": safety, "method": method}

    def build_protocol(self) -> aurora_unicycler.CyclingProtocol:
        return build_protocol_from_visual_data(self.raw_data())

    def add_selected_step(self):
        self.add_step(self.step_type_combo.currentData())

    def add_step(self, step_type: str, raw_values: dict[str, Any] | None = None, index: int | None = None):
        card = AuroraStepCard(step_type, raw_values=raw_values, parent=self.steps_container)
        card.changed.connect(self._refresh_cards)
        card.move_up_requested.connect(lambda current: self.move_step(current, -1))
        card.move_down_requested.connect(lambda current: self.move_step(current, 1))
        card.remove_requested.connect(self.remove_step)
        card.expanded_requested.connect(self.toggle_card_expanded)

        insert_index = len(self.step_cards) if index is None else max(0, min(index, len(self.step_cards)))
        self.step_cards.insert(insert_index, card)
        self.steps_layout.insertWidget(insert_index, card)
        self.set_expanded_card(card)
        self._refresh_cards()

    def remove_step(self, card: AuroraStepCard):
        if card not in self.step_cards:
            return
        self.step_cards.remove(card)
        self.steps_layout.removeWidget(card)
        card.deleteLater()
        self._refresh_cards()

    def move_step(self, card: AuroraStepCard, offset: int):
        if card not in self.step_cards:
            return

        old_index = self.step_cards.index(card)
        new_index = old_index + offset
        if new_index < 0 or new_index >= len(self.step_cards):
            return

        self.step_cards.insert(new_index, self.step_cards.pop(old_index))
        self.steps_layout.removeWidget(card)
        self.steps_layout.insertWidget(new_index, card)
        self._refresh_cards()

    def set_context_widget(self, widget: QWidget | None):
        while self.context_widget_layout.count():
            item = self.context_widget_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)

        if widget is not None:
            self.context_widget_layout.addWidget(widget)

    def toggle_card_expanded(self, card: AuroraStepCard):
        if card.is_expanded:
            card.set_expanded(False)
            return
        self.set_expanded_card(card)

    def set_expanded_card(self, card: AuroraStepCard | None):
        for current in self.step_cards:
            current.set_expanded(current is card if card is not None else False)

    def load_protocol_data(self, protocol_data: dict[str, Any]):
        self._set_section(RECORD_FIELDS, protocol_data.get("record", {}))
        self._set_section(SAFETY_FIELDS, protocol_data.get("safety", {}))

        for card in list(self.step_cards):
            self.steps_layout.removeWidget(card)
            card.deleteLater()
        self.step_cards.clear()

        for raw_step in protocol_data.get("method", []):
            self.add_step(raw_step.get("step", "constant_current"), raw_values=raw_step)

        if self.step_cards:
            self.set_expanded_card(self.step_cards[0])
        self._refresh_cards()

    def _refresh_cards(self, *_args):
        available_tags: list[str] = []
        for index, card in enumerate(self.step_cards):
            card.update_header(index)
            card.move_up_button.setEnabled(index > 0)
            card.move_down_button.setEnabled(index < len(self.step_cards) - 1)
            if card.step_type == "loop":
                card.set_tag_options(available_tags)
            elif card.step_type == "tag":
                tag_name = _as_text(card.raw_values().get("tag"))
                if tag_name:
                    available_tags.append(tag_name)
        count = len(self.step_cards)
        self.sequence_meta_label.setText(
            "No steps yet" if count == 0 else f"{count} step{'s' if count != 1 else ''}"
        )
        self.changed.emit()

    def _raw_section(self, field_specs: tuple[BuilderFieldSpec, ...]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in field_specs:
            widget = getattr(self, f"{field.key}_widget")
            if field.widget_kind == "bool":
                values[field.key] = widget.currentData()
            else:
                values[field.key] = widget.text().strip()
        return values

    def _set_section(self, field_specs: tuple[BuilderFieldSpec, ...], raw_values: dict[str, Any]):
        for field in field_specs:
            widget = getattr(self, f"{field.key}_widget")
            raw_value = raw_values.get(field.key, field.default)
            if field.widget_kind == "bool":
                widget.setCurrentIndex(1 if parse_bool(raw_value) else 0)
            else:
                widget.setText(_as_text(raw_value))
