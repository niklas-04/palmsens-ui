from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatasetView:
    id: str
    title: str
    dataset: Any
    source: Any
    is_eis: bool = False


def measurement_dataset_views(measurement, include_subscans: bool = False) -> list[DatasetView]:
    views: list[DatasetView] = []

    for index, eis_data in enumerate(_eis_data_items(measurement), start=1):
        dataset = _get_dataset(eis_data)
        if _has_arrays(dataset):
            title = _get_title(eis_data, f"EIS {index}")
            views.append(DatasetView(f"eis_{index}", title, dataset, eis_data, is_eis=True))

        if include_subscans:
            for subscan_index, subscan in enumerate(_subscan_items(eis_data), start=1):
                subscan_dataset = _get_dataset(subscan)
                if _has_arrays(subscan_dataset):
                    title = _get_title(subscan, f"EIS {index} subscan {subscan_index}")
                    view_id = f"eis_{index}_subscan_{subscan_index}"
                    views.append(DatasetView(view_id, title, subscan_dataset, subscan, is_eis=True))

    dataset = _get_dataset(measurement)
    if _has_arrays(dataset):
        views.append(DatasetView("measurement", _get_title(measurement, "Measurement"), dataset, measurement))

    return views


def primary_measurement_dataset(measurement):
    views = measurement_dataset_views(measurement)
    if not views:
        return None
    return views[0].dataset


def measurement_arrays(measurement) -> list[Any]:
    dataset = primary_measurement_dataset(measurement)
    if dataset is None:
        return []
    return dataset_arrays(dataset)


def dataset_arrays(dataset) -> list[Any]:
    arrays = getattr(dataset, "arrays", None)
    if callable(arrays):
        return list(arrays())

    values = getattr(dataset, "values", None)
    if callable(values):
        return list(values())

    try:
        return [dataset[key] for key in dataset]
    except TypeError:
        return []


def default_axis_indexes(arrays: list[Any]) -> tuple[int, int]:
    if not arrays:
        return 0, 0

    x_index = _find_array_index(arrays, ("Frequency",), ("frequency", "freq", "f"))
    y_index = _find_array_index(arrays, ("Z",), ("z", "impedance", "modulus"))

    if x_index is not None and y_index is not None and x_index != y_index:
        return x_index, y_index

    x_index = _find_array_index(arrays, ("ZRe",), ("zre", "zreal", "z'", "z`"))
    y_index = _find_array_index(arrays, ("ZIm",), ("zim", "zimag", "z''", "z``"))

    if x_index is not None and y_index is not None and x_index != y_index:
        return x_index, y_index

    return 0, min(1, len(arrays) - 1)


def _get_dataset(source):
    if source is None:
        return None
    return getattr(source, "dataset", None)


def _has_arrays(dataset) -> bool:
    if dataset is None:
        return False
    return bool(dataset_arrays(dataset))


def _get_title(source, default: str) -> str:
    title = getattr(source, "title", None)
    return str(title) if title else default


def _eis_data_items(measurement) -> list[Any]:
    for attribute in ("eis_data", "eisdata"):
        eis_data = getattr(measurement, attribute, None)
        if eis_data:
            return list(eis_data)
    return []


def _subscan_items(eis_data) -> list[Any]:
    subscans = getattr(eis_data, "subscans", None)
    if subscans:
        return list(subscans)
    return []


def _find_array_index(arrays: list[Any], type_names: tuple[str, ...], text_names: tuple[str, ...]) -> int | None:
    normalized_types = {_normalize_text(name) for name in type_names}
    normalized_texts = {_normalize_text(name) for name in text_names}

    for index, data_array in enumerate(arrays):
        array_type = _normalize_text(getattr(data_array, "type", ""))
        if array_type in normalized_types:
            return index

    for index, data_array in enumerate(arrays):
        texts = (
            _normalize_text(getattr(data_array, "name", "")),
            _normalize_text(getattr(data_array, "quantity", "")),
        )
        if any(text in normalized_texts for text in texts):
            return index

    return None


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return "".join(character for character in str(value).casefold() if character.isalnum())
