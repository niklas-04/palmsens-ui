from dataclasses import dataclass
from typing import Any, Callable

import pypalmsens as ps


Parser = Callable[[str], Any]
Builder = Callable[[dict[str, Any]], object]


@dataclass()
class FieldSpec:
    key: str
    label: str
    default: str
    parser: Parser

    def parse(self, raw_value: str) -> Any:
        value = raw_value.strip()
        if not value:
            raise ValueError(f"{self.label} is required.")

        try:
            return self.parser(value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {self.label}: {raw_value}") from exc


@dataclass()
class MethodSpec:
    key: str
    label: str
    fields: tuple[FieldSpec, ...]
    builder: Builder

    def default_params(self) -> dict[str, str]:
        return {field.key: field.default for field in self.fields}

    def build_method(self, raw_params: dict[str, str]) -> object:
        parsed_params = {
            field.key: field.parse(raw_params.get(field.key, ""))
            for field in self.fields
        }
        return self.builder(parsed_params)


METHOD_SPECS: dict[str, MethodSpec] = {
    "ca": MethodSpec(
        key="ca",
        label="Chrono Amperometry",
        fields=(
            FieldSpec("equilibration_time", "Equilibration time (s)", "0.0", float),
            FieldSpec("interval_time", "Interval time (s)", "0.1", float),
            FieldSpec("potential", "Potential (V)", "0.0", float),
            FieldSpec("run_time", "Run time (s)", "10.0", float),
        ),
        builder=lambda params: ps.ChronoAmperometry(
            equilibration_time=params["equilibration_time"],
            interval_time=params["interval_time"],
            potential=params["potential"],
            run_time=params["run_time"],
        ),
    ),
    "cv": MethodSpec(
        key="cv",
        label="Cyclic Voltammetry",
        fields=(
            FieldSpec("equilibration_time", "Equilibration time (s)", "0.0", float),
            FieldSpec("begin_potential", "Begin potential (V)", "-0.5", float),
            FieldSpec("vertex1_potential", "Vertex 1 potential (V)", "0.5", float),
            FieldSpec("vertex2_potential", "Vertex 2 potential (V)", "-0.5", float),
            FieldSpec("step_potential", "Step potential (V)", "0.01", float),
            FieldSpec("scanrate", "Scan rate (V/s)", "0.1", float),
            FieldSpec("n_scans", "Number of scans", "1", int),
        ),
        builder=lambda params: ps.CyclicVoltammetry(
            equilibration_time=params["equilibration_time"],
            begin_potential=params["begin_potential"],
            vertex1_potential=params["vertex1_potential"],
            vertex2_potential=params["vertex2_potential"],
            step_potential=params["step_potential"],
            scanrate=params["scanrate"],
            n_scans=params["n_scans"],
        ),
    ),
}

METHOD_ORDER = tuple(METHOD_SPECS.keys())


def default_params(method_key: str) -> dict[str, str]:
    return METHOD_SPECS[method_key].default_params()


def build_method(method_key: str, raw_params: dict[str, str]) -> object:
    return METHOD_SPECS[method_key].build_method(raw_params)

