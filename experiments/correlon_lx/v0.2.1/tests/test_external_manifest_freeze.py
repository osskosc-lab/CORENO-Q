from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "experiments/correlon_lx/v0.2.1/src/external_manifest_freeze.py"
SPEC = importlib.util.spec_from_file_location("external_manifest_freeze", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExternalManifestFreezeTests(unittest.TestCase):
    def test_manifest_has_exact_non_self_referential_payload_set(self):
        entries, errors = MODULE.parse_manifest(
            ROOT / "specs/correlon_lx/v0.2.1/manifest.sha256"
        )
        self.assertEqual(errors, [])
        self.assertEqual(set(entries), MODULE.EXPECTED_PAYLOADS)
        self.assertNotIn("manifest.sha256", entries)
        self.assertNotIn("preregistration.json", entries)

    def test_payload_hashes_match(self):
        spec = ROOT / "specs/correlon_lx/v0.2.1"
        entries, _ = MODULE.parse_manifest(spec / "manifest.sha256")
        for name, expected in entries.items():
            self.assertEqual(MODULE.sha256(spec / name), expected)

    def test_scientific_contract_and_integrity_envelope(self):
        result = MODULE.evaluate(ROOT, MODULE.git(ROOT, "rev-parse", "HEAD"))
        self.assertTrue(all(result["cross_file_contract"].values()))
        self.assertEqual(result["byte_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
