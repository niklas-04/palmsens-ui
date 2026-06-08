from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QToolBar,
    QDialog,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QDialogButtonBox,
    QMessageBox,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QAction
import pyqtgraph as pg
import ps_helpers as pslib
import re


_GROUPED_KEY_PATTERN = re.compile(r"^(?P<base>.+)_(?P<group>\d+)$")


def _dataset_entries(dataset):
    if hasattr(dataset, "items"):
        try:
            return [(str(key), data_array) for key, data_array in dataset.items()]
        except TypeError:
            pass

    return [
        (getattr(data_array, "name", f"array_{index}"), data_array)
        for index, data_array in enumerate(dataset.arrays())
    ]


def _split_grouped_name(value):
    match = _GROUPED_KEY_PATTERN.match(str(value))
    if match:
        return match.group("base"), match.group("group")
    return str(value), None


def _normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _is_time_array(entry):
    data_array = entry["array"]
    texts = (
        _normalize_text(entry["base_key"]),
        _normalize_text(getattr(data_array, "name", "")),
        _normalize_text(getattr(data_array, "type", "")),
    )
    unit = _normalize_text(getattr(data_array, "unit", ""))
    return any(text.startswith("time") or "elapsedtime" in text for text in texts) or unit in {
        "s",
        "sec",
        "second",
        "seconds",
        "ms",
    }


def _is_voltage_array(entry):
    data_array = entry["array"]
    texts = (
        _normalize_text(entry["base_key"]),
        _normalize_text(getattr(data_array, "name", "")),
        _normalize_text(getattr(data_array, "type", "")),
    )
    unit = _normalize_text(getattr(data_array, "unit", ""))
    return any("potential" in text or "voltage" in text for text in texts) or unit in {
        "v",
        "mv",
    }


def _voltage_preference(entry):
    data_array = entry["array"]
    text = _normalize_text(f"{entry['base_key']} {getattr(data_array, 'name', '')}")
    if "wevsce" in text:
        return 2
    if "appliedpotential" in text or text.startswith("potential") or text.startswith("voltage"):
        return 0
    return 1


def _measurement_segments(dataset):
    groups = {}

    for key, data_array in _dataset_entries(dataset):
        base_key, group_id = _split_grouped_name(key)
        if group_id is None:
            base_key, group_id = _split_grouped_name(getattr(data_array, "name", key))
        if group_id is None:
            continue

        group = groups.setdefault(group_id, {"id": group_id, "arrays": []})
        group["arrays"].append(
            {
                "key": key,
                "base_key": base_key,
                "array": data_array,
            }
        )

    segments = []
    for group in groups.values():
        time_entry = next((entry for entry in group["arrays"] if _is_time_array(entry)), None)
        voltage_entries = [entry for entry in group["arrays"] if _is_voltage_array(entry)]
        if time_entry is None or not voltage_entries:
            continue

        voltage_entry = sorted(voltage_entries, key=_voltage_preference)[0]
        segments.append(
            {
                "id": group["id"],
                "label": f"Measurement {group['id']}",
                "time_array": time_entry["array"],
                "voltage_array": voltage_entry["array"],
            }
        )

    return sorted(
        segments,
        key=lambda segment: (
            int(segment["id"]) if str(segment["id"]).isdigit() else float("inf"),
            str(segment["id"]),
        ),
    )


class graph_widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("graphWidget")
        self.measurement = None
        self.x_index = None
        self.y_index = None
        self.live_curve = None
        self.combine_measurements = True
        self.selected_measurement_ids = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.getAxis("bottom").setPen("#7b8794")
        self.plot_widget.getAxis("left").setPen("#7b8794")
        self.plot_widget.getAxis("bottom").setTextPen("#56616f")
        self.plot_widget.getAxis("left").setTextPen("#56616f")
        layout.addWidget(self.plot_widget)

    def plot_measurement(
        self,
        measurement,
        x_index=0,
        y_index=1,
        combine_measurements=None,
        measurement_ids=None,
    ):
        self.measurement = measurement
        self.x_index = x_index
        self.y_index = y_index

        dataset = self.measurement.dataset
        arrays = list(dataset.arrays())
        if not arrays:
            return
        if self.x_index >= len(arrays):
            self.x_index = 0
        if self.y_index >= len(arrays):
            self.y_index = min(1, len(arrays) - 1)

        segments = _measurement_segments(dataset)
        if combine_measurements is None:
            combine_measurements = bool(segments)

        if combine_measurements and segments:
            selected_ids = tuple(measurement_ids or [segment["id"] for segment in segments])
            selected_segments = [
                segment
                for segment in segments
                if segment["id"] in selected_ids
            ]
            if selected_segments:
                self.combine_measurements = True
                self.selected_measurement_ids = selected_ids
                self._plot_combined_measurements(selected_segments)
                return

        self.combine_measurements = False
        self.selected_measurement_ids = ()
        x_array = arrays[self.x_index]
        y_array = arrays[self.y_index]
        self._plot_arrays(x_array, y_array)

    def plot_live_data(self, callback_data):
        self.measurement = None
        self.x_index = 0
        self.y_index = 1
        self.combine_measurements = False
        self.selected_measurement_ids = ()
        self._plot_arrays(callback_data.x_array, callback_data.y_array)

    def _plot_combined_measurements(self, segments):
        x_values = []
        y_values = []

        for segment in segments:
            time_values = segment["time_array"].to_numpy()
            voltage_values = segment["voltage_array"].to_numpy()
            count = min(len(time_values), len(voltage_values))
            x_values.extend(time_values[:count])
            y_values.extend(voltage_values[:count])

        if not x_values or not y_values:
            self.plot_widget.clear()
            self.live_curve = None
            return

        first_time = segments[0]["time_array"]
        first_voltage = segments[0]["voltage_array"]
        self.plot_widget.setLabel("bottom", f"{first_time.name}, {first_time.unit}")
        self.plot_widget.setLabel("left", f"{first_voltage.name}, {first_voltage.unit}")
        pen = pg.mkPen(color="#2f6f9f", width=2)

        self.plot_widget.clear()
        self.live_curve = self.plot_widget.plot(x_values, y_values, pen=pen)

    def _plot_arrays(self, x_array, y_array):
        x_values = x_array.to_numpy()
        y_values = y_array.to_numpy()

        self.plot_widget.setLabel("bottom", f"{x_array.name}, {x_array.unit}")
        self.plot_widget.setLabel("left", f"{y_array.name}, {y_array.unit}")
        pen = pg.mkPen(color="#2f6f9f", width=2)

        self.plot_widget.clear()
        self.live_curve = self.plot_widget.plot(x_values, y_values, pen=pen)


class axis_selection_dialog(QDialog):
    def __init__(
        self,
        arrays,
        segments=(),
        current_x=0,
        current_y=1,
        combine_measurements=True,
        selected_measurement_ids=(),
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Axes")
        self.segments = list(segments)
        self.measurement_checks = {}

        layout = QFormLayout(self)
        self.combine_check = QCheckBox("Combine measurement time/voltage arrays", self)
        self.x_combo = QComboBox(self)
        self.y_combo = QComboBox(self)

        for index, data_array in enumerate(arrays):
            label = self._format_array_label(index, data_array)
            self.x_combo.addItem(label, index)
            self.y_combo.addItem(label, index)

        self.x_combo.setCurrentIndex(current_x)
        self.y_combo.setCurrentIndex(current_y)

        if self.segments:
            self.combine_check.setChecked(combine_measurements)
            self.combine_check.toggled.connect(self._update_axis_controls)
            layout.addRow("View", self.combine_check)

            selected_ids = set(selected_measurement_ids)
            if not selected_ids:
                selected_ids = {segment["id"] for segment in self.segments}

            measurement_widget = QWidget(self)
            measurement_layout = QVBoxLayout(measurement_widget)
            measurement_layout.setContentsMargins(0, 0, 0, 0)
            measurement_layout.setSpacing(4)

            for segment in self.segments:
                checkbox = QCheckBox(segment["label"], measurement_widget)
                checkbox.setChecked(segment["id"] in selected_ids)
                self.measurement_checks[segment["id"]] = checkbox
                measurement_layout.addWidget(checkbox)

            layout.addRow("Measurements", measurement_widget)

        layout.addRow("X axis", self.x_combo)
        layout.addRow("Y axis", self.y_combo)
        self._update_axis_controls()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def selected_axes(self):
        selected_measurement_ids = tuple(
            measurement_id
            for measurement_id, checkbox in self.measurement_checks.items()
            if checkbox.isChecked()
        )
        return (
            self.x_combo.currentData(),
            self.y_combo.currentData(),
            self.combine_check.isChecked() and bool(self.segments),
            selected_measurement_ids,
        )

    def accept(self):
        if self.combine_check.isChecked() and self.segments:
            if not any(checkbox.isChecked() for checkbox in self.measurement_checks.values()):
                QMessageBox.warning(
                    self,
                    "No measurements selected",
                    "Select at least one measurement to plot.",
                )
                return
        super().accept()

    def _update_axis_controls(self):
        use_combined = self.combine_check.isChecked() and bool(self.segments)
        self.x_combo.setEnabled(not use_combined)
        self.y_combo.setEnabled(not use_combined)
        for checkbox in self.measurement_checks.values():
            checkbox.setEnabled(use_combined)

    @staticmethod
    def _format_array_label(index, data_array):
        name = getattr(data_array, "name", f"array_{index}")
        unit = getattr(data_array, "unit", "")
        array_type = getattr(data_array, "type", "")

        details = [detail for detail in (array_type, unit) if detail]
        if details:
            return f"{index}: {name} ({', '.join(details)})"
        return f"{index}: {name}"


class graph_panel(QFrame):
    run_requested = Signal() # Dessa två signaler kan användas senare i main fönstret för att intiera/stoppa measurement
    stop_requested = Signal()
    expand_requested = Signal(bool)

    def __init__(self, title, instrument=None):
        super().__init__()
        self.setObjectName("graphPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.instrument = instrument
        self.base_title = title

        self.graph = graph_widget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        self.title_label = QLabel(self.base_title)
        self.title_label.setObjectName("graphPanelTitle")
        header_layout.addWidget(self.title_label, 1)

        self.toolbar = QToolBar("Graph Utilities", self)
        self.toolbar.setObjectName("graphToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        header_layout.addWidget(self.toolbar, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(header_layout)
        layout.addWidget(self.graph, 1)

        self.run_action = QAction("Run", self)
        self.stop_action = QAction("Stop", self)
        self.expand_action = QAction("Expand", self)
        self.expand_action.setCheckable(True)
        self.axes_action = QAction("Edit Axes", self)

        self.toolbar.addAction(self.run_action)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.addAction(self.expand_action)
        self.toolbar.addAction(self.axes_action)

        self.run_action.triggered.connect(self.run_requested.emit)
        self.stop_action.triggered.connect(self.stop_requested.emit)
        self.expand_action.toggled.connect(self.expand_requested.emit)
        self.axes_action.triggered.connect(self.edit_axes)
        self.set_running(False)

    def set_running(self, is_running: bool):
        self.run_action.setEnabled(not is_running)
        self.stop_action.setEnabled(is_running)

    def set_status_text(self, status: str | None = None):
        if status:
            self.title_label.setText(f"{self.base_title} [{status}]")
        else:
            self.title_label.setText(self.base_title)

    def set_expanded(self, is_expanded: bool):
        self.expand_action.blockSignals(True)
        self.expand_action.setChecked(is_expanded)
        self.expand_action.setText("Restore" if is_expanded else "Expand")
        self.expand_action.blockSignals(False)

    def edit_axes(self):
        measurement = self.graph.measurement
        if measurement is None:
            QMessageBox.information(
                self,
                "No measurement loaded",
                "Load or run a measurement before editing axes.",
            )
            return

        arrays = list(measurement.dataset.arrays())
        if not arrays:
            QMessageBox.warning(
                self,
                "No data arrays",
                "This measurement does not contain any plottable arrays.",
            )
            return

        current_x = self.graph.x_index if self.graph.x_index is not None else 0
        current_y = self.graph.y_index if self.graph.y_index is not None else min(1, len(arrays) - 1)
        segments = _measurement_segments(measurement.dataset)

        dialog = axis_selection_dialog(
            arrays,
            segments=segments,
            current_x=current_x,
            current_y=current_y,
            combine_measurements=self.graph.combine_measurements,
            selected_measurement_ids=self.graph.selected_measurement_ids,
            parent=self,
        )
        if dialog.exec():
            x_index, y_index, combine_measurements, measurement_ids = dialog.selected_axes()
            self.graph.plot_measurement(
                measurement,
                x_index=x_index,
                y_index=y_index,
                combine_measurements=combine_measurements,
                measurement_ids=measurement_ids,
            )
