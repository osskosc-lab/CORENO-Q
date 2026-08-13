import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "experiments/correlon_lx/v0.3/phase1a_adapter/run_phase1a.py"
SPEC = importlib.util.spec_from_file_location("phase1a", MODULE)
assert SPEC and SPEC.loader
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def test_preregistration_bundle_is_stable_shape():
    value = P.preregistration_bundle_sha256()
    assert len(value) == 64
    assert value == value.upper()


def test_score_preprocessed_is_finite_bounded_and_combined_max():
    raw = P.M.generate("nonlinear_square", P.M.seed64("phase1a-unit-test-not-experimental"))
    score = P.score_preprocessed(P.M.transform(raw, "R2"), "R2")
    assert all(np.isfinite(value).all() for value in score.values())
    assert all(((value >= 0) & (value <= 1 + 1e-12)).all() for value in score.values())
    np.testing.assert_allclose(score["combined"], np.maximum(score["linear"], score["nonlinear"]))


def test_canonical_decision_uses_familywise_null_and_target_positive():
    assert P.canonical_decision("null", target_p=0.9, maximum_p=0.04)
    assert not P.canonical_decision("null", target_p=0.01, maximum_p=0.06)
    assert P.canonical_decision("direct_linear", target_p=0.04, maximum_p=0.9)
    assert not P.canonical_decision("direct_linear", target_p=0.06, maximum_p=0.01)
