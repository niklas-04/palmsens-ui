"""Ensure the desktop delegates Aurora workflow behaviour to the shared package."""

from __future__ import annotations

import unittest

import aurora_unicycler
import palmsens_aurora_workflow as shared

from src.aurora_app import aurora_methods as desktop


class SharedWorkflowEquivalenceTests(unittest.TestCase):
    def test_desktop_exports_shared_types_and_functions(self):
        self.assertIs(desktop.AuroraMethodPackage, shared.AuroraMethodPackage)
        self.assertIs(desktop.AuroraStepwiseMethod, shared.AuroraStepwiseMethod)
        self.assertIs(desktop.build_aurora_package, shared.build_aurora_package)
        self.assertIs(desktop.load_aurora_package, shared.load_aurora_package)
        self.assertIs(desktop.render_aurora_step_actions, shared.render_aurora_step_actions)

    def test_desktop_entrypoint_preserves_stepwise_behaviour(self):
        protocol = aurora_unicycler.CyclingProtocol.from_dict(
            {
                "record": {"time_s": 1},
                "method": [
                    {"step": "tag", "tag": "cycle"},
                    {"step": "wait", "until_time_s": 2},
                    {
                        "step": "temperature",
                        "until_temp_c": 25,
                        "wait_after_s": 30,
                        "ramp_rate": 0.35,
                    },
                    {"step": "constant_current", "current_mA": 1, "until_time_s": 3},
                    {"step": "loop", "loop_to": "cycle", "cycle_count": 2},
                ],
            }
        )
        settings = desktop.AuroraExportSettings(
            sample_name="test",
            capacity_mAh=None,
            device_key="emstat4_hr",
            channel=0,
            scan_step_voltage_v=None,
            eis_dc_potential_v=0,
            eis_dc_current_ma=0,
            additional_measurements=(),
        )
        desktop_actions = desktop.render_aurora_step_actions(protocol, settings)
        self.assertEqual(
            [action.source_step_index for action in desktop_actions],
            [2, 3, 4, 2, 3, 4],
        )
        self.assertEqual(
            [action.step_type for action in desktop_actions],
            [
                "wait",
                "temperature",
                "constant_current",
                "wait",
                "temperature",
                "constant_current",
            ],
        )


if __name__ == "__main__":
    unittest.main()
