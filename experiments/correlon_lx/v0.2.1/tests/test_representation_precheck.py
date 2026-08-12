from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "experiments/correlon_lx/v0.2.1/src/representation_precheck.py"
SPEC = importlib.util.spec_from_file_location("representation_precheck", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepresentationPrecheckTests(unittest.TestCase):
    def test_incomplete_implementation_stops_before_data_generation(self):
        freeze = {
            "decision": "REPOSITORY_FREEZE_COMPLETE",
            "eligible_for_cycle1": True,
            "seed_namespace": "test-fresh-namespace",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.json"
            path.write_text(json.dumps(freeze), encoding="utf-8")
            result = MODULE.evaluate(ROOT, path)
        self.assertEqual(result["decision"], "STOP_REPRESENTATION_SPEC_INCOMPLETE")
        self.assertFalse(result["data_generated"])
        self.assertEqual(result["null_resamples_executed"], 0)
        self.assertGreater(len(result["missing_frozen_implementation_fields"]), 0)


if __name__ == "__main__":
    unittest.main()
