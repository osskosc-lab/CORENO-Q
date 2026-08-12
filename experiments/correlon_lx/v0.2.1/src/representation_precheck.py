from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_IMPLEMENTATION_FIELDS = [
    "synthetic_generators.null_equation_and_parameters",
    "synthetic_generators.direct_linear_equation_and_parameters",
    "synthetic_generators.common_pair_equation_and_parameters",
    "synthetic_generators.nonlinear_square_equation_and_parameters",
    "synthetic_generators.nonlinear_tanh_equation_and_parameters",
    "synthetic_generators.global_common_equation_and_parameters",
    "representations.zscore_ddof_and_zero_variance_policy",
    "representations.mad_scale_ties_and_zero_policy",
    "representations.rank_gaussian_formula_and_tie_policy",
    "representations.winsor_quantiles_and_zero_variance_policy",
    "nonlinear.kernel_family_and_bandwidth_rule",
    "nonlinear.rff_distribution_phase_rule_and_seed_mapping",
    "nonlinear.normalized_hsic_estimator_formula",
    "lags.boundary_and_effective_sample_rule",
    "nulls.resampling_algorithm_block_length_and_seed_mapping",
    "threshold.higher_order_statistic_index_rule",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def nested_get(value: dict, dotted: str):
    current = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate(root: Path, freeze_decision: Path) -> dict:
    freeze = json.loads(freeze_decision.read_text(encoding="utf-8"))
    prereg_path = root / "specs/correlon_lx/v0.2.1/preregistration.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    implementation = prereg.get("phase0r", {}).get("implementation", {})
    missing = [
        field for field in REQUIRED_IMPLEMENTATION_FIELDS if nested_get(implementation, field) is None
    ]
    freeze_ok = (
        freeze.get("decision") == "REPOSITORY_FREEZE_COMPLETE"
        and freeze.get("eligible_for_cycle1") is True
        and bool(freeze.get("seed_namespace"))
    )
    if not freeze_ok:
        decision = "STOP_FREEZE_PREREQUISITE"
    elif missing:
        decision = "STOP_REPRESENTATION_SPEC_INCOMPLETE"
    else:
        decision = "READY_FOR_REPRESENTATION_EXECUTION"
    return {
        "version": "Correlon-LX-v0.2.1",
        "phase": "0R Representation Robustness PRECHECK",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "freeze_decision_sha256": sha256(freeze_decision),
        "preregistration_sha256": sha256(prereg_path),
        "seed_namespace": freeze.get("seed_namespace") if freeze_ok else None,
        "decision": decision,
        "data_generated": False,
        "null_resamples_executed": 0,
        "evaluation_replicates_executed": 0,
        "missing_frozen_implementation_fields": missing,
        "scientific_claim_boundary": "candidate-edge generator only",
        "next_action": (
            "Publish a fresh preregistration revision that fixes every missing implementation detail before any synthetic seed is drawn."
            if missing
            else "Execute the frozen Phase 0R implementation."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze-decision", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.root.resolve(), args.freeze_decision.resolve())
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["decision"] == "READY_FOR_REPRESENTATION_EXECUTION" else 2


if __name__ == "__main__":
    sys.exit(main())
