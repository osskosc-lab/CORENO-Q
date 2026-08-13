from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path

import numpy as np


os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[4]
PARENT_MODULE = ROOT / "experiments/correlon_lx/v0.2.3/src/experiment.py"
SPEC = importlib.util.spec_from_file_location("correlon_lx_v023", PARENT_MODULE)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

VERSION = "Correlon-LX-v0.3"
REPS = M.REPRESENTATIONS
CONDS = M.CONDITIONS
CHANNELS = ("linear", "nonlinear", "combined")
N = 100
ALPHA = 0.05
CALIBRATION_PATH = ROOT / "experiments/correlon_lx/v0.2.3/artifacts/experiment-run1/phase0r/calibration_maxima.csv"
PARENT_DECISION_PATH = ROOT / "experiments/correlon_lx/v0.2.3/artifacts/experiment-run1/final_decision.json"
STRESS_DECISION_PATH = ROOT / "experiments/correlon_lx/v0.2.3/artifacts/stress100/decision.json"
PREREG_PATH = ROOT / "experiments/correlon_lx/v0.3/phase1a_adapter/preregistration.md"
GATES_PATH = ROOT / "experiments/correlon_lx/v0.3/phase1a_adapter/gates.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def introducing_commit(path: Path) -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
    ).strip()


def preregistration_bundle_sha256() -> str:
    digest = hashlib.sha256()
    for path in (PREREG_PATH, GATES_PATH):
        rel = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(rel + b"\0" + path.read_bytes())
    return digest.hexdigest().upper()


def load_calibration() -> dict[str, dict[str, np.ndarray]]:
    rows = list(csv.DictReader(CALIBRATION_PATH.open(encoding="utf-8", newline="")))
    return {
        rep: {
            channel: np.asarray(
                [float(row[f"{channel}_max"]) for row in rows if row["representation"] == rep],
                dtype=np.float64,
            )
            for channel in CHANNELS
        }
        for rep in REPS
    }


def p_value(calibration: np.ndarray, score: float) -> float:
    ordered = np.sort(calibration)
    count_ge = len(ordered) - int(np.searchsorted(ordered, score, side="left"))
    return (1.0 + count_ge) / (len(ordered) + 1.0)


def score_preprocessed(data: np.ndarray, representation: str) -> dict[str, np.ndarray]:
    linear_max = np.zeros(len(M.PAIRS), dtype=np.float64)
    nonlinear_max = np.zeros(len(M.PAIRS), dtype=np.float64)
    for lag in M.LAGS:
        if lag >= 0:
            left_data, right_data = data[: 600 - lag], data[lag:]
        else:
            left_data, right_data = data[-lag:], data[: 600 + lag]
        left = left_data[:, M.PAIR_I].T
        right = right_data[:, M.PAIR_J].T
        linear_max = np.maximum(linear_max, M.linear_at_lag(left, right))
        nonlinear_max = np.maximum(
            nonlinear_max,
            M.member_hsic(left, right, "rff24", 0, representation, lag),
        )
    return {
        "linear": linear_max,
        "nonlinear": nonlinear_max,
        "combined": np.maximum(linear_max, nonlinear_max),
    }


def canonical_seed(condition: str, replicate: int) -> int:
    return M.seed64(
        f"{VERSION}|phase1a-paired|condition={condition}|replicate={replicate}"
    )


def canonical_decision(condition: str, target_p: float, maximum_p: float) -> bool:
    return (maximum_p if condition == "null" else target_p) <= ALPHA


def init_worker(calibration: dict[str, dict[str, np.ndarray]]) -> None:
    global CALIBRATION
    CALIBRATION = calibration


def task(item: tuple[str, str, int]) -> dict:
    representation, condition, replicate = item
    raw = M.generate(condition, canonical_seed(condition, replicate))
    adapted = M.transform(raw, representation)
    before = score_preprocessed(raw, representation)
    after = score_preprocessed(adapted, representation)
    row: dict[str, object] = {
        "representation": representation,
        "condition": condition,
        "replicate": replicate,
    }
    numeric_arrays = [*before.values(), *after.values()]
    row["finite"] = all(np.isfinite(value).all() for value in numeric_arrays)
    row["bounded"] = all(
        ((value >= -1e-12) & (value <= 1.0 + 1e-12)).all()
        for value in numeric_arrays
    )
    for channel in CHANNELS:
        before_target = float(before[channel][M.TARGET_INDEX])
        after_target = float(after[channel][M.TARGET_INDEX])
        before_max = float(before[channel].max())
        after_max = float(after[channel].max())
        before_target_p = p_value(CALIBRATION[representation][channel], before_target)
        after_target_p = p_value(CALIBRATION[representation][channel], after_target)
        before_max_p = p_value(CALIBRATION[representation][channel], before_max)
        after_max_p = p_value(CALIBRATION[representation][channel], after_max)
        before_decision = canonical_decision(condition, before_target_p, before_max_p)
        after_decision = canonical_decision(condition, after_target_p, after_max_p)
        row.update(
            {
                f"before_{channel}_target_score": before_target,
                f"after_{channel}_target_score": after_target,
                f"delta_{channel}_target_score": after_target - before_target,
                f"before_{channel}_max_score": before_max,
                f"after_{channel}_max_score": after_max,
                f"delta_{channel}_max_score": after_max - before_max,
                f"before_{channel}_target_p": before_target_p,
                f"after_{channel}_target_p": after_target_p,
                f"before_{channel}_max_p": before_max_p,
                f"after_{channel}_max_p": after_max_p,
                f"before_{channel}_decision": before_decision,
                f"after_{channel}_decision": after_decision,
                f"{channel}_decision_agree": before_decision == after_decision,
            }
        )
    row["after_combined_or_expected"] = bool(
        row["after_linear_decision"] or row["after_nonlinear_decision"]
    )
    row["after_combined_or_match"] = (
        row["after_combined_decision"] == row["after_combined_or_expected"]
    )
    return row


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rate(rows: list[dict], key: str) -> float:
    return sum(bool(row[key]) for row in rows) / len(rows)


def summarize(rows: list[dict], gates: dict) -> tuple[list[dict], list[dict], dict]:
    cells: list[dict] = []
    distortions: list[dict] = []
    for rep in REPS:
        for condition in CONDS:
            subset = [r for r in rows if r["representation"] == rep and r["condition"] == condition]
            cell: dict[str, object] = {
                "representation": rep,
                "condition": condition,
                "n": len(subset),
                "finite_failures": sum(not r["finite"] for r in subset),
                "range_failures": sum(not r["bounded"] for r in subset),
                "combined_or_mismatches": sum(not r["after_combined_or_match"] for r in subset),
            }
            for channel in CHANNELS:
                cell[f"before_{channel}_rate"] = rate(subset, f"before_{channel}_decision")
                cell[f"after_{channel}_rate"] = rate(subset, f"after_{channel}_decision")
                cell[f"{channel}_agreement"] = rate(subset, f"{channel}_decision_agree")
                for score_scope in ("target", "max"):
                    values = np.asarray(
                        [r[f"delta_{channel}_{score_scope}_score"] for r in subset],
                        dtype=np.float64,
                    )
                    distortions.append(
                        {
                            "representation": rep,
                            "condition": condition,
                            "channel": channel,
                            "score_scope": score_scope,
                            "n": len(values),
                            "mean_delta": float(values.mean()),
                            "median_delta": float(np.median(values)),
                            "mean_absolute_delta": float(np.abs(values).mean()),
                            "max_absolute_delta": float(np.abs(values).max()),
                        }
                    )
            cells.append(cell)

    by_rep = {rep: {(r["condition"]): r for r in cells if r["representation"] == rep} for rep in REPS}
    thresholds = gates["gates"]
    numeric_failures = sum(not r["finite"] for r in rows)
    range_failures = sum(not r["bounded"] for r in rows)
    a0 = numeric_failures <= thresholds["A0"]["nonfinite_failures_max"] and range_failures <= thresholds["A0"]["range_failures_max"]
    a1 = all(by_rep[rep]["null"]["after_combined_rate"] <= thresholds["A1"]["adapted_null_combined_fwer_max"] for rep in REPS)
    a2 = all(by_rep[rep]["direct_linear"]["after_linear_rate"] >= thresholds["A2"]["adapted_direct_linear_sensitivity_min"] for rep in REPS)
    a3 = all(
        by_rep[rep]["nonlinear_square"]["after_nonlinear_rate"] >= thresholds["A3"]["adapted_square_nonlinear_sensitivity_min"]
        and by_rep[rep]["nonlinear_tanh"]["after_nonlinear_rate"] >= thresholds["A3"]["adapted_tanh_nonlinear_sensitivity_min"]
        for rep in REPS
    )
    a4 = all(by_rep[rep]["nonlinear_square"]["after_linear_rate"] <= thresholds["A4"]["adapted_square_linear_fp_max"] for rep in REPS)
    agreement_values = [float(cell[f"{channel}_agreement"]) for cell in cells for channel in CHANNELS]
    a5 = min(agreement_values) >= thresholds["A5"]["paired_decision_agreement_min"]

    performance_cells = [
        ("null", "after_combined_rate"),
        ("direct_linear", "after_linear_rate"),
        ("nonlinear_square", "after_nonlinear_rate"),
        ("nonlinear_tanh", "after_nonlinear_rate"),
        ("nonlinear_square", "after_linear_rate"),
    ]
    spreads = {
        f"{condition}:{metric}": max(float(by_rep[rep][condition][metric]) for rep in REPS)
        - min(float(by_rep[rep][condition][metric]) for rep in REPS)
        for condition, metric in performance_cells
    }
    agreement_spreads = {
        f"{condition}:{channel}_agreement": max(float(by_rep[rep][condition][f"{channel}_agreement"]) for rep in REPS)
        - min(float(by_rep[rep][condition][f"{channel}_agreement"]) for rep in REPS)
        for condition in CONDS
        for channel in CHANNELS
    }
    spreads.update(agreement_spreads)
    a6 = max(spreads.values()) <= thresholds["A6"]["representation_rate_spread_max"]
    a7_mismatches = sum(not r["after_combined_or_match"] for r in rows)
    a7 = a7_mismatches <= thresholds["A7"]["adapted_decision_mismatches_max"]
    gate_results = {"A0": a0, "A1": a1, "A2": a2, "A3": a3, "A4": a4, "A5": a5, "A6": a6, "A7": a7}
    if all(gate_results.values()):
        decision = gates["pass_decision"]
    elif not a7:
        decision = gates["a7_failure_decision"]
    else:
        decision = gates["other_failure_decision"]
    result = {
        "version": VERSION,
        "phase": "1A Adapter Qualification",
        "decision": decision,
        "gate_results": gate_results,
        "eligible_for_phase1b": decision == "ADAPTER_QUALIFIED",
        "phase1b_entered": False,
        "datasets": len(rows),
        "paired_evaluations": len(rows),
        "numeric_failures": numeric_failures,
        "range_failures": range_failures,
        "minimum_paired_agreement": min(agreement_values),
        "maximum_representation_spread": max(spreads.values()),
        "representation_spreads": spreads,
        "combined_or_mismatches": a7_mismatches,
        "combined_semantics_case": "Case B: OR-style general detector",
        "claim_level_reached": "L1" if decision == "ADAPTER_QUALIFIED" else "L0",
        "claim_ceiling": "L3 shared-structure discovery; L4 causal-link claim prohibited",
        "qualified_theories": [],
        "discovery_candidates": [],
        "post_result_parameter_changes": [],
    }
    return cells, distortions, result


def verify_freeze(freeze: dict) -> None:
    parent = json.loads(PARENT_DECISION_PATH.read_text(encoding="utf-8"))
    stress = json.loads(STRESS_DECISION_PATH.read_text(encoding="utf-8"))
    checks = {
        "freeze_decision": freeze.get("decision") == "PHASE1A_REPOSITORY_FREEZE_COMPLETE",
        "eligible": freeze.get("eligible_for_phase1a") is True,
        "preregistration_bundle": freeze.get("preregistration_bundle_sha256") == preregistration_bundle_sha256(),
        "calibration": freeze.get("parent_sha256", {}).get("calibration_maxima.csv") == sha256(CALIBRATION_PATH),
        "parent_decision_hash": freeze.get("parent_sha256", {}).get("final_decision.json") == sha256(PARENT_DECISION_PATH),
        "stress_decision_hash": freeze.get("parent_sha256", {}).get("stress_decision.json") == sha256(STRESS_DECISION_PATH),
        "parent_phase0r_pass": parent.get("decision") == "PHASE_0R_PASS",
        "stress_pass": stress.get("decision") == "STRESS_PASS",
    }
    if not all(checks.values()):
        raise RuntimeError(f"Phase 1A freeze verification failed: {checks}")


def run(freeze_path: Path, output: Path, workers: int) -> dict:
    started = time.time()
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    verify_freeze(freeze)
    gates = json.loads(GATES_PATH.read_text(encoding="utf-8"))
    calibration = load_calibration()
    tasks = [(rep, condition, replicate) for replicate in range(1, N + 1) for condition in CONDS for rep in REPS]
    if workers == 1:
        init_worker(calibration)
        rows = [task(item) for item in tasks]
    else:
        with mp.Pool(workers, initializer=init_worker, initargs=(calibration,)) as pool:
            rows = pool.map(task, tasks, chunksize=1)
    rows.sort(key=lambda r: (r["replicate"], r["condition"], r["representation"]))
    cells, distortions, result = summarize(rows, gates)
    result.update(
        {
            "source_commit": freeze["source_commit"],
            "freeze_commit": introducing_commit(freeze_path),
            "preregistration_bundle_sha256": preregistration_bundle_sha256(),
            "seed_namespace": "Correlon-LX-v0.3|phase1a-paired|condition|replicate",
            "calibration_source": CALIBRATION_PATH.relative_to(ROOT).as_posix(),
            "elapsed_seconds": time.time() - started,
        }
    )
    write_csv(output / "paired_runs.csv", rows)
    write_csv(output / "condition_summary.csv", cells)
    write_csv(output / "distortion_summary.csv", distortions)
    write_json(output / "decision.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(8, mp.cpu_count() or 1))
    args = parser.parse_args()
    result = run(args.freeze_decision.resolve(), args.output.resolve(), args.workers)
    return 0 if result["decision"] == "ADAPTER_QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
