# PalmSens UI

Small PySide6 desktop app for running PalmSens measurements, plotting live data, and exporting results to Battery Data Format-style CSV files.

This project mainly builds upon three seperate related works:
- PyPalmSens (https://github.com/PalmSens/PalmSens_SDK/releases)
- Aurora Unicycler (https://github.com/EmpaEConversion/aurora-unicycler)
- Battery Data Format (https://github.com/battery-data-alliance/battery-data-format)

Some of the functionality includes:

- Connecting to PalmSens instruments through PyPalmSens.
- Runs built-in PalmSens methods, pasted MethodSCRIPT, or imported Aurora method packages.
- Converts Aurora packages into step-by-step execution so each PalmSens-compatible step runs as its own MethodSCRIPT measurement.
- Groups those step measurements into one logical run for plotting and export.
- Handles time-series data and EIS data separately, while preserving shared step metadata such as step id, step type, and execution index.
- Exports measurement results based on Battery Data Format.

## Temperature Chamber

Temperature steps are non-Palsmens native steps and are handled directly by the app through `temperature_chamber/temperature_controller.py`. Enable the Arduino temperature chamber in the Aurora package run dialog, choose the serial settings, then run the method normally.

Leave the serial port blank to auto-detect Arduino/CH340 USB serial devices, or enter a port such as `COM31`.

## Running
Install the project dependencies:

```powershell
pip install -e .
```

then run:

```powershell
python main.py
```
Note: if using a local aurora package, put the library in the top-most directory.
