Exit code: 0
Wall time: 0.9 seconds
Output:
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "experiments/correlon_lx/v0.2.3/src/experiment.py"
SPEC = importlib.util.spec_from_file_location("correlon_v023_experiment", MODULE_PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

REPS = M.REPRESENTATIONS
CONDS = M.CONDITIONS
N = 100


def p_value(calibration: np.ndarray, score: float) -> float:
    ordered = np.sort(calibration)
    return (1.0 + len(ordered) - int(np.searchsorted(ordered, score, side="left"))) / (len(ordered) + 1.0)


def load_calibration(path: Path) -> dict[str, dict[str, np.ndarray]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    out = {}
    for rep in REPS:
        subset = [r for r in rows if r["representation"] == rep]
        out[rep] = {
            channel: np.asarray([float(r[f"{channel}_max"]) for r in subset], dtype=np.float64)
            for channel in ("linear", "nonlinear", "combined")
        }
    return out


def task(item):
    rep, condition, iteration = item
    seed = M.seed64(f"{M.VERSION}|stress100|iteration={iteration}|representation={rep}|condition={condition}")
    raw = M.generate(condition, seed)
    scores = M.score_candidates(raw, rep, ("rff24",))["rff24"]
    # Fixed v0.2.3 confirmatory calibration; stress namespace is disjoint.
    cal = CAL[rep]
    p = {ch: p_value(cal[ch], float(scores[ch][M.TARGET_INDEX])) for ch in ("linear", "nonlinear", "combined")}
    combined_sig = p["combined"] <= 0.05
    nonlinear_sig = p["nonlinear"] <= 0.05
    linear_sig = p["linear"] <= 0.05
    finite = all(np.isfinite(v).all() for v in scores.values())
    bounded = all(((v >= 0.0) & (v <= 1.0 + 1e-12)).all() for v in scores.values())
    return {
        "iteration": iteration,
        "representation": rep,
        "condition": condition,
        "target_linear_p": p["linear"],
        "target_nonlinear_p": p["nonlinear"],
        "target_combined_p": p["combined"],
        "target_linear_significant": linear_sig,
        "target_nonlinear_significant": nonlinear_sig,
        "target_combined_significant": combined_sig,
        "finite": finite,
        "bounded": bounded,
    }


def init_worker(calibration):
    global CAL
    CAL = calibration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(8, mp.cpu_count() or 1))
    args = parser.parse_args()
    global CAL
    cal_path = ROOT / "experiments/correlon_lx/v0.2.3/artifacts/experiment-run1/phase0r/calibration_maxima.csv"
    CAL = load_calibration(cal_path)
    tasks = [(rep, condition, iteration) for iteration in range(1, N + 1) for condition in CONDS for rep in REPS]
    started = time.time()
    with mp.Pool(args.workers, initializer=init_worker, initargs=(CAL,)) as pool:
        rows = pool.map(task, tasks, chunksize=1)
    rows.sort(key=lambda r: (r["iteration"], r["condition"], r["representation"]))
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "runs.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = []
    for rep in REPS:
        for condition in CONDS:
            subset = [r for r in rows if r["representation"] == rep and r["condition"] == condition]
            summary.append({
                "representation": rep,
                "condition": condition,
                "n": len(subset),
                "combined_rate": sum(r["target_combined_significant"] for r in subset) / N,
                "nonlinear_rate": sum(r["target_nonlinear_significant"] for r in subset) / N,
                "linear_rate": sum(r["target_linear_significant"] for r in subset) / N,
                "finite_failures": sum(not r["finite"] for r in subset),
                "bounded_failures": sum(not r["bounded"] for r in subset),
            })
    with (args.output / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    result = {
        "version": M.VERSION,
        "test": "stress100",
        "decision": "STRESS_PASS" if all(r["finite_failures"] == 0 and r["bounded_failures"] == 0 for r in summary) else "STRESS_FAIL_NUMERIC",
        "iterations": N,
        "datasets": len(rows),
        "representations": list(REPS),
        "conditions": list(CONDS),
        "candidate": "rff24",
        "calibration_source": str(cal_path.relative_to(ROOT)).replace("\\", "/"),
        "seed_namespace": "Correlon-LX-v0.2.3|stress100|iteration|representation|condition",
        "elapsed_seconds": time.time() - started,
        "numeric_failures": sum(r["finite_failures"] + r["bounded_failures"] for r in summary),
        "scientific_status": "engineering_stress_only; does_not_replace_confirmatory_phase0r",
    }
    (args.output / "decision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "STRESS_PASS" else 2


if __name__ == "__main__":
    main()

