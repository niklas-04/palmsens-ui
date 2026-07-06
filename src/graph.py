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
    QCheckBox
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QAction
import pyqtgraph as pg
import re
import numpy as np

from src.measurement_data import DatasetView, dataset_arrays, default_axis_indexes, measurement_arrays, measurement_dataset_views

def _canonical_measurement_name(name):
    if name.startswith("Applied"):
        base_name = name.removeprefix("Applied")
        if base_name in {"Current", "Potential", "Voltage"}:
            return base_name
    return name

def _axis_group_name(data_array):
    name = _get_name(data_array, "")
    stripped_name = re.sub(r"\d+_\d+$", "", str(name))
    canonical_name = _canonical_measurement_name(stripped_name)
    if _is_metadata_array_name(canonical_name):
        return None
    return canonical_name or None

def _is_metadata_array_name(name):
    return str(name) in {"segment_index", "step_id", "execution_index", "step_type"}

def _get_unit(data_array, default = None):
    return getattr(data_array, "unit", default)

def _get_name(data_array, default = None):
    return getattr(data_array, "name", default)

class _LiveDataset:
    def __init__(self, title, arrays):
        self.title = title
        self._arrays = tuple(arrays)

    def arrays(self):
        return self._arrays

class graph_widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("graphWidget")
        self.measurement = None
        self.x_index = None
        self.y_index = None
        self.dataset_view_id = None
        self.live_dataset_views = []
        self.live_axis_selection = None
        self.live_curve = None
        self.right_view = None
        self.right_curve = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.getAxis("bottom").setPen("#7b8794")
        self.plot_widget.getAxis("left").setPen("#7b8794")
        self.plot_widget.getAxis("bottom").setTextPen("#56616f")
        self.plot_widget.getAxis("left").setTextPen("#56616f")
        self.plot_item = self.plot_widget.getPlotItem()
        self._setup_right_axis()
        layout.addWidget(self.plot_widget)

    def plot_measurement(self, measurement, selection=None):
        self.measurement = measurement
        self.live_dataset_views = []
        self.live_axis_selection = None
        dataset_view = self._dataset_view_for_selection(measurement, selection)
        self._plot_dataset_view(dataset_view, selection)

    def _plot_dataset_view(self, dataset_view, selection=None):
        arrays = dataset_arrays(dataset_view.dataset) if dataset_view is not None else []

        if not arrays:
            self.plot_widget.clear()
            self.live_curve = None
            return

        if dataset_view is not None:
            self.dataset_view_id = dataset_view.id

        if selection:
            if selection["grouped"]:
                left_x, left_y = self._concat_grouped_arrays(arrays, selection["x"], selection["left_y"])
                if selection["right_y"] is None:
                    self._plot_arrays(left_x, left_y, selection["x"], selection["left_y"])
                    return
                right_x, right_y = self._concat_grouped_arrays(arrays, selection["x"], selection["right_y"])
                self._plot_dual_arrays(
                    left_x,
                    left_y,
                    right_x,
                    right_y,
                    selection["x"],
                    selection["left_y"],
                    selection["right_y"],
                )
                return
            self.x_index = selection["x"]
            self.y_index = selection["left_y"]
            if selection["right_y"] is not None:
                self._plot_dual_arrays_from_indexes(arrays, self.x_index, self.y_index, selection["right_y"])
                return
        else:
            self.x_index, self.y_index = default_axis_indexes(arrays)

        if self.x_index >= len(arrays):
            self.x_index = 0
        if self.y_index >= len(arrays):
            self.y_index = min(1, len(arrays) - 1)

        x_array = arrays[self.x_index]
        y_array = arrays[self.y_index]
        self._plot_arrays(x_array.to_numpy(),
                          y_array.to_numpy(),
                          f"{x_array.name}, {x_array.unit}",
                          f"{y_array.name}, {y_array.unit}"
                          )

    def _dataset_view_for_selection(self, measurement, selection=None):
        return self._dataset_view_from_views(measurement_dataset_views(measurement), selection)

    def _dataset_view_from_views(self, dataset_views, selection=None):
        if not dataset_views:
            return None

        selected_dataset_id = selection.get("dataset_id") if selection else None
        if selected_dataset_id is not None:
            for dataset_view in dataset_views:
                if dataset_view.id == selected_dataset_id:
                    return dataset_view

        if self.dataset_view_id is not None:
            for dataset_view in dataset_views:
                if dataset_view.id == self.dataset_view_id:
                    return dataset_view

        for dataset_view in dataset_views:
            if not dataset_view.is_eis:
                return dataset_view
        return dataset_views[0]

    def plot_live_data(self, callback_data):
        self.measurement = None
        dataset_view = self._live_dataset_view(callback_data)
        if dataset_view is None:
            return

        self.live_dataset_views = [dataset_view]
        selection = self.live_axis_selection
        if selection and selection.get("dataset_id") != dataset_view.id:
            selection = None
        self._plot_dataset_view(dataset_view, selection)

    def plot_live_selection(self, selection):
        self.live_axis_selection = selection
        dataset_view = self._dataset_view_from_views(self.live_dataset_views, selection)
        self._plot_dataset_view(dataset_view, selection)

    def _live_dataset_view(self, callback_data):
        x_array = getattr(callback_data, "x_array", None)
        y_array = getattr(callback_data, "y_array", None)
        if x_array is not None and y_array is not None:
            dataset = _LiveDataset("Live Data", (x_array, y_array))
            return DatasetView("live", "Live Data", dataset, callback_data)

        dataset = getattr(callback_data, "data", None)
        if dataset is None:
            return None
        title = getattr(dataset, "title", None) or "Live EIS"
        return DatasetView("eis_live", str(title), dataset, callback_data, is_eis=True)

    def _plot_arrays(self, x_array, y_array, x_label, y_label):
        x_array = np.asarray(x_array).ravel()
        y_array = np.asarray(y_array).ravel()
        if x_array.shape != y_array.shape:
            return
        self.plot_widget.clear()
        self._clear_right_axis()
        self.plot_widget.setLabel("bottom", f"{x_label}")
        self.plot_widget.setLabel("left", f"{y_label}")
        pen = pg.mkPen(color="#2f6f9f", width=2)
        self.live_curve = self.plot_widget.plot(x_array, y_array, pen=pen)

    def _plot_dual_arrays_from_indexes(self, arrays, x_index, left_y_index, right_y_index):
        if x_index >= len(arrays):
            x_index = 0
        if left_y_index >= len(arrays):
            left_y_index = min(1, len(arrays) - 1)
        if right_y_index >= len(arrays):
            right_y_index = None

        x_array = arrays[x_index]
        left_y_array = arrays[left_y_index]
        if right_y_index is None:
            self._plot_arrays(
                x_array.to_numpy(),
                left_y_array.to_numpy(),
                f"{x_array.name}, {x_array.unit}",
                f"{left_y_array.name}, {left_y_array.unit}",
            )
            return

        right_y_array = arrays[right_y_index]
        self._plot_dual_arrays(
            x_array.to_numpy(),
            left_y_array.to_numpy(),
            x_array.to_numpy(),
            right_y_array.to_numpy(),
            f"{x_array.name}, {x_array.unit}",
            f"{left_y_array.name}, {left_y_array.unit}",
            f"{right_y_array.name}, {right_y_array.unit}",
        )

    def _plot_dual_arrays(self, left_x, left_y, right_x, right_y, x_label, left_label, right_label):
        left_x = np.asarray(left_x).ravel()
        left_y = np.asarray(left_y).ravel()
        right_x = np.asarray(right_x).ravel()
        right_y = np.asarray(right_y).ravel()
        if left_x.shape != left_y.shape:
            return
        if right_x.shape != right_y.shape:
            self._plot_arrays(left_x, left_y, x_label, left_label)
            return

        self.plot_widget.clear()
        self._clear_right_axis()
        self.plot_item.showAxis("right")
        self.plot_item.setLabel("bottom", f"{x_label}")
        self.plot_item.setLabel("left", f"{left_label}", color="#2f6f9f")
        self.plot_item.setLabel("right", f"{right_label}", color="#7c3aed")

        self.live_curve = self.plot_item.plot(
            left_x,
            left_y,
            pen=pg.mkPen(color="#2f6f9f", width=2),
        )
        self.right_curve = pg.PlotDataItem(
            right_x,
            right_y,
            pen=pg.mkPen(color="#7c3aed", width=2),
        )
        self.right_view.addItem(self.right_curve)
        self._update_right_axis()
        self.right_view.autoRange()

    def _setup_right_axis(self):
        self.right_view = pg.ViewBox()
        self.plot_item.showAxis("right")
        self.plot_item.scene().addItem(self.right_view)
        self.plot_item.getAxis("right").linkToView(self.right_view)
        self.right_view.setXLink(self.plot_item.vb)
        self.plot_item.getAxis("right").setPen("#7b8794")
        self.plot_item.getAxis("right").setTextPen("#56616f")
        self.plot_item.vb.sigResized.connect(self._update_right_axis)
        self.plot_item.hideAxis("right")

    def _clear_right_axis(self):
        if self.right_view is not None:
            self.right_view.clear()
        self.right_curve = None
        self.plot_item.hideAxis("right")

    def _update_right_axis(self): # TODO:fixa till eis data, inte numrerat? eller pröva fler eis? 
        if self.right_view is None:
            return
        self.right_view.setGeometry(self.plot_item.vb.sceneBoundingRect())
        self.right_view.linkedViewChanged(self.plot_item.vb, self.right_view.XAxis)
    
    @staticmethod
    def _concat_grouped_arrays(arrays, name_arr_1, name_arr_2):
        pattern = re.compile(r"^(?P<measurement>[A-Za-z_]+?)(?P<measurement_number>\d+)_(?P<group>\d+)$")

        groups = {}
        for arr in arrays:
            name = _get_name(arr, "")
            match = pattern.match(name)
            if not match:
                continue

            measurement = _canonical_measurement_name(match.group("measurement"))
            if measurement not in {name_arr_1, name_arr_2}:
                continue

            group = int(match.group("group"))
            grouped_arrays = groups.setdefault(group, {})
            if measurement not in grouped_arrays or not match.group("measurement").startswith("Applied"):
                grouped_arrays[measurement] = arr

        concat_arr1 = []
        concat_arr2 = []
        for group in sorted(groups):
            grouped_arrays = groups[group]
            if name_arr_1 not in grouped_arrays or name_arr_2 not in grouped_arrays:
                continue
            x_values = np.asarray(grouped_arrays[name_arr_1].to_numpy()).ravel()
            y_values = np.asarray(grouped_arrays[name_arr_2].to_numpy()).ravel()
            if x_values.shape != y_values.shape:
                continue
            concat_arr1.extend(x_values)
            concat_arr2.extend(y_values)

        if concat_arr1 and concat_arr2:
            return np.asarray(concat_arr1), np.asarray(concat_arr2)

        x_array = next((arr for arr in arrays if _axis_group_name(arr) == name_arr_1), None)
        y_array = next((arr for arr in arrays if _axis_group_name(arr) == name_arr_2), None)
        if x_array is None or y_array is None:
            return np.asarray([]), np.asarray([])

        x_values = np.asarray(x_array.to_numpy()).ravel()
        y_values = np.asarray(y_array.to_numpy()).ravel()
        if x_values.shape != y_values.shape:
            return np.asarray([]), np.asarray([])
        return x_values, y_values


class axis_selection_dialog(QDialog):
    def __init__(
        self,
        dataset_views,
        current_dataset_id=None,
        current_x=0,
        current_y=1,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Axes")

        layout = QFormLayout(self)
        self.dataset_combo = QComboBox(self)
        self.x_combo = QComboBox(self)
        self.left_y_combo = QComboBox(self)
        self.right_y_combo = QComboBox(self)
        self.checkbox = QCheckBox(self)
        self.dataset_views = dataset_views
        self.arrays = []
        self.current_x = current_x
        self.current_y = current_y
        self.current_dataset_id = current_dataset_id

        self.rebuild_dataset_choice()
        self.rebuild_axis_choice() 
        
        self.dataset_combo.currentIndexChanged.connect(self.rebuild_axis_choice)
        self.checkbox.toggled.connect(self.rebuild_axis_choice)

        layout.addRow("Dataset", self.dataset_combo)
        layout.addRow("X axis", self.x_combo)
        layout.addRow("Left Y axis", self.left_y_combo)
        layout.addRow("Right Y axis", self.right_y_combo)
        layout.addRow("Group", self.checkbox)
        

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def rebuild_dataset_choice(self):
        self.dataset_combo.clear()
        for dataset_view in self.dataset_views:
            self.dataset_combo.addItem(dataset_view.title, dataset_view.id)

        if self.current_dataset_id is not None:
            self._set_combo_to_data(self.dataset_combo, self.current_dataset_id)
        elif self.dataset_combo.count():
            self.dataset_combo.setCurrentIndex(0)

    def rebuild_axis_choice(self):
        self.x_combo.clear()
        self.left_y_combo.clear()
        self.right_y_combo.clear()
        dataset_view = self.selected_dataset_view()
        self.arrays = dataset_arrays(dataset_view.dataset) if dataset_view is not None else []
        
        if self.checkbox.isChecked():
            measurement_names = self._unique_measurements()
            self.right_y_combo.addItem("None", None)
            for meas_name in measurement_names:
                self.x_combo.addItem(meas_name, meas_name)
                self.left_y_combo.addItem(meas_name, meas_name)
                self.right_y_combo.addItem(meas_name, meas_name)
            self._set_combo_to_data(self.x_combo, "Time")
            self._set_combo_to_data(self.left_y_combo, "Potential")
            self._set_combo_to_data(self.right_y_combo, "Current")
        else:
            self.right_y_combo.addItem("None", None)
            for index, data_array in enumerate(self.arrays):
                if _is_metadata_array_name(_get_name(data_array, "")):
                    continue
                label = self._format_array_label(index, data_array)
                self.x_combo.addItem(label, index)
                self.left_y_combo.addItem(label, index)
                self.right_y_combo.addItem(label, index)
            if self.dataset_combo.currentData() == self.current_dataset_id:
                x_index = self.current_x
                y_index = self.current_y
            else:
                x_index, y_index = default_axis_indexes(self.arrays)
            self._set_combo_to_data(self.x_combo, x_index)
            self._set_combo_to_data(self.left_y_combo, y_index)
        
    def selected_axes(self):
        return {
            "dataset_id": self.dataset_combo.currentData(),
            "grouped": self.checkbox.isChecked(),
            "x": self.x_combo.currentData(),
            "left_y": self.left_y_combo.currentData(),
            "right_y": self.right_y_combo.currentData(),
        }

    def selected_dataset_view(self):
        dataset_id = self.dataset_combo.currentData()
        for dataset_view in self.dataset_views:
            if dataset_view.id == dataset_id:
                return dataset_view
        return self.dataset_views[0] if self.dataset_views else None

    @staticmethod
    def _set_combo_to_data(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.count():
            combo.setCurrentIndex(0)

    @staticmethod
    def _format_array_label(index, data_array):
        name = _get_name(data_array, f"array_{index}")
        unit = _get_unit(data_array, "")
        array_type = getattr(data_array, "type", "")

        details = [detail for detail in (array_type, unit) if detail]
        if details:
            return f"{index}: {name} ({', '.join(details)})"
        return f"{index}: {name}"

    def _unique_measurements(self):
        pattern = re.compile(r"^(?P<measurement>[A-Za-z_]+?)(?P<measurement_number>\d+)_(?P<group>\d+)$")
        names = []

        for data_array in self.arrays:
            name = _get_name(data_array, "")
            match = pattern.match(name)
            if match:
                names.append(_canonical_measurement_name(match.group("measurement")))
                continue
            group_name = _axis_group_name(data_array)
            if group_name:
                names.append(group_name)

        return sorted(set(names))

class graph_panel(QFrame):
    run_requested = Signal()
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
            dataset_views = self.graph.live_dataset_views
        else:
            dataset_views = measurement_dataset_views(measurement)

        if not dataset_views:
            QMessageBox.information(
                self,
                "No data loaded",
                "Load a measurement or wait for live data before editing axes.",
            )
            return

        if measurement is None:
            current_dataset_view = self.graph._dataset_view_from_views(dataset_views)
            arrays = dataset_arrays(current_dataset_view.dataset) if current_dataset_view is not None else []
        else:
            current_dataset_view = self.graph._dataset_view_for_selection(measurement)
            arrays = dataset_arrays(current_dataset_view.dataset) if current_dataset_view is not None else measurement_arrays(measurement)

        if not arrays:
            QMessageBox.warning(
                self,
                "No data arrays",
                "The current data does not contain any plottable arrays.",
            )
            return

        current_x = self.graph.x_index if isinstance(self.graph.x_index, int) else 0
        current_y = self.graph.y_index if isinstance(self.graph.y_index, int) else min(1, len(arrays) - 1)

        dialog = axis_selection_dialog(
            dataset_views,
            current_dataset_id=(
                self.graph.dataset_view_id
                or (current_dataset_view.id if current_dataset_view is not None else None)
            ),
            current_x=current_x,
            current_y=current_y,
            parent=self,
        )
        if dialog.exec():
            selection = dialog.selected_axes()
            if measurement is None:
                self.graph.plot_live_selection(selection)
            else:
                self.graph.plot_measurement(measurement, selection=selection)
