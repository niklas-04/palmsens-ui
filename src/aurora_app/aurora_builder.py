from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aurora_unicycler
from aurora_unicycler._core import Temperature
from PySide6.QtCore import Qt, Signal
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

Parser = Callable[[Any], Any]
SummaryBuilder = Callable[[dict[str, Any]], str]
FieldValueWidget = QLineEdit | QComboBox


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
class BuilderUnitOption:
    key: str
    label: str
    scale_to_aurora: float = 1.0
    offset_to_aurora: float = 0.0
    # lets one ui field target different Aurora fields based on its selected unit.
    aurora_field: str | None = None

    def to_aurora(self, value: float) -> float:
        return value * self.scale_to_aurora + self.offset_to_aurora


@dataclass(frozen=True)
class BuilderFieldSpec:
    key: str
    label: str
    default: Any
    parser: Parser
    widget_kind: str = "line"
    unit_options: tuple[BuilderUnitOption, ...] = ()

    @property
    def unit_key(self) -> str:
        return f"{self.key}_unit"

    @property
    def default_unit(self) -> str:
        return self.unit_options[0].key if self.unit_options else ""

    def parse_for_aurora(self, raw_value: Any, raw_unit: Any = None) -> tuple[str, Any]:
        try:
            value = self.parser(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {self.label}: {raw_value}") from exc

        if value is None or not self.unit_options:
            return self.key, value

        unit_key = _as_text(raw_unit) or self.default_unit
        unit = next((option for option in self.unit_options if option.key == unit_key), None)
        if unit is None:
            raise ValueError(f"Unsupported unit for {self.label}: {unit_key}")
        return unit.aurora_field or self.key, unit.to_aurora(value)


@dataclass(frozen=True)
class BuilderFieldChoiceOption:
    key: str
    label: str
    field_key: str


@dataclass(frozen=True)
class BuilderFieldChoice:
    key: str
    label: str
    options: tuple[BuilderFieldChoiceOption, ...]

    def selected_key(self, raw_values: dict[str, Any]) -> str:
        selected = _as_text(raw_values.get(self.key))
        if any(option.key == selected for option in self.options):
            return selected
        for option in self.options:
            if _as_text(raw_values.get(option.field_key)):
                return option.key
        return self.options[0].key

    def active_field_key(self, selected: str) -> str:
        return next(option.field_key for option in self.options if option.key == selected)

    def selected_values(
        self, raw_values: dict[str, Any], selected: str | None = None
    ) -> dict[str, Any]:
        values = dict(raw_values)
        selected = selected or self.selected_key(values)
        values[self.key] = selected
        active_field = self.active_field_key(selected)
        for option in self.options:
            if option.field_key != active_field:
                values[option.field_key] = ""
        return values


@dataclass(frozen=True)
class BuilderStepSpec:
    key: str
    label: str
    fields: tuple[BuilderFieldSpec, ...]
    builder: Callable[[dict[str, Any]], object]
    summary_builder: SummaryBuilder
    field_choice: BuilderFieldChoice | None = None


def _unit_field(
    key: str,
    label: str,
    default: Any,
    parser: Parser,
    units: tuple[BuilderUnitOption, ...],
) -> BuilderFieldSpec:
    return BuilderFieldSpec(key, label, default, parser, unit_options=units)


def _set_unit_widget(
    field: BuilderFieldSpec,
    widget: QComboBox,
    raw_values: dict[str, Any],
) -> None:
    unit_key = _as_text(raw_values.get(field.unit_key, field.default_unit))
    widget.setCurrentIndex(max(widget.findData(unit_key), 0))


def _create_field_editor(
    field: BuilderFieldSpec,
    raw_values: dict[str, Any],
    parent: QWidget,
    on_changed: Callable[..., None],
) -> tuple[FieldValueWidget, QWidget, QComboBox | None]:
    raw_value = raw_values.get(field.key, field.default)
    if field.widget_kind == "bool":
        value_widget = QComboBox(parent)
        value_widget.addItem("No", False)
        value_widget.addItem("Yes", True)
        value_widget.setCurrentIndex(1 if parse_bool(raw_value) else 0)
        value_widget.currentIndexChanged.connect(on_changed)
    else:
        value_widget = QLineEdit(_as_text(raw_value), parent)
        value_widget.textChanged.connect(on_changed)

    if not field.unit_options:
        return value_widget, value_widget, None

    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(value_widget, 1)

    unit_widget = QComboBox(container)
    for option in field.unit_options:
        unit_widget.addItem(option.label, option.key)
    _set_unit_widget(field, unit_widget, raw_values)
    unit_widget.currentIndexChanged.connect(on_changed)
    layout.addWidget(unit_widget)
    return value_widget, container, unit_widget


def _read_field_widget(field: BuilderFieldSpec, widget: FieldValueWidget) -> Any:
    if field.widget_kind == "bool":
        return widget.currentData()
    return widget.text().strip()


def _set_field_widget(field: BuilderFieldSpec, widget: FieldValueWidget, raw_value: Any) -> None:
    if field.widget_kind == "bool":
        widget.setCurrentIndex(1 if parse_bool(raw_value) else 0)
    else:
        widget.setText(_as_text(raw_value))


TIME_UNITS = (
    BuilderUnitOption("s", "s"),
    BuilderUnitOption("ms", "ms", 1e-3),
    BuilderUnitOption("min", "min", 60.0),
    BuilderUnitOption("h", "h", 3600.0),
    BuilderUnitOption("d", "d", 86400.0),
)
VOLTAGE_UNITS = (
    BuilderUnitOption("V", "V"),
    BuilderUnitOption("mV", "mV", 1e-3),
    BuilderUnitOption("uV", "µV", 1e-6),
)
CURRENT_UNITS = (
    BuilderUnitOption("mA", "mA"),
    BuilderUnitOption("uA", "µA", 1e-3),
    BuilderUnitOption("A", "A", 1e3),
)
EIS_AMPLITUDE_UNITS = (
    BuilderUnitOption("V", "V", aurora_field="amplitude_V"),
    BuilderUnitOption("mV", "mV", 1e-3, aurora_field="amplitude_V"),
    BuilderUnitOption("uV", "µV", 1e-6, aurora_field="amplitude_V"),
    BuilderUnitOption("mA", "mA", aurora_field="amplitude_mA"),
    BuilderUnitOption("uA", "µA", 1e-3, aurora_field="amplitude_mA"),
    BuilderUnitOption("A", "A", 1e3, aurora_field="amplitude_mA"),
)
CAPACITY_UNITS = (
    BuilderUnitOption("mAh", "mAh"),
    BuilderUnitOption("uAh", "µAh", 1e-3),
    BuilderUnitOption("Ah", "Ah", 1e3),
)
TEMPERATURE_UNITS = (
    BuilderUnitOption("degC", "°C"),
    BuilderUnitOption("degF", "°F", 5.0 / 9.0, -32.0 * 5.0 / 9.0),
    BuilderUnitOption("K", "K", 1.0, -273.15),
)
TEMPERATURE_RATE_UNITS = (
    BuilderUnitOption("degC/min", "°C/min"),
    BuilderUnitOption("degC/s", "°C/s", 60.0),
    BuilderUnitOption("degC/h", "°C/h", 1.0 / 60.0),
)
FREQUENCY_UNITS = (
    BuilderUnitOption("Hz", "Hz"),
    BuilderUnitOption("mHz", "mHz", 1e-3),
    BuilderUnitOption("kHz", "kHz", 1e3),
    BuilderUnitOption("MHz", "MHz", 1e6),
)
SCAN_RATE_UNITS = (
    BuilderUnitOption("mV/s", "mV/s"),
    BuilderUnitOption("uV/s", "µV/s", 1e-3),
    BuilderUnitOption("V/s", "V/s", 1e3),
    BuilderUnitOption("V/min", "V/min", 1e3 / 60.0),
)


RECORD_FIELDS: tuple[BuilderFieldSpec, ...] = (
    _unit_field("time_s", "Record interval time", "10", parse_required_float, TIME_UNITS),
    _unit_field("voltage_V", "Record voltage delta", "0.01", parse_optional_float, VOLTAGE_UNITS),
    _unit_field("current_mA", "Record current delta", "", parse_optional_float, CURRENT_UNITS),
)

SAFETY_FIELDS: tuple[BuilderFieldSpec, ...] = (
    _unit_field("max_voltage_V", "Max voltage", "4.3", parse_optional_float, VOLTAGE_UNITS),
    _unit_field("min_voltage_V", "Min voltage", "2.5", parse_optional_float, VOLTAGE_UNITS),
    _unit_field("max_current_mA", "Max current", "", parse_optional_float, CURRENT_UNITS),
    _unit_field("min_current_mA", "Min current", "", parse_optional_float, CURRENT_UNITS),
    _unit_field("max_capacity_mAh", "Max capacity", "", parse_optional_float, CAPACITY_UNITS),
    _unit_field("delay_s", "Safety delay", "", parse_optional_float, TIME_UNITS),
)


def _summary_from_parts(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _current_step_target_summary(params: dict[str, Any]) -> str:
    if params.get("rate_C"):
        return f"{params['rate_C']} C"
    if params.get("current_mA"):
        return _display_value(params, "current_mA", "mA")
    return ""


def _display_value(params: dict[str, Any], key: str, default_unit: str) -> str:
    value = params.get(key, "")
    if value in {None, ""}:
        return ""
    return f"{value} {params.get(f'{key}_unit') or default_unit}"


STEP_SPECS: dict[str, BuilderStepSpec] = {
    "tag": BuilderStepSpec(
        key="tag",
        label="Tag",
        fields=(BuilderFieldSpec("tag", "Tag name", "cycle", parse_required_text),),
        builder=lambda params: aurora_unicycler.Tag(tag=params["tag"]),
        summary_builder=lambda params: _summary_from_parts(params.get("tag", "")),
    ),
    "open_circuit_voltage": BuilderStepSpec(
        key="open_circuit_voltage",
        label="Open Circuit Voltage",
        fields=(_unit_field("until_time_s", "Duration", "600", parse_required_float, TIME_UNITS),),
        builder=lambda params: aurora_unicycler.OpenCircuitVoltage(**params),
        summary_builder=lambda params: _summary_from_parts(
            _display_value(params, "until_time_s", "s")
        ),
    ),
    "wait": BuilderStepSpec(
        key="wait",
        label="Wait",
        fields=(_unit_field("until_time_s", "Duration", "60", parse_required_float, TIME_UNITS),),
        builder=lambda params: aurora_unicycler.Wait(**params),
        summary_builder=lambda params: _summary_from_parts(
            _display_value(params, "until_time_s", "s")
        ),
    ),
    "temperature": BuilderStepSpec(
        key="temperature",
        label="Temperature",
        fields=(
            _unit_field(
                "until_temp_c",
                "Target temperature",
                "25",
                parse_required_float,
                TEMPERATURE_UNITS,
            ),
            _unit_field(
                "wait_after_s", "Wait after target", "60", parse_required_float, TIME_UNITS
            ),
            _unit_field(
                "ramp_rate", "Ramp rate", "0.35", parse_required_float, TEMPERATURE_RATE_UNITS
            ),
        ),
        builder=lambda params: Temperature(**params),
        summary_builder=lambda params: _summary_from_parts(
            _display_value(params, "until_temp_c", "degC"),
            _display_value(params, "ramp_rate", "degC/min"),
            f"wait {_display_value(params, 'wait_after_s', 's')}"
            if params.get("wait_after_s")
            else ""
        ),
    ),
    "constant_current": BuilderStepSpec(
        key="constant_current",
        label="Constant Current",
        fields=(
            BuilderFieldSpec("rate_C", "C-rate", "0.5", parse_optional_c_rate),
            _unit_field("current_mA", "Current", "", parse_optional_float, CURRENT_UNITS),
            _unit_field("until_time_s", "Max time", "10800", parse_optional_float, TIME_UNITS),
            _unit_field(
                "until_voltage_V",
                "Stop at voltage",
                "4.2",
                parse_optional_float,
                VOLTAGE_UNITS,
            ),
        ),
        builder=lambda params: aurora_unicycler.ConstantCurrent(**params),
        summary_builder=lambda params: _summary_from_parts(
            _current_step_target_summary(params),
            f"until {_display_value(params, 'until_voltage_V', 'V')}"
            if params.get("until_voltage_V")
            else "",
            f"max {_display_value(params, 'until_time_s', 's')}"
            if params.get("until_time_s")
            else "",
        ),
        field_choice=BuilderFieldChoice(
            key="current_mode",
            label="Current input",
            options=(
                BuilderFieldChoiceOption("rate", "C-rate", "rate_C"),
                BuilderFieldChoiceOption("current", "Current", "current_mA"),
            ),
        ),
    ),
    "constant_voltage": BuilderStepSpec(
        key="constant_voltage",
        label="Constant Voltage",
        fields=(
            _unit_field("voltage_V", "Voltage", "4.2", parse_required_float, VOLTAGE_UNITS),
            _unit_field("until_time_s", "Max time", "3600", parse_optional_float, TIME_UNITS),
            BuilderFieldSpec("until_rate_C", "Stop at rate (C)", "0.05", parse_optional_c_rate),
            _unit_field(
                "until_current_mA",
                "Stop at current",
                "",
                parse_optional_float,
                CURRENT_UNITS,
            ),
        ),
        builder=lambda params: aurora_unicycler.ConstantVoltage(**params),
        summary_builder=lambda params: _summary_from_parts(
            _display_value(params, "voltage_V", "V"),
            f"until {params.get('until_rate_C', '')} C" if params.get("until_rate_C") else "",
            f"until {_display_value(params, 'until_current_mA', 'mA')}"
            if params.get("until_current_mA")
            else "",
            f"max {_display_value(params, 'until_time_s', 's')}"
            if params.get("until_time_s")
            else "",
        ),
    ),
    "voltage_scan": BuilderStepSpec(
        key="voltage_scan",
        label="Voltage Scan",
        fields=(
            _unit_field(
                "start_voltage_V",
                "Start voltage",
                "3.0",
                parse_required_float,
                VOLTAGE_UNITS,
            ),
            _unit_field("end_voltage_V", "End voltage", "4.2", parse_required_float, VOLTAGE_UNITS),
            _unit_field(
                "scan_rate_mV_per_s",
                "Scan rate",
                "10",
                parse_required_float,
                SCAN_RATE_UNITS,
            ),
        ),
        builder=lambda params: aurora_unicycler.VoltageScan(**params),
        summary_builder=lambda params: _summary_from_parts(
            f"{_display_value(params, 'start_voltage_V', 'V')} -> "
            f"{_display_value(params, 'end_voltage_V', 'V')}",
            _display_value(params, "scan_rate_mV_per_s", "mV/s"),
        ),
    ),
    "impedance_spectroscopy": BuilderStepSpec(
        key="impedance_spectroscopy",
        label="Impedance Spectroscopy",
        fields=(
            _unit_field(
                "amplitude", "Amplitude", "0.01", parse_optional_float, EIS_AMPLITUDE_UNITS
            ),
            _unit_field(
                "start_frequency_Hz",
                "Start frequency",
                "10000",
                parse_required_float,
                FREQUENCY_UNITS,
            ),
            _unit_field(
                "end_frequency_Hz",
                "End frequency",
                "0.1",
                parse_required_float,
                FREQUENCY_UNITS,
            ),
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
            f"{_display_value(params, 'start_frequency_Hz', 'Hz')} -> "
            f"{_display_value(params, 'end_frequency_Hz', 'Hz')}",
            _display_value(params, "amplitude", "V"),
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


def visual_steps_from_protocol_data(protocol_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert canonical Aurora protocol steps into visual-builder step data."""
    method = protocol_data.get("method", [])
    if not isinstance(method, list):
        raise ValueError("Imported package method data must be a list.")

    visual_steps: list[dict[str, Any]] = []
    for raw_step in method:
        if not isinstance(raw_step, dict):
            raise ValueError("Every imported method step must be an object.")

        step = {key: value for key, value in raw_step.items() if key != "id"}
        step_type = step.get("step")
        if step_type == "loop":
            loop_target = step.pop("loop_to", None)
            if isinstance(loop_target, int) and not isinstance(loop_target, bool):
                step["loop_to_mode"] = "step"
                step["loop_to_step"] = loop_target
                step["loop_to_tag"] = ""
            elif isinstance(loop_target, str):
                step["loop_to_mode"] = "tag"
                step["loop_to_tag"] = loop_target
                step["loop_to_step"] = ""
            else:
                raise ValueError("An imported Loop step has an invalid target.")
        elif step_type == "impedance_spectroscopy":
            amplitude_v = step.pop("amplitude_V", None)
            amplitude_ma = step.pop("amplitude_mA", None)
            if amplitude_ma is not None:
                step["amplitude"] = amplitude_ma
                step["amplitude_unit"] = "mA"
            else:
                step["amplitude"] = amplitude_v
                step["amplitude_unit"] = "V"

        visual_steps.append(step)

    return visual_steps


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


def _parse_fields(
    field_specs: tuple[BuilderFieldSpec, ...], raw_values: dict[str, Any]
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for field in field_specs:
        parsed_key, parsed_value = field.parse_for_aurora(
            raw_values.get(field.key, field.default),
            raw_values.get(field.unit_key, field.default_unit),
        )
        parsed[parsed_key] = parsed_value
    return parsed


def _clean_none_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def build_protocol_from_visual_data(
    protocol_data: dict[str, Any],
) -> aurora_unicycler.CyclingProtocol:
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
            method_steps.append(aurora_unicycler.Loop(loop_to=loop_to, cycle_count=cycle_count))
            continue

        spec = STEP_SPECS.get(step_type)
        if spec is None:
            raise ValueError(f"Unsupported Aurora step type: {step_type}")
        if spec.field_choice is not None:
            raw_step = spec.field_choice.selected_values(raw_step)
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
    open_requested = Signal(object)

    def __init__(self, step_type: str, raw_values: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.step_type = step_type
        self.field_widgets: dict[str, FieldValueWidget] = {}
        self.unit_widgets: dict[str, QComboBox] = {}
        self.field_display_widgets: dict[str, QWidget] = {}
        self.field_labels: dict[QWidget, QLabel] = {}
        self.field_choice_widget: QComboBox | None = None
        self.field_choice_stack: QStackedWidget | None = None
        self.field_choice_label: QLabel | None = None
        self.field_position = 0
        self._expanded = True
        self.setObjectName("auroraStepCard")
        self.setProperty("stepType", step_type)
        self.setProperty("selected", False)
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
        if spec.field_choice is not None:
            self.field_choice_widget = QComboBox(self)
            for option in spec.field_choice.options:
                self.field_choice_widget.addItem(option.label, option.key)
            selected = spec.field_choice.selected_key(raw_values)
            self.field_choice_widget.setCurrentIndex(self.field_choice_widget.findData(selected))
            self._add_compact_field(spec.field_choice.label, self.field_choice_widget)

        editors: list[tuple[BuilderFieldSpec, QWidget]] = []
        for field in spec.fields:
            value_widget, display_widget, unit_widget = _create_field_editor(
                field, raw_values, self, self._on_field_changed
            )
            self.field_widgets[field.key] = value_widget
            self.field_display_widgets[field.key] = display_widget
            if unit_widget is not None:
                self.unit_widgets[field.key] = unit_widget
            editors.append((field, display_widget))

        choice_fields: set[str] = set()
        if spec.field_choice is not None and self.field_choice_widget is not None:
            choice_fields = {option.field_key for option in spec.field_choice.options}
            self.field_choice_stack = QStackedWidget(self)
            for option in spec.field_choice.options:
                self.field_choice_stack.addWidget(self.field_display_widgets[option.field_key])
            self.field_choice_label = self._add_compact_field("", self.field_choice_stack)
            self.field_choice_widget.currentIndexChanged.connect(self._on_field_choice_changed)
            self._update_field_choice_visibility()

        for field, display_widget in editors:
            if field.key not in choice_fields:
                self._add_compact_field(field.label, display_widget)

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

        self.loop_target_step = QLineEdit(_as_text(raw_values.get("loop_to_step", "")), self)
        self.loop_target_step.textChanged.connect(self._on_field_changed)

        self.loop_target_stack = QStackedWidget(self)
        self.loop_target_stack.addWidget(self.loop_target_tag)
        self.loop_target_stack.addWidget(self.loop_target_step)
        self.loop_target_value_label = self._add_compact_field("Tag target", self.loop_target_stack)

        self.loop_cycle_count = QLineEdit(_as_text(raw_values.get("cycle_count", "10")), self)
        self.loop_cycle_count.textChanged.connect(self._on_field_changed)
        self._add_compact_field("Cycle count", self.loop_cycle_count)

        self._on_loop_mode_changed()

    def _add_compact_field(self, label_text: str, widget: QWidget) -> QLabel:
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
        return label

    def _on_loop_mode_changed(self):
        use_tag = self.loop_target_mode.currentData() == "tag"
        self.loop_target_stack.setCurrentWidget(
            self.loop_target_tag if use_tag else self.loop_target_step
        )
        self.loop_target_value_label.setText("Tag target" if use_tag else "Step target")

    def _on_field_changed(self, *_args):
        self.changed.emit()

    def _on_field_choice_changed(self, *_args):
        self._update_field_choice_visibility()
        self.changed.emit()

    def _update_field_choice_visibility(self):
        spec = STEP_SPECS[self.step_type]
        if (
            spec.field_choice is None
            or self.field_choice_widget is None
            or self.field_choice_stack is None
            or self.field_choice_label is None
        ):
            return

        active_field = spec.field_choice.active_field_key(self.field_choice_widget.currentData())
        self.field_choice_stack.setCurrentWidget(self.field_display_widgets[active_field])
        active_spec = next(field for field in spec.fields if field.key == active_field)
        self.field_choice_label.setText(active_spec.label)

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
        spec = STEP_SPECS[self.step_type]
        for field in spec.fields:
            widget = self.field_widgets[field.key]
            values[field.key] = _read_field_widget(field, widget)
            if field.unit_options:
                values[field.unit_key] = self.unit_widgets[field.key].currentData()
        if spec.field_choice is not None and self.field_choice_widget is not None:
            values = spec.field_choice.selected_values(
                values, self.field_choice_widget.currentData()
            )
        return values

    def update_header(self, index: int):
        label = "Loop" if self.step_type == "loop" else STEP_SPECS[self.step_type].label
        self.index_label.setText(f"{index + 1}")
        self.title_label.setText(label)
        self.summary_label.setText(self.summary_text())

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        selection_changed = self.property("selected") != expanded
        self.setProperty("selected", expanded)
        self.form_widget.setVisible(expanded)
        if selection_changed:
            for widget in (self, self.index_label):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.is_expanded:
            self.open_requested.emit(self)
        super().mousePressEvent(event)

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
    import_package_requested = Signal()

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

        self.import_package_button = QPushButton("Import Package", self.sequence_frame)
        self.import_package_button.setObjectName("auroraAddStepButton")
        self.import_package_button.clicked.connect(
            lambda: self.import_package_requested.emit()
        )
        sequence_header.addWidget(self.import_package_button)

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
            value_widget, display_widget, unit_widget = _create_field_editor(
                field,
                {},
                frame,
                lambda *_args: self.changed.emit(),
            )
            if unit_widget is not None:
                setattr(self, f"{field.unit_key}_widget", unit_widget)
            form.addRow(field.label, display_widget)
            setattr(self, f"{field.key}_widget", value_widget)

        return frame

    def raw_data(self) -> dict[str, Any]:
        record = self._raw_section(RECORD_FIELDS)
        safety = self._raw_section(SAFETY_FIELDS)
        method = [card.raw_values() for card in self.step_cards]
        return {"record": record, "safety": safety, "method": method}

    def build_protocol(self) -> aurora_unicycler.CyclingProtocol:
        return build_protocol_from_visual_data(self.raw_data())

    def add_selected_step(self):
        self.add_step(
            self.step_type_combo.currentData(),
            index=self._insertion_index_after_selected(),
        )

    def add_step(
        self, step_type: str, raw_values: dict[str, Any] | None = None, index: int | None = None
    ):
        card = AuroraStepCard(step_type, raw_values=raw_values, parent=self.steps_container)
        card.changed.connect(self._refresh_cards)
        card.move_up_requested.connect(lambda current: self.move_step(current, -1))
        card.move_down_requested.connect(lambda current: self.move_step(current, 1))
        card.remove_requested.connect(self.remove_step)
        card.open_requested.connect(self.set_expanded_card)

        insert_index = (
            len(self.step_cards) if index is None else max(0, min(index, len(self.step_cards)))
        )
        self.step_cards.insert(insert_index, card)
        self.steps_layout.insertWidget(insert_index, card)
        self.set_expanded_card(card)
        self._refresh_cards()

    def insert_steps_after_selected(self, raw_steps: list[dict[str, Any]]) -> None:
        if not raw_steps:
            raise ValueError("The imported package does not contain any method steps.")

        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise ValueError("Every imported method step must be an object.")
            if raw_step.get("step") not in STEP_ORDER:
                raise ValueError(f"Unsupported imported step type: {raw_step.get('step')}")

        insert_index = self._insertion_index_after_selected()
        for offset, raw_step in enumerate(raw_steps):
            imported_step = dict(raw_step)
            if (
                imported_step["step"] == "loop"
                and imported_step.get("loop_to_mode") == "step"
            ):
                target = parse_required_int(imported_step.get("loop_to_step"))
                imported_step["loop_to_step"] = target + insert_index
            self.add_step(
                imported_step["step"],
                raw_values=imported_step,
                index=insert_index + offset,
            )

    def _insertion_index_after_selected(self) -> int:
        for index, card in enumerate(self.step_cards):
            if card.is_expanded:
                return index + 1
        return len(self.step_cards)

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
            values[field.key] = _read_field_widget(field, widget)
            if field.unit_options:
                unit_widget = getattr(self, f"{field.unit_key}_widget")
                values[field.unit_key] = unit_widget.currentData()
        return values

    def _set_section(self, field_specs: tuple[BuilderFieldSpec, ...], raw_values: dict[str, Any]):
        for field in field_specs:
            widget = getattr(self, f"{field.key}_widget")
            raw_value = raw_values.get(field.key, field.default)
            _set_field_widget(field, widget, raw_value)
            if field.unit_options:
                unit_widget = getattr(self, f"{field.unit_key}_widget")
                _set_unit_widget(field, unit_widget, raw_values)
