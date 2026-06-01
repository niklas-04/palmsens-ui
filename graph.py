from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QToolBar,
    QDialog,
    QFormLayout,
    QComboBox,
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


_GROUPED_KEY_PATTERN = re.compile(r"^(?P<base>.+?)_(?P<group>\d+)$")
_GROUP_COLORS = (
    "#2f6f9f",
    "#c15a2c",
    "#2e8b57",
    "#7a4fa3",
    "#b33c5a",
    "#4f6d7a",
)


def _split_dataset_key(key):
    match = _GROUPED_KEY_PATTERN.match(key)
    if match:
        return match.group("base"), match.group("group")
    return key, None


def _measurement_groups(dataset):
    groups: dict[str, dict] = {}

    for key, data_array in dataset.items():
        base_key, group_id = _split_dataset_key(key)
        normalized_group_id = group_id or "default"
        group = groups.setdefault(
            normalized_group_id,
            {
                "id": normalized_group_id,
                "label": (
                    f"Measurement {group_id}"
                    if group_id is not None
                    else "Measurement"
                ),
                "arrays": [],
                "by_base_key": {},
            },
        )
        entry = {
            "key": key,
            "base_key": base_key,
            "array": data_array,
        }
        group["arrays"].append(entry)
        group["by_base_key"][base_key] = entry

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            group["id"] == "default",
            int(group["id"]) if group["id"].isdigit() else float("inf"),
            group["id"],
        ),
    )
    return ordered_groups


def _default_axis_keys(group):
    arrays = group["arrays"]
    if not arrays:
        return None, None

    x_key = arrays[0]["base_key"]
    y_key = arrays[min(1, len(arrays) - 1)]["base_key"]
    return x_key, y_key


def _axis_entries_for_group(group):
    return [
        {
            "axis_key": entry["base_key"],
            "label": axis_selection_dialog.format_array_label(entry["array"], entry["base_key"]),
        }
        for entry in group["arrays"]
    ]


def _axis_entries_for_all_groups(groups):
    entries_by_key: dict[str, dict] = {}
    for group in groups:
        for entry in group["arrays"]:
            axis_key = entry["base_key"]
            if axis_key not in entries_by_key:
                entries_by_key[axis_key] = {
                    "axis_key": axis_key,
                    "label": axis_selection_dialog.format_array_label(entry["array"], axis_key),
                }
    return list(entries_by_key.values())


class graph_widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("graphWidget")
        self.measurement = None
        self.x_index = None
        self.y_index = None
        self.selected_group_id = None
        self.selected_x_key = None
        self.selected_y_key = None
        self.legend = None

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

    def plot_measurement(self, measurement, x_key=None, y_key=None, group_id=None):
        self.measurement = measurement
        dataset = self.measurement.dataset
        groups = _measurement_groups(dataset)
        if not groups:
            return

        selected_group_id = group_id
        if selected_group_id is None:
            selected_group_id = "all" if len(groups) > 1 else groups[0]["id"]

        current_group = next(
            (group for group in groups if group["id"] == selected_group_id),
            None,
        )
        if current_group is None:
            current_group = groups[0]
            selected_group_id = current_group["id"]

        default_x_key, default_y_key = _default_axis_keys(current_group)
        x_key = x_key or default_x_key
        y_key = y_key or default_y_key
        self.selected_group_id = selected_group_id
        self.selected_x_key = x_key
        self.selected_y_key = y_key

        axis_entries = (
            _axis_entries_for_all_groups(groups)
            if selected_group_id == "all"
            else _axis_entries_for_group(current_group)
        )
        axis_keys = [entry["axis_key"] for entry in axis_entries]
        if x_key not in axis_keys:
            x_key = axis_keys[0]
            self.selected_x_key = x_key
        if y_key not in axis_keys:
            y_key = axis_keys[min(1, len(axis_keys) - 1)]
            self.selected_y_key = y_key

        if selected_group_id == "all":
            self._plot_grouped_measurements(groups, x_key, y_key)
            return

        x_entry = current_group["by_base_key"].get(x_key)
        y_entry = current_group["by_base_key"].get(y_key)
        if x_entry is None or y_entry is None:
            return

        self._plot_arrays(
            [(x_entry["array"], y_entry["array"], current_group["label"], _GROUP_COLORS[0])],
        )

    def plot_live_data(self, callback_data):
        self.measurement = None
        self.x_index = 0
        self.y_index = 1
        self.selected_group_id = None
        self.selected_x_key = None
        self.selected_y_key = None
        self._plot_arrays(
            [(callback_data.x_array, callback_data.y_array, None, _GROUP_COLORS[0])],
        )

    def _plot_grouped_measurements(self, groups, x_key, y_key):
        curves = []
        for index, group in enumerate(groups):
            x_entry = group["by_base_key"].get(x_key)
            y_entry = group["by_base_key"].get(y_key)
            if x_entry is None or y_entry is None:
                continue
            curves.append(
                (
                    x_entry["array"],
                    y_entry["array"],
                    group["label"],
                    _GROUP_COLORS[index % len(_GROUP_COLORS)],
                )
            )

        if curves:
            self._plot_arrays(curves)

    def _reset_plot(self):
        self.plot_widget.clear()
        if self.legend is not None:
            self.plot_widget.removeItem(self.legend)
            self.legend = None

    def _plot_arrays(self, curves):
        if not curves:
            self._reset_plot()
            return

        self._reset_plot()
        if any(label for _, _, label, _ in curves):
            self.legend = self.plot_widget.addLegend(offset=(10, 10))

        first_x_array, first_y_array, _, _ = curves[0]
        self.plot_widget.setLabel("bottom", f"{first_x_array.name}, {first_x_array.unit}")
        self.plot_widget.setLabel("left", f"{first_y_array.name}, {first_y_array.unit}")

        for x_array, y_array, label, color in curves:
            x_values = x_array.to_numpy()
            y_values = y_array.to_numpy()
            pen = pg.mkPen(color=color, width=2)
            self.plot_widget.plot(x_values, y_values, pen=pen, name=label)


class axis_selection_dialog(QDialog):
    def __init__(self, groups, current_group_id, current_x_key, current_y_key, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Axes")
        self.groups = groups

        layout = QFormLayout(self)
        self.group_combo = QComboBox(self)
        self.x_combo = QComboBox(self)
        self.y_combo = QComboBox(self)

        if len(groups) > 1:
            self.group_combo.addItem("All measurements", "all")
        for group in groups:
            self.group_combo.addItem(group["label"], group["id"])

        group_index = max(0, self.group_combo.findData(current_group_id))
        self.group_combo.setCurrentIndex(group_index)
        self.group_combo.currentIndexChanged.connect(self._populate_axis_combos)
        self._populate_axis_combos()
        self._set_current_axis(self.x_combo, current_x_key)
        self._set_current_axis(self.y_combo, current_y_key)

        layout.addRow("Measurement", self.group_combo)
        layout.addRow("X axis", self.x_combo)
        layout.addRow("Y axis", self.y_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def selected_axes(self):
        return (
            self.group_combo.currentData(),
            self.x_combo.currentData(),
            self.y_combo.currentData(),
        )

    def _populate_axis_combos(self):
        group_id = self.group_combo.currentData()
        axis_entries = self._axis_entries(group_id)
        self.x_combo.clear()
        self.y_combo.clear()
        for entry in axis_entries:
            self.x_combo.addItem(entry["label"], entry["axis_key"])
            self.y_combo.addItem(entry["label"], entry["axis_key"])

        if self.y_combo.count() > 1:
            self.y_combo.setCurrentIndex(1)

    def _axis_entries(self, group_id):
        if group_id == "all":
            return _axis_entries_for_all_groups(self.groups)

        current_group = next(
            (group for group in self.groups if group["id"] == group_id),
            None,
        )
        if current_group is None:
            return []
        return _axis_entries_for_group(current_group)

    @staticmethod
    def _set_current_axis(combo, axis_key):
        if axis_key is None:
            return

        index = combo.findData(axis_key)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def format_array_label(data_array, axis_key):
        name = getattr(data_array, "name", axis_key)
        unit = getattr(data_array, "unit", "")
        array_type = getattr(data_array, "type", "")

        details = [detail for detail in (array_type, unit) if detail]
        if details:
            return f"{name} ({', '.join(details)})"
        return str(name)


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

        groups = _measurement_groups(measurement.dataset)
        if not groups:
            QMessageBox.warning(
                self,
                "No data arrays",
                "This measurement does not contain any plottable arrays.",
            )
            return

        current_group_id = self.graph.selected_group_id
        if current_group_id is None:
            current_group_id = "all" if len(groups) > 1 else groups[0]["id"]
        current_group = next(
            (group for group in groups if group["id"] == current_group_id),
            groups[0],
        )
        default_x_key, default_y_key = _default_axis_keys(current_group)
        current_x_key = self.graph.selected_x_key or default_x_key
        current_y_key = self.graph.selected_y_key or default_y_key

        dialog = axis_selection_dialog(
            groups,
            current_group_id=current_group_id,
            current_x_key=current_x_key,
            current_y_key=current_y_key,
            parent=self,
        )
        if dialog.exec():
            group_id, x_key, y_key = dialog.selected_axes()
            self.graph.plot_measurement(measurement, x_key=x_key, y_key=y_key, group_id=group_id)
