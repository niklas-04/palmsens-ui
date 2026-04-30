from PySide6.QtWidgets import QWidget, QVBoxLayout
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
      measurement = pslib.load_session(session_path)[measurement_index]
      self.plot_measurement(measurement=measurement)
    
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
