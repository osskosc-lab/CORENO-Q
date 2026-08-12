from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "experiments/correlon_lx/v0.2.2/src/external_manifest_freeze.py"
SPEC = importlib.util.spec_from_file_location("freeze", PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FreezeTests(unittest.TestCase):
    def test_manifest_payloads_and_bytes(self):
        spec = ROOT / "specs/correlon_lx/v0.2.2"
        entries, errors = M.parse_manifest(spec / "manifest.sha256")
        self.assertEqual(errors, [])
        self.assertEqual(set(entries), M.PAYLOADS)
        for name, expected in entries.items():
            self.assertEqual(M.digest(spec / name), expected)


if __name__ == "__main__":
    unittest.main()
