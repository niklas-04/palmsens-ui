# PalmSens UI

Small PySide6 desktop app for running PalmSens measurements, plotting live data, and exporting results to Battery Data Format-style CSV files.

This project mainly builds upon three seperate related works:
- PyPalmSens (https://github.com/PalmSens/PalmSens_SDK/releases)
- Aurora Unicycler (https://github.com/EmpaEConversion/aurora-unicycler)
- Battery Data Format (https://github.com/battery-data-alliance/battery-data-format)

Note: The system introduces two new steps in measurements that aurora unicycler currently does not implement (Wait, Temperature), and therefore relies on a fork (https://github.com/Laswer5/aurora-unicycler).

Some of the functionality includes:

- Connecting to PalmSens instruments through PyPalmSens.
- Runs built-in PalmSens methods, pasted MethodSCRIPT, or imported Aurora method packages.
- Converts Aurora packages into step-by-step execution so each PalmSens-compatible step runs as its own MethodSCRIPT measurement.
- Groups those step measurements into one logical run for plotting and export.
- Handles time-series data and EIS data separately, while preserving shared step metadata such as step id, step type, and execution index.
- Exports measurement results based on Battery Data Format.

## Temperature Chamber

Temperature steps are non-Palsmens native steps and are handled directly by the app through `temperature_chamber/temperature_controller.py`. Enable the Arduino temperature chamber in the Aurora package run dialog, choose the serial settings, then run the method normally.

Leave the serial port blank to auto-detect Arduino USB serial devices, or enter a port such as `COM31`.

# Method defintion and packaging
Currently the aurora module exists as it own system. Defining a method creates a psmethod file which contains the following fields:

- format: Fixed identifier
- version: Used to avoid bugs with old psmethods being ran
- name: user-entered method name
- source_mode: One of three values depending on how the psmethod was created: aurora_visual, aurora_json, aurora_python
- source_payload: Editable source representation
- protocol_json: normalized Aurora Unicycler protocol produced by CyclingProtocol.to_dict() (see aurora unicycler)

## Running
Install the project dependencies:

```powershell
make setup
```

then run:

```powershell
make run
```

# TODOs
- The current implementation of the temperature chamber is hardwired based on the firmware run on local hardware. In a future implementation communication with external hardware could be abstracted through an API, which would allow for integration of external hardware and custom steps. This would mainly require refactoring the storage of measured data, to allow for "custom" data.
- Since the system makes use both Palmsens-native data and non-Palmsens native data (temperature) the handling of data can be messy. A solution would be further abstraction to make the system "blind" to where the data came from with the use of helpers.
- Live data currently only uses a live dataset for the current measurement. This makes the system unable to display past measurements during running. A solution would be to instead use unified datasets, even during live plotting.
