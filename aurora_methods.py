from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aurora_unicycler
from aurora_unicycler._core import Loop, Tag, Temperature
from aurora_unicycler.palmsens import PalmSensDevice


PACKAGE_FORMAT = "palmsens_aurora_method_package"
PACKAGE_VERSION = 2


AURORA_DEVICE_OPTIONS = (
    ("EmStat4 HR", "emstat4_hr"),
    ("EmStat4 LR", "emstat4_lr"),
    ("Nexus", "nexus"),
)

AURORA_ADDITIONAL_MEASUREMENT_OPTIONS = (
    ("ab", "ab Potential"),
    ("ac", "ac CE potential"),
    ("ae", "ae RE potential"),
    ("ag", "ag WE vs CE"),
    ("as", "as Analog input 0"),
    ("ah", "ah S2 vs RE"),
    ("ai", "ai SE vs S2"),
    ("ba", "ba Current"),
    ("bb", "bb Bipot current"),
    ("ed", "ed Temperature"),
    ("ef", "ef Board temperature"),
)

AURORA_DEVICE_MEASUREMENT_TYPES = {
    "emstat4_hr": {"ab", "ac", "ae", "ag", "as", "ba"},
    "emstat4_lr": {"ab", "ac", "ae", "ag", "as", "ba"},
    "nexus": {"ab", "ac", "ag", "as", "ah", "ai", "ba", "bb", "ed", "ef"},
}


@dataclass(frozen=True)
class AuroraExportSettings:
    sample_name: str | None
    capacity_mAh: float | None
    device_key: str
    channel: int
    scan_step_voltage_v: float | None
    eis_dc_potential_v: float
    eis_dc_current_ma: float
    additional_measurements: tuple[str, ...]


@dataclass(frozen=True)
class AuroraMethodPackage:
    name: str
    source_mode: str
    source_payload: dict[str, Any] | str
    protocol_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": PACKAGE_FORMAT,
            "version": PACKAGE_VERSION,
            "name": self.name,
            "source_mode": self.source_mode,
            "source_payload": self.source_payload,
            "protocol_json": self.protocol_json,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuroraMethodPackage":
        if data.get("format") != PACKAGE_FORMAT:
            raise ValueError("Unsupported Aurora package format.")
        if data.get("version") != PACKAGE_VERSION:
            raise ValueError("Unsupported Aurora package version.")
        return cls(
            name=data.get("name", "Aurora Method"),
            source_mode=data.get("source_mode", "aurora_visual"),
            source_payload=data.get("source_payload", {}),
            protocol_json=data.get("protocol_json", {}),
        )


@dataclass(frozen=True)
class AuroraStepAction:
    execution_index: int
    source_step_index: int
    step_type: str
    label: str
    methodscript: str | None = None
    target_temperature_c: float | None = None
    ramp_rate_c_per_min: float | None = None
    wait_after_s: float | None = None

    @property
    def is_palmsens(self) -> bool:
        return self.methodscript is not None

    @property
    def is_temperature(self) -> bool:
        return self.target_temperature_c is not None


@dataclass(frozen=True)
class AuroraStepwiseMethod:
    name: str
    protocol_json: dict[str, Any]
    settings: AuroraExportSettings
    max_executed_steps: int = 10_000

    def render_actions(self) -> tuple[AuroraStepAction, ...]:
        protocol = aurora_unicycler.CyclingProtocol.from_dict(self.protocol_json)
        return render_aurora_step_actions(
            protocol,
            self.settings,
            max_executed_steps=self.max_executed_steps,
        )


def build_aurora_protocol(source_mode: str, source_payload: dict[str, Any] | str):
    if source_mode == "aurora_visual":
        from aurora_builder import build_protocol_from_visual_data

        if not isinstance(source_payload, dict):
            raise ValueError("Aurora visual payload must be a dictionary.")
        return build_protocol_from_visual_data(source_payload)

    if not isinstance(source_payload, str) or not source_payload.strip():
        raise ValueError("Aurora source text is required.")

    if source_mode == "aurora_json":
        try:
            protocol_data = json.loads(source_payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Aurora JSON: {exc.msg}") from exc
        return aurora_unicycler.CyclingProtocol.from_dict(protocol_data)

    if source_mode == "aurora_python":
        execution_scope = {
            "__builtins__": __builtins__,
            "CyclingProtocol": aurora_unicycler.CyclingProtocol,
            "ConstantCurrent": aurora_unicycler.ConstantCurrent,
            "ConstantVoltage": aurora_unicycler.ConstantVoltage,
            "ImpedanceSpectroscopy": aurora_unicycler.ImpedanceSpectroscopy,
            "Loop": aurora_unicycler.Loop,
            "OpenCircuitVoltage": aurora_unicycler.OpenCircuitVoltage,
            "PalmSensDevice": PalmSensDevice,
            "RecordParams": aurora_unicycler.RecordParams,
            "SafetyParams": aurora_unicycler.SafetyParams,
            "SampleParams": aurora_unicycler.SampleParams,
            "Tag": aurora_unicycler.Tag,
            "Temperature": Temperature,
            "VoltageScan": aurora_unicycler.VoltageScan,
            "Wait": aurora_unicycler.Wait,
        }
        exec(source_payload, execution_scope, execution_scope)
        protocol = execution_scope.get("protocol")
        if protocol is None:
            build_protocol_fn = execution_scope.get("build_protocol")
            if callable(build_protocol_fn):
                protocol = build_protocol_fn()
        if protocol is None:
            raise ValueError(
                "Aurora Python scripts must define `protocol = CyclingProtocol(...)` "
                "or `build_protocol()`."
            )
        if not isinstance(protocol, aurora_unicycler.CyclingProtocol):
            raise ValueError("Aurora Python script did not produce a CyclingProtocol.")
        return protocol

    raise ValueError(f"Unsupported Aurora source mode: {source_mode}")


def build_aurora_methodscript(
    protocol: aurora_unicycler.CyclingProtocol,
    settings: AuroraExportSettings,
) -> str:
    return protocol.to_palmsens_methodscript(
        sample_name=settings.sample_name,
        capacity_mAh=settings.capacity_mAh,
        device=PalmSensDevice(settings.device_key),
        channel=0, # Konstig fix: Palmsensen hanterar kanalerna som egna enheter med en kanal
        scan_step_voltage_V=settings.scan_step_voltage_v,
        eis_dc_potential_V=settings.eis_dc_potential_v,
        eis_dc_current_mA=settings.eis_dc_current_ma,
        additional_measurements=settings.additional_measurements,
    )


def build_aurora_package(
    *,
    name: str,
    source_mode: str,
    source_payload: dict[str, Any] | str,
) -> AuroraMethodPackage:
    protocol = build_aurora_protocol(source_mode, source_payload)
    return AuroraMethodPackage(
        name=name,
        source_mode=source_mode,
        source_payload=source_payload,
        protocol_json=protocol.to_dict(),
    )


def render_aurora_package(
    package: AuroraMethodPackage,
    settings: AuroraExportSettings,
) -> str:
    protocol = aurora_unicycler.CyclingProtocol.from_dict(package.protocol_json)
    return build_aurora_methodscript(protocol, settings)


def build_aurora_stepwise_method(
    package: AuroraMethodPackage,
    settings: AuroraExportSettings,
) -> AuroraStepwiseMethod:
    return AuroraStepwiseMethod(
        name=package.name,
        protocol_json=package.protocol_json,
        settings=settings,
    )


def render_aurora_step_actions(
    protocol: aurora_unicycler.CyclingProtocol,
    settings: AuroraExportSettings,
    *,
    max_executed_steps: int = 10_000,
) -> tuple[AuroraStepAction, ...]:
    actions = []
    for execution_index, source_step_index, step in _expanded_protocol_steps(protocol, max_executed_steps):
        step_type = str(getattr(step, "step", step.__class__.__name__))
        label = f"Step {source_step_index}: {step_type}"

        if isinstance(step, Temperature):
            actions.append(
                AuroraStepAction(
                    execution_index=execution_index,
                    source_step_index=source_step_index,
                    step_type=step_type,
                    label=label,
                    target_temperature_c=step.until_temp_c,
                    ramp_rate_c_per_min=step.ramp_rate,
                    wait_after_s=step.wait_after_s,
                )
            )
            continue

        single_step_protocol = _single_step_protocol(protocol, step)
        actions.append(
            AuroraStepAction(
                execution_index=execution_index,
                source_step_index=source_step_index,
                step_type=step_type,
                label=label,
                methodscript=build_aurora_methodscript(single_step_protocol, settings),
            )
        )

    return tuple(actions)


def _expanded_protocol_steps(
    protocol: aurora_unicycler.CyclingProtocol,
    max_executed_steps: int,
):
    method_steps = list(protocol.method)
    tag_indexes = {
        step.tag: index
        for index, step in enumerate(method_steps)
        if isinstance(step, Tag)
    }
    loop_counts: dict[int, int] = {}
    executed_steps = 0
    index = 0

    while index < len(method_steps):
        step = method_steps[index]

        if isinstance(step, Tag):
            index += 1
            continue

        if isinstance(step, Loop):
            current_cycle = loop_counts.get(index, 1)
            if current_cycle < step.cycle_count:
                loop_counts[index] = current_cycle + 1
                index = _loop_target_index(step, tag_indexes, len(method_steps))
            else:
                loop_counts.pop(index, None)
                index += 1
            continue

        executed_steps += 1
        if executed_steps > max_executed_steps:
            raise ValueError(
                f"Aurora step-wise execution exceeded {max_executed_steps} expanded steps. "
                "Check the protocol loops."
            )
        yield executed_steps, index + 1, step
        index += 1


def _loop_target_index(loop_step: Loop, tag_indexes: dict[str, int], method_length: int) -> int:
    loop_to = loop_step.loop_to
    if isinstance(loop_to, int):
        target_index = loop_to - 1
    else:
        if loop_to not in tag_indexes:
            raise ValueError(f"Loop target tag is missing: {loop_to}")
        target_index = tag_indexes[loop_to] + 1

    if target_index < 0 or target_index >= method_length:
        raise ValueError(f"Loop target is outside the method: {loop_to}")
    return target_index


def _single_step_protocol(protocol: aurora_unicycler.CyclingProtocol, step) -> aurora_unicycler.CyclingProtocol:
    protocol_data = protocol.to_dict()
    if hasattr(step, "model_dump"):
        step_data = step.model_dump()
    else:
        step_data = step
    protocol_data["method"] = [step_data]
    return aurora_unicycler.CyclingProtocol.from_dict(protocol_data)


def save_aurora_package(path: Path | str, package: AuroraMethodPackage) -> None:
    target = Path(path)
    target.write_text(json.dumps(package.to_dict(), indent=2), encoding="utf-8")


def load_aurora_package(path: Path | str) -> AuroraMethodPackage:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    return AuroraMethodPackage.from_dict(data)
