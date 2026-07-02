
import asyncio
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot
import pypalmsens as ps

from aurora_methods import AuroraStepwiseMethod
from measurement_data import LogicalMeasurementRun, MeasurementSegment


class measurement_worker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, instrument, method):
        super().__init__()
        self.instrument = instrument
        self.method = method
        self.manager = None
        self.loop = None
        self.abort_requested = False
        self._state_lock = threading.Lock()

    @Slot()
    def run(self):
        try:
            measurement = asyncio.run(self._measure())
            self.finished.emit(measurement)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            with self._state_lock:
                self.manager = None
                self.loop = None

    async def _measure(self):
        async with await ps.connect_async(instrument=self.instrument) as manager:
            with self._state_lock:
                self.manager = manager
                self.loop = asyncio.get_running_loop()
                abort_requested = self.abort_requested

            if isinstance(self.method, AuroraStepwiseMethod):
                return await self._measure_aurora_stepwise(manager, self.method)

            manager.validate_method(self.method)

            if abort_requested:
                await manager.abort()
                raise RuntimeError("Measurement aborted")

            def on_data(data):
                self.progress.emit(data)

            return await manager.measure(self.method, callback=on_data)

    async def _measure_aurora_stepwise(self, manager, stepwise_method: AuroraStepwiseMethod):
        actions = stepwise_method.render_actions()
        if not actions:
            raise RuntimeError("Aurora package did not produce any executable steps.")

        run = LogicalMeasurementRun(stepwise_method.name)
        run_start = time.monotonic()

        def on_data(data):
            self.progress.emit(data)

        for action in actions:
            if self._abort_requested():
                await manager.abort()
                raise RuntimeError("Measurement aborted")

            if action.is_temperature:
                raise RuntimeError(
                    "Aurora temperature steps are planned for step-wise execution, "
                    "but the temperature chamber controller is not connected to this worker yet."
                )

            if not action.is_palmsens or action.methodscript is None:
                continue

            method = ps.MethodScript(script=action.methodscript)
            manager.validate_method(method)
            segment_offset_s = time.monotonic() - run_start
            measurement = await manager.measure(method, callback=on_data)
            run.add_segment(
                MeasurementSegment(
                    index=len(run.segments) + 1,
                    label=action.label,
                    source=measurement,
                    elapsed_offset_s=segment_offset_s,
                    source_step_index=action.source_step_index,
                    step_type=action.step_type,
                    execution_index=action.execution_index,
                )
            )

        if not run.segments:
            raise RuntimeError("Aurora step-wise execution completed without measurement data.")
        return run

    @Slot()
    def abort(self):
        with self._state_lock:
            self.abort_requested = True
            manager = self.manager
            loop = self.loop

        if manager is not None and loop is not None:
            asyncio.run_coroutine_threadsafe(manager.abort(), loop)

    def _abort_requested(self) -> bool:
        with self._state_lock:
            return self.abort_requested


def collect_params(form_layout, field_names):
    params = {}
    for field in field_names:
        widget = form_layout[field]
        params[field] = widget.text().strip()
    return params
