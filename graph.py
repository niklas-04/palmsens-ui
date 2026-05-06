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


class graph_widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("graphWidget")
        self.measurement = None
        self.x_index = None
        self.y_index = None
        self.live_curve = None

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

    def plot_measurement(self, measurement, x_index=0, y_index=1):
        self.measurement = measurement
        self.x_index = x_index
        self.y_index = y_index

        dataset = self.measurement.dataset
        x_array = dataset.arrays()[self.x_index]
        y_array = dataset.arrays()[self.y_index]

        self._plot_arrays(x_array, y_array)

    def plot_live_data(self, callback_data):
        self.measurement = None
        self.x_index = 0
        self.y_index = 1
        self._plot_arrays(callback_data.x_array, callback_data.y_array)

    def _plot_arrays(self, x_array, y_array):
        x_values = x_array.to_numpy()
        y_values = y_array.to_numpy()

        self.plot_widget.setLabel("bottom", f"{x_array.name}, {x_array.unit}")
        self.plot_widget.setLabel("left", f"{y_array.name}, {y_array.unit}")
        pen = pg.mkPen(color="#2f6f9f", width=2)

        if self.live_curve is None:
            self.plot_widget.clear()
            self.live_curve = self.plot_widget.plot(x_values, y_values, pen=pen)
            return

        self.live_curve.setData(x_values, y_values)


class axis_selection_dialog(QDialog):
    def __init__(self, arrays, current_x=0, current_y=1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Axes")

        layout = QFormLayout(self)
        self.x_combo = QComboBox(self)
        self.y_combo = QComboBox(self)

        for index, data_array in enumerate(arrays):
            label = self._format_array_label(index, data_array)
            self.x_combo.addItem(label, index)
            self.y_combo.addItem(label, index)

        self.x_combo.setCurrentIndex(current_x)
        self.y_combo.setCurrentIndex(current_y)

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
        return self.x_combo.currentData(), self.y_combo.currentData()

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
    remove_requested = Signal()

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
        self.axes_action = QAction("Edit Axes", self)
        self.remove_action = QAction("Remove", self)

        self.toolbar.addAction(self.run_action)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.addAction(self.axes_action)
        self.toolbar.addAction(self.remove_action)

        self.run_action.triggered.connect(self.run_requested.emit)
        self.stop_action.triggered.connect(self.stop_requested.emit)
        self.axes_action.triggered.connect(self.edit_axes)
        self.remove_action.triggered.connect(self.remove_requested.emit)
        self.set_running(False)

    def set_running(self, is_running: bool):
        self.run_action.setEnabled(not is_running)
        self.stop_action.setEnabled(is_running)
        self.remove_action.setEnabled(not is_running)

    def set_status_text(self, status: str | None = None):
        if status:
            self.title_label.setText(f"{self.base_title} [{status}]")
        else:
            self.title_label.setText(self.base_title)

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
        current_y = self.graph.y_index if self.graph.y_index is not None else min(1, len(arrays) - 1) # Om datasetet endast innehåller en mätdata

        dialog = axis_selection_dialog(arrays, current_x=current_x, current_y=current_y, parent=self)
        if dialog.exec():
            x_index, y_index = dialog.selected_axes()
            self.graph.plot_measurement(measurement, x_index=x_index, y_index=y_index)
