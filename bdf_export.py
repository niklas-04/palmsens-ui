import re
from pathlib import Path

import bdf
import pandas as pd


_GROUPED_KEY_PATTERN = re.compile(r"^(?P<base>.+?)_(?P<group>\d+)$") # Matchar: mätningar + grippering

_TIME_ALIASES = (
    "time",
    "testtime",
    "elapsedtime",
)
_VOLTAGE_ALIASES = (
    "voltage",
    "potential",
)
_CURRENT_ALIASES = (
    "current",
)

_TIME_FACTORS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "ms": 1e-3,
    "millisecond": 1e-3,
    "milliseconds": 1e-3,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
}

_VOLTAGE_FACTORS = {
    "v": 1.0,
    "mv": 1e-3,
}

_CURRENT_FACTORS = {
    "a": 1.0,
    "ma": 1e-3,
    "ua": 1e-6,
    "na": 1e-9,
}


class BdfExportError(ValueError):
    pass


def export_measurement_to_bdf_files(
    measurement,
    output_dir: Path,
    filename_stem: str,
    export_type: str,
    export_separate: bool = False,
) -> list[Path]:
    dataset = getattr(measurement, "dataset", None)
    if not dataset:
        raise BdfExportError("Measurement does not contain any dataset arrays.")

    groups = _measurement_groups(dataset)
    if not groups:
        raise BdfExportError("Measurement does not contain any exportable dataset groups.")

    written_paths = []
    multiple_groups = len(groups) > 1
    dataframes = []

    for group in groups:
        series = _extract_required_series(group)
        dataframe = _build_dataframe(series)
        dataframes.append(dataframe)
        res = bdf.validate(dataframe, raise_on_error=True)
        if not res["ok"]:
            pass
        stem = filename_stem
        if multiple_groups:
            stem = f"{filename_stem}_group_{group['id']}"
        if export_separate:
            output_path = _unique_output_path(output_dir, stem, export_type)
            _write_dataframe(output_path, dataframe, export_type)
            written_paths.append(output_path)

    combined_dataframes = pd.concat(dataframes, ignore_index=True)
    total_path = _unique_output_path(output_dir, f"{filename_stem}_total", export_type)
    _write_dataframe(total_path, combined_dataframes, export_type)
    written_paths.append(total_path)
    return written_paths


def _measurement_groups(dataset):
    # TODO: Flytta ut delad logik till en utils?
    groups = {}

    for key, data_array in dataset.items():
        match = _GROUPED_KEY_PATTERN.match(key)
        if match:
            base_key = match.group("base")
            group_id = match.group("group")
        else:
            base_key = key
            group_id = "default"

        group = groups.setdefault(
            group_id,
            {
                "id": group_id,
                "arrays": [],
            },
        )
        group["arrays"].append(
            {
                "key": key,
                "base_key": base_key,
                "array": data_array,
            }
        )

    return sorted(
        groups.values(),
        key=lambda group: (
            group["id"] == "default",
            int(group["id"]) if str(group["id"]).isdigit() else float("inf"),
            str(group["id"]),
        ),
    )


def _extract_required_series(group) -> dict[str, list[float]]:
    series = {}

    for entry in group["arrays"]:
        data_array = entry["array"]
        base_key = entry["base_key"]
        array_name = getattr(data_array, "name", base_key)
        array_type = getattr(data_array, "type", "")
        unit = getattr(data_array, "unit", "")
        values = data_array.to_numpy()

        column_key = _detect_required_column(base_key, array_name, array_type, unit)
        if column_key is None or column_key in series:
            continue

        factor = _conversion_factor(column_key, unit)
        series[column_key] = [_to_float(value) * factor for value in values]

    missing_columns = [
        column_key
        for column_key in ("test_time_second", "voltage_volt", "current_ampere")
        if column_key not in series
    ]
    if missing_columns:
        raise BdfExportError(
            "Missing required BDF quantities. The measurement must include time, voltage, and current arrays."
        )

    length = len(series["test_time_second"])
    if len(series["voltage_volt"]) != length or len(series["current_ampere"]) != length:
        raise BdfExportError("Required BDF arrays do not have matching lengths.")

    return series


def _detect_required_column(base_key: str, array_name: str, array_type: str, unit: str) -> str | None:
    texts = (
        _normalize_text(base_key),
        _normalize_text(array_name),
        _normalize_text(array_type),
    )
    unit_key = _normalize_unit(unit)

    if any(alias in text for text in texts for alias in _TIME_ALIASES):
        return "test_time_second"
    if any(alias in text for text in texts for alias in _VOLTAGE_ALIASES):
        return "voltage_volt"
    if any(alias in text for text in texts for alias in _CURRENT_ALIASES):
        return "current_ampere"

    if unit_key in _TIME_FACTORS:
        return "test_time_second"
    if unit_key in _VOLTAGE_FACTORS:
        return "voltage_volt"
    if unit_key in _CURRENT_FACTORS:
        return "current_ampere"

    return None


def _conversion_factor(column_key: str, unit: str) -> float:
    unit_key = _normalize_unit(unit)

    if column_key == "test_time_second":
        factor = _TIME_FACTORS.get(unit_key)
        if factor is None:
            raise BdfExportError(f"Unsupported time unit for BDF export: {unit!r}")
        return factor

    if column_key == "voltage_volt":
        factor = _VOLTAGE_FACTORS.get(unit_key)
        if factor is None:
            raise BdfExportError(f"Unsupported voltage unit for BDF export: {unit!r}")
        return factor

    if column_key == "current_ampere":
        factor = _CURRENT_FACTORS.get(unit_key)
        if factor is None:
            raise BdfExportError(f"Unsupported current unit for BDF export: {unit!r}")
        return factor

    raise BdfExportError(f"Unsupported BDF column: {column_key}")


def _build_dataframe(series: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Test Time / s": series["test_time_second"],
            "Voltage / V": series["voltage_volt"],
            "Current / A": series["current_ampere"],
        }
    )


def _write_csv(path: Path, dataframe: pd.DataFrame):
    dataframe.to_csv(path, index=False, float_format="%.15g")

def _write_parquet(path: Path, dataframe: pd.DataFrame):
    dataframe.to_parquet(path, index=False)

def _write_dataframe(path: Path, dataframe: pd.DataFrame, export_type: str):
    if export_type == "csv":
        _write_csv(path, dataframe)
    elif export_type == "parquet":
        _write_parquet(path, dataframe)
    else:
        raise BdfExportError(f"Unsupported BDF export type: {export_type}")

def _unique_output_path(output_dir: Path, stem: str, export_type: str) -> Path:
    candidate = output_dir / f"{stem}.bdf.{export_type}"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{stem}_{suffix}.bdf.{export_type}"
        suffix += 1
    return candidate


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _normalize_unit(unit) -> str:
    if unit is None:
        return ""

    normalized = str(unit).strip().casefold()
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("μ", "u")
    normalized = normalized.replace("µ", "u")
    normalized = normalized.replace("°", "deg")
    normalized = normalized.replace("deg.c", "degc")
    normalized = normalized.replace("degcelsius", "degc")
    return normalized


def _to_float(value) -> float:
    if hasattr(value, "item"):
        value = value.item()
    return float(value)

