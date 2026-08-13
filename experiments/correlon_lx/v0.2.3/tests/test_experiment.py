from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "experiments/correlon_lx/v0.2.3/src/experiment.py"
SPEC = importlib.util.spec_from_file_location("correlon_v023_experiment", PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class ExperimentTests(unittest.TestCase):
    def test_seed_mapping_is_stable(self):
        self.assertEqual(M.seed64("Correlon-LX-v0.2.3|test"), 43911665692554595)

    def test_generator_is_deterministic(self):
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

    def test_conformal_formula_uses_greater_or_equal(self):
        calibration = np.array([1.0, 2.0, 3.0])
        self.assertEqual(M.conformal_p(calibration, 2.0), 0.75)
        np.testing.assert_array_equal(M.pair_p_values(calibration, np.array([2.0])), np.array([0.75]))

    def test_capacity_ladder_is_closed(self):
        self.assertEqual(M.CANDIDATE_ORDER, ("rff24", "rff64", "rff128", "ensemble4x32"))
        self.assertEqual(M.CANDIDATES["ensemble4x32"], (32, 32, 32, 32))

    def test_detector_keeps_channels_separate(self):
        raw = M.generate("nonlinear_square", 789)
        scores = M.score_candidates(raw, "R1", ("rff24",))["rff24"]
        self.assertEqual(set(scores), {"linear", "nonlinear", "combined"})
        for values in scores.values():
            self.assertEqual(values.shape, (15,))
            self.assertTrue(np.isfinite(values).all())
            self.assertTrue(((values >= 0.0) & (values <= 1.0 + 1e-12)).all())

    def test_preregistration_has_disjoint_partitions(self):
        prereg = json.loads(
            (ROOT / "specs/correlon_lx/v0.2.3/preregistration_v0.2.3.json").read_text(encoding="utf-8")
        )
        partitions = prereg["seed_mapping"]["partitions"]
        self.assertEqual(len(partitions), len(set(partitions)))
        self.assertTrue(prereg["seed_mapping"]["all_partitions_disjoint"])


if __name__ == "__main__":
    unittest.main()
