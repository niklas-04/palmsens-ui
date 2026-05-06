from dataclasses import dataclass
from pathlib import Path

import pypalmsens as ps


@dataclass(slots=True)
class mock_instrument:
    id: str
    interface: str
    name: str
    channel: int = -1

def create_mock_device(name: str, channel_count: int):
    channels = []

    for channel in range(1, channel_count + 1):
        if channel_count == 1:
            instrument = mock_instrument(
                id=name,
                interface="mock",
                name=name,
            )
        else:
            instrument = mock_instrument(
                id=f"{name}CH{channel:02d}", # formaterar kanalnamn på samma sätt som riktiga enheter
                interface="mock",
                name=name,
                channel=channel,
            )
        channels.append(instrument)

    return discovered_device(name, channels)



@dataclass(slots=True)
class discovered_device:
    name: str
    channels: list[ps.Instrument]

    def channel_count(self):
        return len(self.channels)


def _device_group_key(instrument: ps.Instrument):
    if instrument.channel > 0: # Om det enheten har flera kanaler
        return (instrument.interface, instrument.name)

    return (instrument.interface, instrument.id)

def _channel_sort_key(instrument: ps.Instrument):
    if instrument.channel > 0:
        return instrument.channel
    return 10**9 # stort tal bara för att sortera sist


def find_devices():
    return [create_mock_device("Mock PalmSens", 9)]

    instruments = ps.discover(ignore_errors=True)
    if not instruments:
        return []
    
    grouped_channels: dict[tuple[str, str], list[ps.Instrument]] = {}

    for instrument in instruments:
        key = _device_group_key(instrument)
        if key not in grouped_channels:
            grouped_channels[key] = []
        grouped_channels[key].append(instrument)

    devices: list[discovered_device] = []

    for channels in grouped_channels.values():
        channels.sort(key=_channel_sort_key)
        devices.append(discovered_device(channels[0].name, channels))

    devices.sort(key=lambda device: device.name.casefold()) # sortera efter namn
    return devices


def save_session(path: str | Path, session):
    ps.save_session_file(path, session)


def load_session(path: str | Path):
    return ps.load_session_file(path)
