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

## Notes

The methods made in the Aurora method builder may contain non-Palmsens native steps, currently only being setting temperature. The core app keeps those as neutral external actions. The generic worker can accept an optional `external_step_executor`, but it does not import Arduino, serial, or chamber-specific code directly.

This keeps the normal PalmSens app portable while still leaving a hook for local lab hardware integration, such as a custom temperature chamber.

## Running
Install the project dependencies:

```powershell
pip install -e .
```

then run:

```powershell
python main.py
```
