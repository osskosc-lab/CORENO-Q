from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "experiments/correlon_lx/v0.2/src/repository_freeze.py"
SPEC = importlib.util.spec_from_file_location("repository_freeze", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepositoryFreezeTests(unittest.TestCase):
    def test_required_inputs_are_byte_exact(self):
        result = MODULE.evaluate(ROOT, "test-commit")
        self.assertEqual(result["missing_files"], [])
        self.assertEqual(result["byte_mismatches"], [])

    def test_cross_file_contract_is_consistent(self):
        result = MODULE.evaluate(ROOT, "test-commit")
        self.assertTrue(all(result["cross_file_consistency"].values()))

    def test_embedded_hash_mismatch_is_not_repaired(self):
        result = MODULE.evaluate(ROOT, "test-commit")
        self.assertNotEqual(
            result["embedded_freeze_sha256"], result["interface_file_sha256"]
        )
        self.assertEqual(result["decision"], "STOP_FREEZE_HASH_MISMATCH")
        self.assertFalse(result["eligible_for_cycle1"])
        self.assertIsNone(result["seed_namespace"])


if __name__ == "__main__":
    unittest.main()
