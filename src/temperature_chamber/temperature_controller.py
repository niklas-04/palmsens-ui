# Communicates  with the arduino firmware #
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Callable

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None



_MODE_RE = re.compile(r"^\s*(?P<mode>HEATING|COOLING|ON TARGET)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TemperatureSettings:
    port: str | None = None
    baud_rate: int = 9600
    tolerance_c: float = 0.5
    poll_interval_s: float = 1.0 # check poll interval vs timeu
    timeout_s: float | None = None
    log_dir: str | None = None
    stop_on_abort: bool = True


@dataclass(frozen=True)
class TemperatureStatus:
    elapsed_s: float
    mode: str | None
    temperature_c: float
    setpoint_c: float
    active_setpoint_c: float | None
    feedforward: float | None
    integral: float | None
    pid: float | None
    pwm: int | None
    raw_line: str


@dataclass(frozen=True)
class TemperatureProgress:
    target_c: float
    temperature_c: float | None
    setpoint_c: float | None
    stable_for_s: float
    message: str


class TemperatureController:
    def __init__(self, settings: TemperatureSettings):
        self.settings = settings
        self.serial = None
        self.started_at = None
        self.log_path = None
        self._log_handle = None

    def connect(self):
        if serial is None:
            raise RuntimeError("pyserial is required for temperature chamber control.")

        if self.serial is not None:
            return

        port = self.settings.port or self.find_arduino_port()
        if not port:
            raise RuntimeError("Could not find an Arduino serial port for the temperature chamber.")

        self.serial = serial.Serial(
            port,
            self.settings.baud_rate,
            timeout=self.settings.poll_interval_s,
        )
        self.started_at = time.monotonic()
        self._open_log()
        time.sleep(2.0) # TODO: check sleep time
        self.serial.reset_input_buffer()
        self._log(f"Connected to {port} at {self.settings.baud_rate} baud")

    def close(self):
        if self.serial is not None:
            self.serial.close()
            self.serial = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def start(self):
        self._write("G\n")

    def stop(self):
        self._write("S\n")

    def set_ramp_rate(self, degc_per_min: float):
        self._write(f"R{degc_per_min:.2f}\n")

    def set_target(self, degc: float):
        self._write(f"P{degc:.2f}\n")

    def request_temperature(self):
        self._write("T\n")

    def read_status(self) -> TemperatureStatus | None:
        if self.serial is None:
            raise RuntimeError("Temperature controller is not connected.")

        raw = self.serial.readline()
        if not raw:
            return None

        line = raw.decode("utf-8", errors="ignore").strip()
        if not line:
            return None

        self._log(line)
        return self._parse_status(line)

    def wait_until_stable(
        self,
        target_c: float,
        dwell_s: float,
        abort_check: Callable[[], bool],
        progress_callback: Callable[[TemperatureProgress], None] | None = None,
    ) -> TemperatureStatus:
        started_at = time.monotonic()
        stable_since = None
        last_status = None

        while True:
            if abort_check():
                if self.settings.stop_on_abort:
                    self.stop()
                raise RuntimeError("Temperature step aborted.")

            elapsed = time.monotonic() - started_at
            if self.settings.timeout_s is not None and elapsed > self.settings.timeout_s:
                raise RuntimeError("Temperature step timed out.")

            self.request_temperature()
            status = self.read_status()
            if status is None:
                continue

            last_status = status
            error_c = abs(status.temperature_c - target_c)
            if error_c <= self.settings.tolerance_c:
                if stable_since is None:
                    stable_since = time.monotonic()
                stable_for_s = time.monotonic() - stable_since
            else:
                stable_since = None
                stable_for_s = 0.0

            if progress_callback is not None:
                progress_callback(
                    TemperatureProgress(
                        target_c=target_c,
                        temperature_c=status.temperature_c,
                        setpoint_c=status.setpoint_c,
                        stable_for_s=stable_for_s,
                        message=self._progress_message(status, target_c, stable_for_s, dwell_s),
                    )
                )

            if stable_since is not None and stable_for_s >= dwell_s:
                return status

            if last_status is None:
                raise RuntimeError("Temperature controller did not report status.")

    def _write(self, command: str):
        if self.serial is None:
            raise RuntimeError("Temperature controller is not connected.")
        self.serial.write(command.encode("ascii"))
        self._log(f"Sent command: {command.strip()}")

    def _parse_status(self, line: str) -> TemperatureStatus | None:
        temperature = self._field_float(line, "T")
        setpoint = self._field_float(line, "SP")
        if temperature is None or setpoint is None:
            return None

        mode_match = _MODE_RE.search(line)
        return TemperatureStatus(
            elapsed_s=self._elapsed_s(),
            mode=mode_match.group("mode").upper() if mode_match else None,
            temperature_c=temperature,
            setpoint_c=setpoint,
            active_setpoint_c=self._field_float(line, "ActiveSP"),
            feedforward=self._field_float(line, "FF"),
            integral=self._field_float(line, "I"),
            pid=self._field_float(line, "PID"),
            pwm=self._field_int(line, "PWM"),
            raw_line=line,
        )

    def _progress_message(
        self,
        status: TemperatureStatus,
        target_c: float,
        stable_for_s: float,
        dwell_s: float,
    ) -> str:
        mode = f"{status.mode} " if status.mode else ""
        return (
            f"{mode}{status.temperature_c:.2f}/{target_c:.2f} C "
            f"(stable {stable_for_s:.0f}/{dwell_s:.0f} s)"
        )

    def _open_log(self):
        if not self.settings.log_dir:
            return

        log_dir = Path(self.settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = log_dir / f"SetTempWatcher_{timestamp}.txt"
        self._log_handle = self.log_path.open("w", encoding="utf-8")

    def _log(self, message: str):
        if self._log_handle is None:
            return

        elapsed_s = self._elapsed_s()
        self._log_handle.write(f"{datetime.now():%H:%M:%S}  [+{elapsed_s:6.0f}s] {message}\n")
        self._log_handle.flush()

    def _elapsed_s(self) -> float:
        if self.started_at is None:
            return 0.0
        return time.monotonic() - self.started_at

    @staticmethod
    def _field_float(line: str, field: str) -> float | None:
        match = re.search(rf"\b{re.escape(field)}:(-?\d+(?:\.\d+)?)", line)
        return float(match.group(1)) if match else None

    @staticmethod
    def _field_int(line: str, field: str) -> int | None:
        match = re.search(rf"\b{re.escape(field)}:(-?\d+)", line)
        return int(match.group(1)) if match else None

    @staticmethod
    def find_arduino_port() -> str | None:
        if serial is None:
            return None

        for port in serial.tools.list_ports.comports():
            description = port.description or ""
            if any(token in description for token in ("Arduino", "CH340", "USB Serial")):
                return port.device
        return None
 
