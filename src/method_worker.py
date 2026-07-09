
import asyncio
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot
import pypalmsens as ps

from src.aurora_app.aurora_methods import AuroraStepwiseMethod
from src.measurement_data import LogicalMeasurementRun, MeasurementSegment, TemperatureSample
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
        last_chamber_temperature_c = None
        last_chamber_setpoint_c = None

        has_temperature_actions = any(action.is_temperature for action in actions)
        if has_temperature_actions:
            if self.temperature_settings is None:
                raise RuntimeError("This Aurora method contains temperature steps, but the chamber is not enabled.")

        if self.temperature_settings is not None:
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
                    status = await self._execute_temperature_action(temperature_controller, action)
                    last_chamber_temperature_c = status.temperature_c
                    last_chamber_setpoint_c = status.setpoint_c
                    continue

                if not action.is_palmsens or action.methodscript is None:
                    continue

                method = ps.MethodScript(script=action.methodscript)
                manager.validate_method(method)
                segment_offset_s = time.monotonic() - run_start
                segment_started_at = time.monotonic()
                temperature_samples = []
                poll_stop_event = None
                poll_task = None
                if temperature_controller is not None:
                    poll_stop_event = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._poll_temperature_during_measurement(
                            temperature_controller,
                            segment_started_at,
                            temperature_samples,
                            poll_stop_event,
                        )
                    )

                try:
                    measurement = await manager.measure(method, callback=on_data)
                finally:
                    if poll_stop_event is not None:
                        poll_stop_event.set()
                    if poll_task is not None:
                        await poll_task

                if temperature_samples:
                    last_chamber_temperature_c = temperature_samples[-1].temperature_c
                    last_chamber_setpoint_c = temperature_samples[-1].setpoint_c
                run.add_segment(
                    MeasurementSegment(
                        index=len(run.segments) + 1,
                        label=action.label,
                        source=measurement,
                        elapsed_offset_s=segment_offset_s,
                        source_step_index=action.source_step_index,
                        step_type=action.step_type,
                        execution_index=action.execution_index,
                        chamber_temperature_c=last_chamber_temperature_c,
                        chamber_setpoint_c=last_chamber_setpoint_c,
                        chamber_temperature_samples=tuple(temperature_samples),
                    )
                )
        finally:
            if temperature_controller is not None:
                temperature_controller.close()

        if not run.segments:
            raise RuntimeError("Aurora step-wise execution completed without measurement data.")
        return run

    # TODO: current architecture hardwires temperature chamber
    # solution: possibly switch to general implementation and non native steps as  modules
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
        return status

    async def _poll_temperature_during_measurement(
        self,
        temperature_controller,
        segment_started_at: float,
        samples: list[TemperatureSample],
        stop_event: asyncio.Event,
    ):
        while not stop_event.is_set():
            status = await asyncio.to_thread(self._request_temperature_status, temperature_controller)
            if status is not None:
                samples.append(
                    TemperatureSample(
                        elapsed_s=max(0.0, time.monotonic() - segment_started_at),
                        temperature_c=status.temperature_c,
                        setpoint_c=status.setpoint_c,
                    )
                )
                self.progress.emit(
                    TemperatureProgress(
                        target_c=status.setpoint_c,
                        temperature_c=status.temperature_c,
                        setpoint_c=status.setpoint_c,
                        stable_for_s=0.0,
                        message=f"Temperature {status.temperature_c:.2f} C, setpoint {status.setpoint_c:.2f} C",
                    )
                )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.temperature_settings.poll_interval_s)
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _request_temperature_status(temperature_controller):
        temperature_controller.request_temperature()
        return temperature_controller.read_status()

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
