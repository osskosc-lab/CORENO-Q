from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "experiments/correlon_lx/v0.2.3/src/external_manifest_freeze.py"
SPEC = importlib.util.spec_from_file_location("correlon_v023_freeze", PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FreezeTests(unittest.TestCase):
    def test_manifest_is_external_and_exact(self):
        entries, errors = M.parse_manifest(ROOT / "specs/correlon_lx/v0.2.3/manifest.sha256")
        self.assertFalse(errors)
        self.assertEqual(set(entries), M.PAYLOADS)
        self.assertNotIn("manifest.sha256", entries)
        for name, expected in entries.items():
            self.assertEqual(M.digest(ROOT / "specs/correlon_lx/v0.2.3" / name), expected)

    def test_synthetic_code_has_no_block_permutation(self):
        source = (ROOT / "experiments/correlon_lx/v0.2.3/src/experiment.py").read_text(encoding="utf-8")
        self.assertNotIn("block_permute", source)


if __name__ == "__main__":
    unittest.main()
