setup:
	python -m venv .venv
	.venv/Scripts/python.exe -m pip install -e ./aurora-unicycler
	.venv/Scripts/python.exe -m pip install -e .

run:
	.venv/Scripts/python.exe -m src.main

builder:
	.venv/Scripts/python.exe -m src.aurora_app.aurora_method_builder_app

check:
	.venv/Scripts/python.exe -m compileall -q src
