"""Ensure the Qt builder uses shared visual protocol definitions."""

from __future__ import annotations

import unittest

from palmsens_aurora_workflow import visual as shared_visual
from src.aurora_app import aurora_builder


class SharedBuilderIntegrationTests(unittest.TestCase):
    def test_builder_uses_shared_metadata_and_compiler(self):
        self.assertIs(aurora_builder.RECORD_FIELDS, shared_visual.RECORD_FIELDS)
        self.assertIs(aurora_builder.SAFETY_FIELDS, shared_visual.SAFETY_FIELDS)
        self.assertIs(aurora_builder.STEP_SPECS, shared_visual.STEP_SPECS)
        self.assertIs(
            aurora_builder.build_protocol_from_visual_data,
            shared_visual.build_protocol_from_visual_data,
        )


if __name__ == "__main__":
    unittest.main()

