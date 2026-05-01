from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolBar,
    QDialog,
    QFormLayout,
    QComboBox,
    QDialogButtonBox,
    QMessageBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
import pyqtgraph as pg
import ps_helpers as pslib


class graph_widget(QWidget):
    def __init__(self):
        super().__init__()
        self.measurement = None
        self.x_index = None
        self.y_index = None

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

    def plot_measurement_from_session(self, session_path, measurement_index):
      measurements = pslib.load_session(session_path)
      if measurement_index < len(measurements):
        self.plot_measurement(measurement=measurements[measurement_index])
    
    def plot_measurement(self, measurement, x_index=0, y_index=1):
        self.measurement = measurement
        self.x_index = x_index
        self.y_index = y_index

        dataset = self.measurement.dataset
        x_array = dataset.arrays()[self.x_index]
        y_array = dataset.arrays()[self.y_index]

        self.plot_widget.clear()
        self.plot_widget.setLabel("bottom", f"{x_array.name}, {x_array.unit}")
        self.plot_widget.setLabel("left", f"{y_array.name}, {y_array.unit}")
        self.plot_widget.plot(x_array.to_numpy(), y_array.to_numpy())


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


class graph_panel(QWidget):
    run_requested = Signal() # Dessa två signaler kan användas senare i main fönstret för att intiera/stoppa measurement
    stop_requested = Signal()

    def __init__(self):
        super().__init__()

        self.graph = graph_widget()

        layout = QVBoxLayout(self)

        self.toolbar = QToolBar("Graph Utilities", self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.graph)

        self.run_action = QAction("Run", self)
        self.stop_action = QAction("Stop", self)
        self.axes_action = QAction("Edit Axes", self)

        self.toolbar.addAction(self.run_action)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.addAction(self.axes_action)

        self.run_action.triggered.connect(self.run_requested.emit)
        self.stop_action.triggered.connect(self.stop_requested.emit)
        self.axes_action.triggered.connect(self.edit_axes)

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
