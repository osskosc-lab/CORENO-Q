from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import NormalDist

import numpy as np


VERSION = "Correlon-LX-v0.2.2"
VARIABLES = ("D", "R", "H", "P", "F", "V")
REPRESENTATIONS = ("R1", "R2", "R3", "R4")
CONDITIONS = ("null", "direct_linear", "common_pair", "nonlinear_square", "nonlinear_tanh", "global_common")
LAGS = (-3, -2, -1, 0, 1, 2, 3)
PAIRS = tuple((i, j) for i in range(6) for j in range(i + 1, 6))
PAIR_I = np.array([i for i, _ in PAIRS])
PAIR_J = np.array([j for _, j in PAIRS])
TARGET_INDEX = PAIRS.index((2, 5))
RFF_SCALE = math.sqrt(2.0 / 24.0)
NORMAL = NormalDist()


def seed64(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big", signed=False)


def dataset_seed(partition: str, representation: str, condition: str, replicate: int) -> int:
    return seed64(
        f"{VERSION}|phase0R|dataset|partition={partition}|representation={representation}|condition={condition}|replicate={replicate}"
    )


def generate(condition: str, seed: int) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    eps = rng.normal(0.0, 1.0, size=(800, 6))
    eta = rng.normal(0.0, 1.0, size=800)
    x = np.zeros((800, 6), dtype=np.float64)
    z_prev = 0.0
    sigma_sq = 1.0 / (1.0 - 0.45**2)
    sigma = math.sqrt(sigma_sq)
    for t in range(800):
        prev = x[t - 1] if t else np.zeros(6, dtype=np.float64)
        current = 0.45 * prev + eps[t]
        if condition == "direct_linear":
            current[5] = 0.45 * prev[5] + 0.65 * prev[2] + eps[t, 5]
        elif condition == "common_pair":
            current[2] += 0.70 * z_prev
            current[5] += 0.70 * z_prev
        elif condition == "nonlinear_square":
            q = (prev[2] ** 2 - sigma_sq) / (math.sqrt(2.0) * sigma_sq)
            current[5] = 0.45 * prev[5] + 0.75 * q + eps[t, 5]
        elif condition == "nonlinear_tanh":
            current[5] = 0.45 * prev[5] + 0.90 * math.tanh(prev[2] / sigma) + eps[t, 5]
        elif condition == "global_common":
            current += 0.55 * z_prev
        elif condition != "null":
            raise ValueError(f"Unknown condition: {condition}")
        x[t] = current
        if condition in {"common_pair", "global_common"}:
            z_prev = 0.60 * z_prev + eta[t]
    return x[200:].copy()


def zscore(values: np.ndarray) -> np.ndarray:
    centered = values - values.mean(axis=0)
    scale = np.sqrt(np.mean(centered * centered, axis=0))
    result = np.zeros_like(centered)
    valid = scale > 1e-12
    result[:, valid] = centered[:, valid] / scale[valid]
    return result


def average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    return ranks


_RANK_GAUSS_LOOKUP = np.array(
    [NORMAL.inv_cdf(min(max((rank - 0.5) / 600.0, 1e-6), 1.0 - 1e-6)) for rank in range(1, 601)],
    dtype=np.float64,
)


def transform(raw: np.ndarray, representation: str) -> np.ndarray:
    if representation == "R1":
        return zscore(raw)
    if representation == "R2":
        median = np.median(raw, axis=0)
        centered = raw - median
        scale = 1.482602218505602 * np.median(np.abs(centered), axis=0)
        result = np.zeros_like(raw)
        valid = scale > 1e-12
        result[:, valid] = centered[:, valid] / scale[valid]
        return result
    if representation == "R3":
        result = np.empty_like(raw)
        for column in range(raw.shape[1]):
            ranks = average_ranks(raw[:, column])
            if np.all(ranks == np.floor(ranks)):
                result[:, column] = _RANK_GAUSS_LOOKUP[ranks.astype(int) - 1]
            else:
                probabilities = np.clip((ranks - 0.5) / len(ranks), 1e-6, 1.0 - 1e-6)
                result[:, column] = np.fromiter(
                    (NORMAL.inv_cdf(float(p)) for p in probabilities), dtype=np.float64, count=len(ranks)
                )
        return result
    if representation == "R4":
        lower = np.quantile(raw, 0.01, axis=0, method="linear")
        upper = np.quantile(raw, 0.99, axis=0, method="linear")
        return zscore(np.clip(raw, lower, upper))
    raise ValueError(representation)


def rff_parameters(representation: str, lag: int):
    wx, bx, wy, by = [], [], [], []
    for i, j in PAIRS:
        pair = f"{VARIABLES[i]}-{VARIABLES[j]}"
        rows = []
        for side in ("X", "Y"):
            canonical = f"{VERSION}|phase0R|representation={representation}|pair={pair}|lag={lag}|side={side}"
            rng = np.random.Generator(np.random.PCG64(seed64(canonical)))
            rows.append((rng.normal(0.0, 1.0, 24), rng.uniform(0.0, 2.0 * math.pi, 24)))
        wx.append(rows[0][0]); bx.append(rows[0][1]); wy.append(rows[1][0]); by.append(rows[1][1])
    return tuple(np.asarray(value) for value in (wx, bx, wy, by))


_RFF_CACHE = {
    (representation, lag): rff_parameters(representation, lag)
    for representation in REPRESENTATIONS
    for lag in LAGS
}


def pair_scores(data: np.ndarray, representation: str) -> np.ndarray:
    maxima = np.zeros(15, dtype=np.float64)
    for lag in LAGS:
        if lag >= 0:
            left_data, right_data = data[: 600 - lag], data[lag:]
        else:
            left_data, right_data = data[-lag:], data[: 600 + lag]
        left = left_data[:, PAIR_I].T
        right = right_data[:, PAIR_J].T
        lc = left - left.mean(axis=1, keepdims=True)
        rc = right - right.mean(axis=1, keepdims=True)
        denominator = np.sqrt(np.sum(lc * lc, axis=1) * np.sum(rc * rc, axis=1))
        linear = np.divide(
            np.abs(np.sum(lc * rc, axis=1)), denominator, out=np.zeros(15), where=denominator > 1e-15
        )
        wx, bx, wy, by = _RFF_CACHE[(representation, lag)]
        phix = RFF_SCALE * np.cos(left[:, :, None] * wx[:, None, :] + bx[:, None, :])
        phiy = RFF_SCALE * np.cos(right[:, :, None] * wy[:, None, :] + by[:, None, :])
        phix -= phix.mean(axis=1, keepdims=True)
        phiy -= phiy.mean(axis=1, keepdims=True)
        scale = 1.0 / (left.shape[1] - 1)
        xt = np.transpose(phix, (0, 2, 1))
        yt = np.transpose(phiy, (0, 2, 1))
        cxy = (xt @ phiy) * scale
        cxx = (xt @ phix) * scale
        cyy = (yt @ phiy) * scale
        cross = np.sum(cxy * cxy, axis=(1, 2))
        auto_x = np.sum(cxx * cxx, axis=(1, 2))
        auto_y = np.sum(cyy * cyy, axis=(1, 2))
        hsic_den = np.sqrt(auto_x * auto_y)
        nonlinear = np.divide(cross, hsic_den, out=np.zeros(15), where=hsic_den > 1e-15)
        maxima = np.maximum(maxima, np.maximum(linear, nonlinear))
    return maxima


def block_permute(data: np.ndarray, replicate: int) -> np.ndarray:
    result = np.empty_like(data)
    for column, series in enumerate(VARIABLES):
        canonical = f"{VERSION}|phase0R|null|replicate={replicate}|series={series}"
        rng = np.random.Generator(np.random.PCG64(seed64(canonical)))
        blocks = data[:, column].reshape(30, 20)
        result[:, column] = blocks[rng.permutation(30)].reshape(600)
    return result


def calibration_task(task):
    representation, replicate = task
    raw = generate("null", dataset_seed("calibration", representation, "null", replicate))
    data = block_permute(transform(raw, representation), replicate)
    return representation, replicate, float(pair_scores(data, representation).max())


def evaluation_task(task):
    representation, condition, replicate, threshold = task
    raw = generate(condition, dataset_seed("evaluation", "SHARED", condition, replicate))
    scores = pair_scores(transform(raw, representation), representation)
    significant = scores > threshold
    target = float(scores[TARGET_INDEX])
    maximum = float(scores.max())
    top_count = int(np.count_nonzero(scores == maximum))
    return {
        "representation": representation,
        "condition": condition,
        "replicate": replicate,
        "max_score": maximum,
        "target_score": target,
        "target_significant": bool(significant[TARGET_INDEX]),
        "target_localized": bool(significant[TARGET_INDEX] and top_count == 1 and scores[TARGET_INDEX] == maximum),
        "significant_pairs": int(significant.sum()),
        "broad_global_mode": bool(significant.sum() >= 8),
    }


def map_tasks(function, tasks, workers):
    if workers == 1:
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, tasks, chunksize=4))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def run(root: Path, freeze_decision: Path, output: Path, workers: int, calibration_n=1000, evaluation_n=200):
    freeze = json.loads(freeze_decision.read_text(encoding="utf-8"))
    prereg_path = root / "specs/correlon_lx/v0.2.2/phase0r_preregistration_v0.2.2.json"
    prereg_sha = hashlib.sha256(prereg_path.read_bytes()).hexdigest().upper()
    if freeze.get("decision") != "REPOSITORY_FREEZE_COMPLETE" or not freeze.get("eligible_for_phase0r"):
        raise RuntimeError("Phase 0F-double-prime prerequisite failed")
    if freeze.get("preregistration_sha256") != prereg_sha:
        raise RuntimeError("Preregistration hash differs from frozen decision")
    started = time.time()
    calibration_rows = []
    thresholds = {}
    for representation in REPRESENTATIONS:
        tasks = [(representation, replicate) for replicate in range(1, calibration_n + 1)]
        values = map_tasks(calibration_task, tasks, workers)
        maxima = np.array([value[2] for value in values])
        ordered = np.sort(maxima)
        k = math.ceil(0.95 * (calibration_n - 1)) + 1
        threshold = float(ordered[k - 1])
        thresholds[representation] = threshold
        calibration_rows.extend(
            {"representation": rep, "replicate": replicate, "maximum_statistic": maximum}
            for rep, replicate, maximum in values
        )
        print(f"CALIBRATION_COMPLETE {representation} threshold={threshold:.12f}", flush=True)
    evaluation_rows = []
    for condition in CONDITIONS:
        tasks = [
            (representation, condition, replicate, thresholds[representation])
            for representation in REPRESENTATIONS
            for replicate in range(1, evaluation_n + 1)
        ]
        evaluation_rows.extend(map_tasks(evaluation_task, tasks, workers))
        print(f"EVALUATION_COMPLETE {condition}", flush=True)
    summary_rows = []
    gate_rows = []
    for representation in REPRESENTATIONS:
        subsets = {}
        for condition in CONDITIONS:
            subset = [r for r in evaluation_rows if r["representation"] == representation and r["condition"] == condition]
            subsets[condition] = subset
            summary_rows.append(
                {
                    "representation": representation,
                    "condition": condition,
                    "detection_rate": sum(r["target_significant"] for r in subset) / evaluation_n,
                    "localization_rate": sum(r["target_localized"] for r in subset) / evaluation_n,
                    "broad_global_mode_rate": sum(r["broad_global_mode"] for r in subset) / evaluation_n,
                    "median_max_score": float(np.median([r["max_score"] for r in subset])),
                    "median_significant_pairs": float(np.median([r["significant_pairs"] for r in subset])),
                }
            )
        metrics = {
            "fwer_null": sum(r["max_score"] > thresholds[representation] for r in subsets["null"]) / evaluation_n,
            "direct_tpr": sum(r["target_significant"] for r in subsets["direct_linear"]) / evaluation_n,
            "direct_localization": sum(r["target_localized"] for r in subsets["direct_linear"]) / evaluation_n,
            "common_pair_tpr": sum(r["target_significant"] for r in subsets["common_pair"]) / evaluation_n,
            "common_pair_localization": sum(r["target_localized"] for r in subsets["common_pair"]) / evaluation_n,
            "square_tpr": sum(r["target_significant"] for r in subsets["nonlinear_square"]) / evaluation_n,
            "square_localization": sum(r["target_localized"] for r in subsets["nonlinear_square"]) / evaluation_n,
            "tanh_tpr": sum(r["target_significant"] for r in subsets["nonlinear_tanh"]) / evaluation_n,
            "global_broad_mode_rate": sum(r["broad_global_mode"] for r in subsets["global_common"]) / evaluation_n,
        }
        checks = {
            "fwer_null_pass": metrics["fwer_null"] <= 0.05,
            "direct_tpr_pass": metrics["direct_tpr"] >= 0.80,
            "direct_localization_pass": metrics["direct_localization"] >= 0.80,
            "common_pair_tpr_pass": metrics["common_pair_tpr"] >= 0.80,
            "common_pair_localization_pass": metrics["common_pair_localization"] >= 0.80,
            "square_tpr_pass": metrics["square_tpr"] >= 0.80,
            "square_localization_pass": metrics["square_localization"] >= 0.80,
            "tanh_tpr_pass": metrics["tanh_tpr"] >= 0.80,
            "global_broad_mode_pass": metrics["global_broad_mode_rate"] >= 0.80,
        }
        gate_rows.append(
            {"representation": representation, "threshold": thresholds[representation], **metrics, **checks, "representation_pass": all(checks.values())}
        )
    passing = sum(row["representation_pass"] for row in gate_rows)
    decision = "PHASE_0R_PASS" if passing >= 3 else "STOP_REPRESENTATION_INSTABILITY"
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "null_distribution.csv", calibration_rows)
    write_csv(output / "evaluation_runs.csv", evaluation_rows)
    write_csv(output / "condition_summary.csv", summary_rows)
    write_csv(output / "representation_gate.csv", gate_rows)
    result = {
        "version": VERSION,
        "phase": "0R Representation Robustness",
        "decision": decision,
        "source_commit": freeze.get("source_commit"),
        "freeze_decision_sha256": hashlib.sha256(freeze_decision.read_bytes()).hexdigest().upper(),
        "preregistration_sha256": prereg_sha,
        "seed_namespace": freeze.get("seed_namespace"),
        "calibration_replicates_per_representation": calibration_n,
        "evaluation_replicates_per_condition": evaluation_n,
        "thresholds": thresholds,
        "passing_representations": passing,
        "representation_results": gate_rows,
        "elapsed_seconds": time.time() - started,
        "post_result_parameter_changes": [],
        "scientific_claim_boundary": "candidate-edge generator only",
        "next_action": "Phase 1A Adapter Qualification" if decision == "PHASE_0R_PASS" else "End v0.2.2; any change requires fresh v0.2.3 revision",
    }
    (output / "decision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze-decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.benchmark:
        start = time.time()
        raw = generate("nonlinear_square", dataset_seed("evaluation", "SHARED", "nonlinear_square", 1))
        scores = pair_scores(transform(raw, "R1"), "R1")
        print(json.dumps({"seconds": time.time() - start, "max": float(scores.max()), "target": float(scores[TARGET_INDEX])}, indent=2))
        return 0
    result = run(root, args.freeze_decision.resolve(), args.output.resolve(), args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "PHASE_0R_PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
