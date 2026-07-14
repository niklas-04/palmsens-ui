from __future__ import annotations

import csv
import math
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


TIME_COLUMN = "Test Time / s"
VOLTAGE_COLUMN = "Voltage / V"
CURRENT_COLUMN = "Current / A"
CYCLE_COLUMN = "Cycle Count / 1"
DISCHARGE_COLUMN = "Discharge_Capacity"
CHARGE_COLUMN = "Charge_Capacity"
CYCLE_COLUMNS = {CYCLE_COLUMN, DISCHARGE_COLUMN, CHARGE_COLUMN}
MAX_TIME_POINTS = 1_500


@dataclass
class PlotData:
    voltage: list[tuple[float, float]]
    current: list[tuple[float, float]]
    capacities: list[tuple[float, float | None, float | None]]


def as_number(value: Any) -> float | None:
    """Convert a cell to a finite float, returning None for invalid cells."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def downsample(points: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return points
    step = math.ceil(len(points) / limit)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def collect_plot_data(
    headers: set[str], rows: Iterable[Mapping[str, Any]]
) -> PlotData:
    missing = {TIME_COLUMN, VOLTAGE_COLUMN} - headers
    if missing:
        raise ValueError(f"Required column(s) missing: {', '.join(sorted(missing))}")

    has_current = CURRENT_COLUMN in headers
    has_cycles = CYCLE_COLUMNS.issubset(headers)
    voltage: list[tuple[float, float]] = []
    current: list[tuple[float, float]] = []
    capacity_by_cycle: dict[float, dict[str, float | None]] = {}

    for row in rows:
        time = as_number(row.get(TIME_COLUMN))
        volts = as_number(row.get(VOLTAGE_COLUMN))
        if time is not None and volts is not None:
            voltage.append((time, volts))

        if has_current and time is not None:
            amps = as_number(row.get(CURRENT_COLUMN))
            if amps is not None:
                current.append((time, amps * 1_000))

        if not has_cycles:
            continue

        cycle = as_number(row.get(CYCLE_COLUMN))
        if cycle is None:
            continue

        record = capacity_by_cycle.setdefault(
            cycle, {"discharge": None, "charge": None}
        )
        discharge = as_number(row.get(DISCHARGE_COLUMN))
        charge = as_number(row.get(CHARGE_COLUMN))
        if discharge is not None:
            previous = record["discharge"]
            record["discharge"] = discharge if previous is None else max(previous, discharge)
        if charge is not None:
            previous = record["charge"]
            record["charge"] = charge if previous is None else max(previous, charge)

    capacities = [
        (cycle, values["charge"], values["discharge"])
        for cycle, values in sorted(capacity_by_cycle.items())
    ]
    return PlotData(
        voltage=downsample(voltage, MAX_TIME_POINTS),
        current=downsample(current, MAX_TIME_POINTS),
        capacities=capacities,
    )


def load_csv(path: Path) -> PlotData:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        headers = {header.strip() for header in (reader.fieldnames or [])}
        return collect_plot_data(headers, reader)


def load_parquet(path: Path) -> PlotData:
    try:
        import polars as pl
    except ImportError as error:
        raise RuntimeError(
            "Parquet support requires Polars. Install battery_plotter_requirements.txt."
        ) from error

    schema = pl.read_parquet_schema(path)
    available = set(schema)
    wanted = [TIME_COLUMN, VOLTAGE_COLUMN]
    if CURRENT_COLUMN in available:
        wanted.append(CURRENT_COLUMN)
    if CYCLE_COLUMNS.issubset(available):
        wanted.extend([CYCLE_COLUMN, DISCHARGE_COLUMN, CHARGE_COLUMN])
    frame = pl.read_parquet(path, columns=wanted)
    return collect_plot_data(set(frame.columns), frame.iter_rows(named=True))


def load_data(path: Path) -> PlotData:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return load_parquet(path)
    return load_csv(path)


def padded_range(values: list[float]) -> tuple[float, float]:
    low, high = min(values), max(values)
    if math.isclose(low, high):
        padding = abs(low) * 0.05 or 1.0
    else:
        padding = (high - low) * 0.05
    return low - padding, high + padding


def add_series(
    chart: QChart,
    name: str,
    points: list[tuple[float, float]],
    color: str,
    show_points: bool = False,
) -> QLineSeries:
    series = QLineSeries()
    series.setName(name)
    series.replace([QPointF(x, y) for x, y in points])
    pen = QPen(QColor(color))
    pen.setWidthF(2.0)
    series.setPen(pen)
    series.setPointsVisible(show_points)
    chart.addSeries(series)
    return series


def make_axis(
    title: str,
    values: list[float],
    label_format: str = "%.4g",
    ticks: int = 7,
) -> QValueAxis:
    axis = QValueAxis()
    axis.setTitleText(title)
    axis.setLabelFormat(label_format)
    axis.setTickCount(ticks)
    low, high = padded_range(values)
    axis.setRange(low, high)
    return axis


def finish_chart(chart: QChart) -> QChartView:
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
    chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    return view


def time_chart(data: PlotData) -> QChartView:
    chart = QChart()
    chart.setTitle("Voltage and current against time")
    voltage = add_series(chart, "Voltage / V", data.voltage, "#1565ff")

    all_times = [x for x, _ in data.voltage] + [x for x, _ in data.current]
    time_axis = make_axis("Test time / s", all_times)
    voltage_axis = make_axis("Voltage / V", [y for _, y in data.voltage])
    chart.addAxis(time_axis, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(voltage_axis, Qt.AlignmentFlag.AlignLeft)
    voltage.attachAxis(time_axis)
    voltage.attachAxis(voltage_axis)

    if data.current:
        current = add_series(chart, "Current / mA", data.current, "#d62728")
        current_axis = make_axis("Current / mA", [y for _, y in data.current])
        chart.addAxis(current_axis, Qt.AlignmentFlag.AlignRight)
        current.attachAxis(time_axis)
        current.attachAxis(current_axis)

    return finish_chart(chart)


def capacity_chart(data: PlotData) -> QChartView:
    chart = QChart()
    chart.setTitle("Capacity against cycle")
    charge_points = [(cycle, value) for cycle, value, _ in data.capacities if value is not None]
    discharge_points = [
        (cycle, value) for cycle, _, value in data.capacities if value is not None
    ]
    charge = add_series(chart, "Charge capacity", charge_points, "#1565ff", True)
    discharge = add_series(
        chart, "Discharge capacity", discharge_points, "#159447", True
    )

    cycles = [cycle for cycle, _, _ in data.capacities]
    values = [value for _, value in charge_points + discharge_points]
    cycle_axis = make_axis("Cycle", cycles, "%.0f", min(10, max(2, len(cycles))))
    capacity_axis = make_axis("Capacity", values)
    chart.addAxis(cycle_axis, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(capacity_axis, Qt.AlignmentFlag.AlignLeft)
    for series in (charge, discharge):
        series.attachAxis(cycle_axis)
        series.attachAxis(capacity_axis)
    return finish_chart(chart)


def efficiency_chart(data: PlotData) -> QChartView | None:
    points = [
        (cycle, discharge / charge * 100)
        for cycle, charge, discharge in data.capacities
        if charge is not None and charge > 0 and discharge is not None
    ]
    if not points:
        return None

    chart = QChart()
    chart.setTitle("Coulombic efficiency against cycle")
    efficiency = add_series(chart, "Coulombic efficiency / %", points, "#9c169c", True)
    cycle_axis = make_axis(
        "Cycle", [x for x, _ in points], "%.0f", min(10, max(2, len(points)))
    )
    efficiency_axis = make_axis("Coulombic efficiency / %", [y for _, y in points], "%.1f")
    chart.addAxis(cycle_axis, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(efficiency_axis, Qt.AlignmentFlag.AlignLeft)
    efficiency.attachAxis(cycle_axis)
    efficiency.attachAxis(efficiency_axis)
    return finish_chart(chart)


class BatteryPlotter(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Battery Dataset Plotter")
        self.resize(1100, 760)
        self.setAcceptDrops(True)

        self.open_button = QPushButton("Open CSV or Parquet…")
        self.open_button.clicked.connect(self.open_file)
        self.status = QLabel("Open a battery dataset to begin.")
        self.tabs = QTabWidget()

        controls = QHBoxLayout()
        controls.addWidget(self.open_button)
        controls.addWidget(self.status, 1)
        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.tabs, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open battery dataset",
            str(Path.home() / "Downloads"),
            "Battery data (*.csv *.txt *.parquet *.pq);;All files (*)",
        )
        if filename:
            self.show_file(Path(filename))

    def show_file(self, path: Path) -> None:
        try:
            data = load_data(path)
            if not data.voltage:
                raise ValueError("No valid time and voltage rows were found.")
        except Exception as error:
            QMessageBox.critical(self, "Could not open dataset", str(error))
            return

        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()

        self.tabs.addTab(time_chart(data), "Time series")
        has_capacity_values = any(
            charge is not None or discharge is not None
            for _, charge, discharge in data.capacities
        )
        if has_capacity_values:
            self.tabs.addTab(capacity_chart(data), "Capacity by cycle")
            efficiency = efficiency_chart(data)
            if efficiency is not None:
                self.tabs.addTab(efficiency, "Coulombic efficiency")

        cycle_text = f", {len(data.capacities)} cycles" if data.capacities else ""
        self.status.setText(
            f"{path.name}: {len(data.voltage)} displayed time points{cycle_text}"
        )
        self.setWindowTitle(f"Battery Dataset Plotter — {path.name}")

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt method name
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt method name
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.show_file(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()


def main() -> int:
    app = QApplication(sys.argv)
    window = BatteryPlotter()
    window.show()
    if len(sys.argv) > 1:
        window.show_file(Path(sys.argv[1]).expanduser())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
