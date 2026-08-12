from __future__ import annotations

import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "experiments/correlon_lx/v0.2.2/src/phase0r.py"
SPEC = importlib.util.spec_from_file_location("phase0r", PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Phase0RTests(unittest.TestCase):
    def test_seed_mapping_is_stable(self):
        self.assertEqual(M.seed64("Correlon-LX-v0.2.2|test"), 5540544716984888823)

    def test_generators_are_deterministic_and_shaped(self):
        first = M.generate("null", 123)
        second = M.generate("null", 123)
        self.assertEqual(first.shape, (600, 6))
        np.testing.assert_array_equal(first, second)

    def test_representations_are_finite(self):
        raw = M.generate("direct_linear", 456)
        for representation in M.REPRESENTATIONS:
            transformed = M.transform(raw, representation)
            self.assertEqual(transformed.shape, raw.shape)
            self.assertTrue(np.isfinite(transformed).all())

    def test_lag_detector_returns_all_pairs(self):
        raw = M.generate("nonlinear_square", 789)
        scores = M.pair_scores(M.transform(raw, "R1"), "R1")
        self.assertEqual(scores.shape, (15,))
        self.assertTrue(((scores >= 0.0) & (scores <= 1.0 + 1e-12)).all())

    def test_threshold_index(self):
        self.assertEqual(math.ceil(0.95 * (1000 - 1)) + 1, 951)


if __name__ == "__main__":
    unittest.main()
