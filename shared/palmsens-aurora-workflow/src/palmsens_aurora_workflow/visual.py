"""Visual-builder protocol metadata, parsing, and Aurora compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import aurora_unicycler
from aurora_unicycler._core import Temperature


Parser = Callable[[Any], Any]
SummaryBuilder = Callable[[dict[str, Any]], str]


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_required_float(raw_value: Any) -> float:
    value = as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return float(value)


def parse_optional_float(raw_value: Any) -> float | None:
    value = as_text(raw_value)
    if not value:
        return None
    return float(value)


def parse_required_int(raw_value: Any) -> int:
    value = as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return int(value)


def parse_required_text(raw_value: Any) -> str:
    value = as_text(raw_value)
    if not value:
        raise ValueError("A value is required.")
    return value


def parse_optional_c_rate(raw_value: Any) -> str | None:
    value = as_text(raw_value)
    return value or None


def parse_bool(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    value = as_text(raw_value).casefold()
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


def summary_from_parts(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _current_step_target_summary(params: dict[str, Any]) -> str:
    if params.get("rate_C"):
        return f"{params['rate_C']} C"
    if params.get("current_mA"):
        return f"{params['current_mA']} mA"
    return ""


STEP_SPECS: dict[str, BuilderStepSpec] = {
    "tag": BuilderStepSpec(
        "tag",
        "Tag",
        (BuilderFieldSpec("tag", "Tag name", "cycle", parse_required_text),),
        lambda params: aurora_unicycler.Tag(tag=params["tag"]),
        lambda params: summary_from_parts(params.get("tag", "")),
    ),
    "open_circuit_voltage": BuilderStepSpec(
        "open_circuit_voltage",
        "Open Circuit Voltage",
        (BuilderFieldSpec("until_time_s", "Duration (s)", "600", parse_required_float),),
        lambda params: aurora_unicycler.OpenCircuitVoltage(**params),
        lambda params: summary_from_parts(f"{params.get('until_time_s', '')} s"),
    ),
    "wait": BuilderStepSpec(
        "wait",
        "Wait",
        (BuilderFieldSpec("until_time_s", "Duration (s)", "60", parse_required_float),),
        lambda params: aurora_unicycler.Wait(**params),
        lambda params: summary_from_parts(f"{params.get('until_time_s', '')} s"),
    ),
    "temperature": BuilderStepSpec(
        "temperature",
        "Temperature",
        (
            BuilderFieldSpec("until_temp_c", "Target temperature (degC)", "25", parse_required_float),
            BuilderFieldSpec("wait_after_s", "Wait after target (s)", "60", parse_required_float),
            BuilderFieldSpec("ramp_rate", "Ramp rate (degC/min)", "0.35", parse_required_float),
        ),
        lambda params: Temperature(**params),
        lambda params: summary_from_parts(
            f"{params.get('until_temp_c', '')} degC",
            f"{params.get('ramp_rate', '')} degC/min" if params.get("ramp_rate") else "",
            f"wait {params.get('wait_after_s', '')} s" if params.get("wait_after_s") else "",
            "INTE IMPLEMENTERAD",
        ),
    ),
    "constant_current": BuilderStepSpec(
        "constant_current",
        "Constant Current",
        (
            BuilderFieldSpec("rate_C", "Rate (C)", "0.5", parse_optional_c_rate),
            BuilderFieldSpec("current_mA", "Current (mA)", "", parse_optional_float),
            BuilderFieldSpec("until_time_s", "Max time (s)", "10800", parse_optional_float),
            BuilderFieldSpec("until_voltage_V", "Stop at voltage (V)", "4.2", parse_optional_float),
        ),
        lambda params: aurora_unicycler.ConstantCurrent(**params),
        lambda params: summary_from_parts(
            _current_step_target_summary(params),
            f"until {params.get('until_voltage_V', '')} V" if params.get("until_voltage_V") else "",
            f"max {params.get('until_time_s', '')} s" if params.get("until_time_s") else "",
        ),
    ),
    "constant_voltage": BuilderStepSpec(
        "constant_voltage",
        "Constant Voltage",
        (
            BuilderFieldSpec("voltage_V", "Voltage (V)", "4.2", parse_required_float),
            BuilderFieldSpec("until_time_s", "Max time (s)", "3600", parse_optional_float),
            BuilderFieldSpec("until_rate_C", "Stop at rate (C)", "0.05", parse_optional_c_rate),
            BuilderFieldSpec("until_current_mA", "Stop at current (mA)", "", parse_optional_float),
        ),
        lambda params: aurora_unicycler.ConstantVoltage(**params),
        lambda params: summary_from_parts(
            f"{params.get('voltage_V', '')} V",
            f"until {params.get('until_rate_C', '')} C" if params.get("until_rate_C") else "",
            f"until {params.get('until_current_mA', '')} mA" if params.get("until_current_mA") else "",
            f"max {params.get('until_time_s', '')} s" if params.get("until_time_s") else "",
        ),
    ),
    "voltage_scan": BuilderStepSpec(
        "voltage_scan",
        "Voltage Scan",
        (
            BuilderFieldSpec("start_voltage_V", "Start voltage (V)", "3.0", parse_required_float),
            BuilderFieldSpec("end_voltage_V", "End voltage (V)", "4.2", parse_required_float),
            BuilderFieldSpec("scan_rate_mV_per_s", "Scan rate (mV/s)", "10", parse_required_float),
        ),
        lambda params: aurora_unicycler.VoltageScan(**params),
        lambda params: summary_from_parts(
            f"{params.get('start_voltage_V', '')} -> {params.get('end_voltage_V', '')} V",
            f"{params.get('scan_rate_mV_per_s', '')} mV/s",
        ),
    ),
    "impedance_spectroscopy": BuilderStepSpec(
        "impedance_spectroscopy",
        "Impedance Spectroscopy",
        (
            BuilderFieldSpec("amplitude_V", "Amplitude (V)", "0.01", parse_optional_float),
            BuilderFieldSpec("amplitude_mA", "Amplitude (mA)", "", parse_optional_float),
            BuilderFieldSpec("start_frequency_Hz", "Start frequency (Hz)", "10000", parse_required_float),
            BuilderFieldSpec("end_frequency_Hz", "End frequency (Hz)", "0.1", parse_required_float),
            BuilderFieldSpec("points_per_decade", "Points per decade", "10", parse_required_int),
            BuilderFieldSpec("measures_per_point", "Measures per point", "1", parse_required_int),
            BuilderFieldSpec("drift_correction", "Drift correction", False, parse_bool, "bool"),
        ),
        lambda params: aurora_unicycler.ImpedanceSpectroscopy(**params),
        lambda params: summary_from_parts(
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


def _parse_fields(
    field_specs: tuple[BuilderFieldSpec, ...], raw_values: dict[str, Any]
) -> dict[str, Any]:
    return {
        field.key: field.parse(raw_values.get(field.key, field.default))
        for field in field_specs
    }


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
                    f"Invalid value for Loop cycle count at step {index}: "
                    f"{raw_step.get('cycle_count', '')}"
                ) from exc
            loop_mode = as_text(raw_step.get("loop_to_mode", "tag")) or "tag"
            if loop_mode == "step":
                try:
                    loop_to = parse_required_int(raw_step.get("loop_to_step", ""))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid value for Loop step target at step {index}: "
                        f"{raw_step.get('loop_to_step', '')}"
                    ) from exc
            else:
                loop_to = as_text(raw_step.get("loop_to_tag", ""))
                if not loop_to:
                    raise ValueError(f"Loop target tag is required for step {index}.")
            method_steps.append(aurora_unicycler.Loop(loop_to=loop_to, cycle_count=cycle_count))
            continue

        spec = STEP_SPECS.get(step_type)
        if spec is None:
            raise ValueError(f"Unsupported Aurora step type: {step_type}")
        params = _clean_none_values(_parse_fields(spec.fields, raw_step))
        method_steps.append(spec.builder(params))

    if not method_steps:
        raise ValueError("Add at least one Aurora step to the sequence.")

    return aurora_unicycler.CyclingProtocol(record=record, safety=safety, method=method_steps)
