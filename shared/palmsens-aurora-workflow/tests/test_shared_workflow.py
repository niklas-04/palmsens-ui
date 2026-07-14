"""Extraction and behavioural-equivalence tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import palmsens_aurora_workflow as shared


VISUAL_PROTOCOL = {
    "record": {"time_s": "1", "voltage_V": "0.01", "current_mA": ""},
    "safety": {
        "max_voltage_V": "4.3",
        "min_voltage_V": "2.5",
        "max_current_mA": "",
        "min_current_mA": "",
        "max_capacity_mAh": "",
        "delay_s": "",
    },
    "method": [
        {"step": "tag", "tag": "cycle"},
        {"step": "wait", "until_time_s": "2"},
        {
            "step": "temperature",
            "until_temp_c": "25",
            "wait_after_s": "30",
            "ramp_rate": "0.35",
        },
        {
            "step": "constant_current",
            "rate_C": "",
            "current_mA": "1",
            "until_time_s": "3",
            "until_voltage_V": "",
        },
        {
            "step": "loop",
            "loop_to_mode": "tag",
            "loop_to_tag": "cycle",
            "loop_to_step": "",
            "cycle_count": "2",
        },
    ],
}


class SharedWorkflowTests(unittest.TestCase):
    def test_visual_protocol_builds_version_two_package(self):
        package = shared.build_aurora_package(
            name="Shared package test",
            source_mode="aurora_visual",
            source_payload=VISUAL_PROTOCOL,
        )

        package_data = package.to_dict()
        self.assertEqual(package_data["format"], "palmsens_aurora_method_package")
        self.assertEqual(package_data["version"], 2)
        self.assertEqual(package_data["source_payload"], VISUAL_PROTOCOL)
        self.assertEqual(
            [step["step"] for step in package_data["protocol_json"]["method"]],
            ["tag", "wait", "temperature", "constant_current", "loop"],
        )

    def test_package_file_round_trip(self):
        package = shared.build_aurora_package(
            name="Round trip",
            source_mode="aurora_visual",
            source_payload=VISUAL_PROTOCOL,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = Path(temporary_directory) / "round-trip.psmethod"
            shared.save_aurora_package(package_path, package)
            loaded = shared.load_aurora_package(package_path)

        self.assertEqual(loaded.to_dict(), package.to_dict())

    def test_shared_planner_expands_workflow_actions(self):
        shared_package = shared.build_aurora_package(
            name="Planner test",
            source_mode="aurora_visual",
            source_payload=VISUAL_PROTOCOL,
        )
        shared_settings = shared.AuroraExportSettings(
            sample_name="test",
            capacity_mAh=None,
            device_key="emstat4_hr",
            channel=0,
            scan_step_voltage_v=None,
            eis_dc_potential_v=0,
            eis_dc_current_ma=0,
            additional_measurements=(),
        )
        shared_method = shared.build_aurora_stepwise_method(shared_package, shared_settings)
        shared_actions = shared_method.render_actions()

        self.assertEqual(
            [action.source_step_index for action in shared_actions],
            [2, 3, 4, 2, 3, 4],
        )
        self.assertEqual(
            [action.step_type for action in shared_actions],
            [
                "wait",
                "temperature",
                "constant_current",
                "wait",
                "temperature",
                "constant_current",
            ],
        )
        self.assertEqual(len([action for action in shared_actions if action.is_temperature]), 2)
        self.assertTrue(
            all(
                action.methodscript is not None
                for action in shared_actions
                if not action.is_temperature
            )
        )


if __name__ == "__main__":
    unittest.main()
