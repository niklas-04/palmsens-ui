
import asyncio
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot
import pypalmsens as ps

from src.aurora_app.aurora_methods import AuroraStepwiseMethod
from src.measurement_data import LogicalMeasurementRun, MeasurementSegment
from src.temperature_chamber.temperature_controller import TemperatureController, TemperatureProgress


class measurement_worker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, instrument, method, temperature_settings=None):
        super().__init__()
        self.instrument = instrument
        self.method = method
        self.temperature_settings = temperature_settings
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
        temperature_controller = None

        if any(action.is_temperature for action in actions):
            if self.temperature_settings is None:
                raise RuntimeError("This Aurora method contains temperature steps, but the chamber is not enabled.")
            temperature_controller = TemperatureController(self.temperature_settings)
            temperature_controller.connect()

        def on_data(data):
            self.progress.emit(data)

        try:
            for action in actions:
                if self._abort_requested():
                    await manager.abort()
                    if temperature_controller is not None and self.temperature_settings.stop_on_abort:
                        temperature_controller.stop()
                    raise RuntimeError("Measurement aborted")

                if action.is_temperature:
                    await self._execute_temperature_action(temperature_controller, action)
                    continue

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
        finally:
            if temperature_controller is not None:
                temperature_controller.close()

        if not run.segments:
            raise RuntimeError("Aurora step-wise execution completed without measurement data.")
        return run

    async def _execute_temperature_action(self, temperature_controller, action):
        if temperature_controller is None:
            raise RuntimeError("Temperature chamber is not configured.")

        target_c = action.target_temperature_c
        if target_c is None:
            raise RuntimeError("Temperature step is missing a target temperature.")

        dwell_s = action.wait_after_s or 0.0
        self.progress.emit(
            TemperatureProgress(
                target_c=target_c,
                temperature_c=None,
                setpoint_c=None,
                stable_for_s=0.0,
                message=f"Setting chamber to {target_c:.2f} C",
            )
        )

        if action.ramp_rate_c_per_min is not None:
            temperature_controller.set_ramp_rate(action.ramp_rate_c_per_min)
        temperature_controller.start()
        temperature_controller.set_target(target_c)

        status = await asyncio.to_thread(
            temperature_controller.wait_until_stable,
            target_c,
            dwell_s,
            self._abort_requested,
            self.progress.emit,
        )
        self.progress.emit(
            TemperatureProgress(
                target_c=target_c,
                temperature_c=status.temperature_c,
                setpoint_c=status.setpoint_c,
                stable_for_s=dwell_s,
                message=f"Temperature stabilized at {status.temperature_c:.2f} C",
            )
        )

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
