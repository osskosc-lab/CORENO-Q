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
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist

import numpy as np


VERSION = "Correlon-LX-v0.2.3"
VARIABLES = ("D", "R", "H", "P", "F", "V")
REPRESENTATIONS = ("R1", "R2", "R3", "R4")
CONDITIONS = (
    "null",
    "direct_linear",
    "common_pair",
    "nonlinear_square",
    "nonlinear_tanh",
    "global_common",
)
LAGS = (-3, -2, -1, 0, 1, 2, 3)
PAIRS = tuple((i, j) for i in range(6) for j in range(i + 1, 6))
PAIR_I = np.array([i for i, _ in PAIRS])
PAIR_J = np.array([j for _, j in PAIRS])
TARGET_INDEX = PAIRS.index((2, 5))
NORMAL = NormalDist()
CANDIDATES = {
    "rff24": (24,),
    "rff64": (64,),
    "rff128": (128,),
    "ensemble4x32": (32, 32, 32, 32),
}
CANDIDATE_ORDER = tuple(CANDIDATES)
EFFECTIVE_CAPACITY = {"rff24": 24, "rff64": 64, "rff128": 128, "ensemble4x32": 128}
ALPHA = 0.05


def seed64(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big", signed=False)


def dataset_seed(partition: str, representation: str, condition: str, replicate: int) -> int:
    canonical = (
        f"{VERSION}|dataset|partition={partition}|representation={representation}"
        f"|condition={condition}|replicate={replicate}"
    )
    return seed64(canonical)


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
            raise ValueError(f"unknown condition: {condition}")
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


@lru_cache(maxsize=None)
def rff_parameters(candidate: str, member: int, representation: str, lag: int):
    features = CANDIDATES[candidate][member]
    wx, bx, wy, by = [], [], [], []
    for i, j in PAIRS:
        pair = f"{VARIABLES[i]}-{VARIABLES[j]}"
        sides = []
        for side in ("X", "Y"):
            canonical = (
                f"{VERSION}|RFF|candidate={candidate}|member={member}|representation={representation}"
                f"|pair={pair}|lag={lag}|side={side}"
            )
            rng = np.random.Generator(np.random.PCG64(seed64(canonical)))
            sides.append((rng.normal(0.0, 1.0, features), rng.uniform(0.0, 2.0 * math.pi, features)))
        wx.append(sides[0][0]); bx.append(sides[0][1])
        wy.append(sides[1][0]); by.append(sides[1][1])
    return tuple(np.asarray(value) for value in (wx, bx, wy, by))


def linear_at_lag(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    lc = left - left.mean(axis=1, keepdims=True)
    rc = right - right.mean(axis=1, keepdims=True)
    denominator = np.sqrt(np.sum(lc * lc, axis=1) * np.sum(rc * rc, axis=1))
    return np.divide(
        np.abs(np.sum(lc * rc, axis=1)), denominator, out=np.zeros(15), where=denominator > 1e-15
    )


def member_hsic(
    left: np.ndarray, right: np.ndarray, candidate: str, member: int, representation: str, lag: int
) -> np.ndarray:
    features = CANDIDATES[candidate][member]
    scale_factor = math.sqrt(2.0 / features)
    wx, bx, wy, by = rff_parameters(candidate, member, representation, lag)
    phix = scale_factor * np.cos(left[:, :, None] * wx[:, None, :] + bx[:, None, :])
    phiy = scale_factor * np.cos(right[:, :, None] * wy[:, None, :] + by[:, None, :])
    phix -= phix.mean(axis=1, keepdims=True)
    phiy -= phiy.mean(axis=1, keepdims=True)
    covariance_scale = 1.0 / (left.shape[1] - 1)
    xt = np.transpose(phix, (0, 2, 1))
    yt = np.transpose(phiy, (0, 2, 1))
    cxy = (xt @ phiy) * covariance_scale
    cxx = (xt @ phix) * covariance_scale
    cyy = (yt @ phiy) * covariance_scale
    cross = np.sum(cxy * cxy, axis=(1, 2))
    auto_x = np.sum(cxx * cxx, axis=(1, 2))
    auto_y = np.sum(cyy * cyy, axis=(1, 2))
    denominator = np.sqrt(auto_x * auto_y)
    return np.divide(cross, denominator, out=np.zeros(15), where=denominator > 1e-15)


def score_candidates(raw: np.ndarray, representation: str, candidates: tuple[str, ...]) -> dict[str, dict[str, np.ndarray]]:
    data = transform(raw, representation)
    linear_max = np.zeros(15, dtype=np.float64)
    nonlinear_max = {candidate: np.zeros(15, dtype=np.float64) for candidate in candidates}
    for lag in LAGS:
        if lag >= 0:
            left_data, right_data = data[: 600 - lag], data[lag:]
        else:
            left_data, right_data = data[-lag:], data[: 600 + lag]
        left = left_data[:, PAIR_I].T
        right = right_data[:, PAIR_J].T
        linear_max = np.maximum(linear_max, linear_at_lag(left, right))
        for candidate in candidates:
            member_scores = [
                member_hsic(left, right, candidate, member, representation, lag)
                for member in range(len(CANDIDATES[candidate]))
            ]
            nonlinear_at_lag = np.mean(member_scores, axis=0)
            nonlinear_max[candidate] = np.maximum(nonlinear_max[candidate], nonlinear_at_lag)
    return {
        candidate: {
            "linear": linear_max.copy(),
            "nonlinear": nonlinear_max[candidate],
            "combined": np.maximum(linear_max, nonlinear_max[candidate]),
        }
        for candidate in candidates
    }


def map_tasks(function, tasks, workers: int, chunksize: int = 1):
    if workers == 1:
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, tasks, chunksize=chunksize))


def phase0c_task(replicate: int, partition: str = "phase0c-calibration"):
    raw = generate("null", dataset_seed(partition, "R1", "null", replicate))
    scores = score_candidates(raw, "R1", CANDIDATE_ORDER)
    return [
        {
            "candidate": candidate,
            "replicate": replicate,
            "linear_max": float(value["linear"].max()),
            "nonlinear_max": float(value["nonlinear"].max()),
            "combined_max": float(value["combined"].max()),
        }
        for candidate, value in scores.items()
    ]


def phase0c_calibration_task(replicate: int):
    return phase0c_task(replicate, "phase0c-calibration")


def phase0c_evaluation_task(replicate: int):
    return phase0c_task(replicate, "phase0c-evaluation")


def phase0n_task(task):
    condition, replicate = task
    raw = generate(condition, dataset_seed("phase0n-development", "R1", condition, replicate))
    scores = score_candidates(raw, "R1", CANDIDATE_ORDER)
    return condition, replicate, scores


def phase0r_calibration_task(task):
    representation, candidate, replicate = task
    raw = generate(
        "null", dataset_seed("phase0r-calibration", representation, "null", replicate)
    )
    value = score_candidates(raw, representation, (candidate,))[candidate]
    return {
        "representation": representation,
        "replicate": replicate,
        "linear_max": float(value["linear"].max()),
        "nonlinear_max": float(value["nonlinear"].max()),
        "combined_max": float(value["combined"].max()),
    }


def phase0r_evaluation_task(task):
    representation, candidate, condition, replicate = task
    raw = generate(
        condition, dataset_seed("phase0r-evaluation", "SHARED", condition, replicate)
    )
    value = score_candidates(raw, representation, (candidate,))[candidate]
    return representation, condition, replicate, value


def conformal_p(calibration: np.ndarray, score: float) -> float:
    ordered = np.sort(calibration)
    count_ge = len(ordered) - int(np.searchsorted(ordered, score, side="left"))
    return (1.0 + count_ge) / (len(ordered) + 1.0)


def pair_p_values(calibration: np.ndarray, scores: np.ndarray) -> np.ndarray:
    ordered = np.sort(calibration)
    positions = np.searchsorted(ordered, scores, side="left")
    return (1.0 + len(ordered) - positions) / (len(ordered) + 1.0)


def is_unique_target_max(scores: np.ndarray, target_significant: bool) -> bool:
    maximum = float(scores.max())
    return bool(target_significant and np.count_nonzero(scores == maximum) == 1 and scores[TARGET_INDEX] == maximum)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def calibration_arrays(rows: list[dict], candidate: str | None = None, representation: str | None = None):
    subset = [
        row for row in rows
        if (candidate is None or row.get("candidate") == candidate)
        and (representation is None or row.get("representation") == representation)
    ]
    return {
        channel: np.asarray([row[f"{channel}_max"] for row in subset], dtype=np.float64)
        for channel in ("linear", "nonlinear", "combined")
    }


def stopped_result(
    decision: str,
    freeze: dict,
    prereg_sha: str,
    phase_reached: str,
    selected_candidate: str | None = None,
    phase0c: dict | None = None,
    phase0n: dict | None = None,
) -> dict:
    return {
        "version": VERSION,
        "source_commit": freeze["source_commit"],
        "phase_reached": phase_reached,
        "decision": decision,
        "repository_freeze": freeze["decision"],
        "preregistration_sha256": prereg_sha,
        "seed_namespace": freeze["seed_namespace"],
        "selected_candidate": selected_candidate,
        "phase0c": phase0c,
        "phase0n": phase0n,
        "phase1a_entered": False,
        "qualified_theories": [],
        "discovery_candidates": [],
        "post_result_parameter_changes": [],
        "scientific_claim_boundary": "candidate-edge generator only",
        "next_action": f"End v0.2.3 with {decision}; any modification requires a fresh v0.2.4 revision",
    }


def run(root: Path, freeze_decision: Path, output: Path, workers: int) -> dict:
    started = time.time()
    freeze = json.loads(freeze_decision.read_text(encoding="utf-8"))
    prereg_path = root / "specs/correlon_lx/v0.2.3/preregistration_v0.2.3.json"
    prereg_sha = hashlib.sha256(prereg_path.read_bytes()).hexdigest().upper()
    if freeze.get("decision") != "REPOSITORY_FREEZE_COMPLETE" or not freeze.get("eligible_for_experiment"):
        raise RuntimeError("Cycle 0F prerequisite failed")
    if freeze.get("preregistration_sha256") != prereg_sha:
        raise RuntimeError("preregistration differs from frozen decision")

    phase0c_dir = output / "phase0c"
    phase0n_dir = output / "phase0n"
    phase0r_dir = output / "phase0r"

    calibration_nested = map_tasks(
        phase0c_calibration_task, range(1, 2000), workers, chunksize=2
    )
    phase0c_calibration = [row for group in calibration_nested for row in group]
    write_csv(phase0c_dir / "calibration_maxima.csv", phase0c_calibration)
    print("PHASE_0C_CALIBRATION_COMPLETE B=1999 candidates=4", flush=True)

    evaluation_nested = map_tasks(
        phase0c_evaluation_task, range(1, 1001), workers, chunksize=2
    )
    phase0c_evaluation = [row for group in evaluation_nested for row in group]
    phase0c_metrics = []
    phase0c_calibrations = {}
    for candidate in CANDIDATE_ORDER:
        arrays = calibration_arrays(phase0c_calibration, candidate=candidate)
        phase0c_calibrations[candidate] = arrays
        eval_rows = [row for row in phase0c_evaluation if row["candidate"] == candidate]
        combined_rejections = [
            conformal_p(arrays["combined"], row["combined_max"]) <= ALPHA for row in eval_rows
        ]
        nonlinear_rejections = [
            conformal_p(arrays["nonlinear"], row["nonlinear_max"]) <= ALPHA for row in eval_rows
        ]
        phase0c_metrics.append(
            {
                "candidate": candidate,
                "combined_fwer": sum(combined_rejections) / len(combined_rejections),
                "nonlinear_fwer": sum(nonlinear_rejections) / len(nonlinear_rejections),
                "combined_fwer_pass": sum(combined_rejections) / len(combined_rejections) <= 0.06,
            }
        )
    write_csv(phase0c_dir / "evaluation_maxima.csv", phase0c_evaluation)
    write_csv(phase0c_dir / "candidate_fwer.csv", phase0c_metrics)
    exchangeability = {
        "calibration_generator": "G_null",
        "evaluation_generator": "G_null",
        "calibration_namespace": "phase0c-calibration",
        "evaluation_namespace": "phase0c-evaluation",
        "namespaces_disjoint": True,
        "block_permutation_used": False,
        "primary_gate_pass": True,
    }
    baseline = next(row for row in phase0c_metrics if row["candidate"] == "rff24")
    phase0c_decision = (
        "PHASE_0C_PASS"
        if exchangeability["primary_gate_pass"] and baseline["combined_fwer_pass"]
        else "STOP_NULL_CALIBRATION_INVALID"
    )
    phase0c_result = {
        "phase": "0C Calibration Equivalence",
        "decision": phase0c_decision,
        "calibration_replicates": 1999,
        "fresh_null_evaluation_replicates": 1000,
        "exchangeability": exchangeability,
        "candidate_metrics": phase0c_metrics,
    }
    write_json(phase0c_dir / "decision.json", phase0c_result)
    print(f"PHASE_0C_COMPLETE decision={phase0c_decision}", flush=True)
    if phase0c_decision != "PHASE_0C_PASS":
        final = stopped_result(
            phase0c_decision, freeze, prereg_sha, "PHASE_0C_CALIBRATION_EQUIVALENCE", phase0c=phase0c_result
        )
        final["elapsed_seconds"] = time.time() - started
        write_json(output / "final_decision.json", final)
        return final

    development_tasks = [
        (condition, replicate)
        for condition in ("nonlinear_square", "null", "direct_linear")
        for replicate in range(1, 101)
    ]
    development_raw = map_tasks(phase0n_task, development_tasks, workers, chunksize=1)
    development_rows = []
    for condition, replicate, candidates in development_raw:
        for candidate, scores in candidates.items():
            calibration = phase0c_calibrations[candidate]
            target_p = {
                channel: conformal_p(calibration[channel], float(scores[channel][TARGET_INDEX]))
                for channel in ("linear", "nonlinear", "combined")
            }
            maximum_p = {
                channel: conformal_p(calibration[channel], float(scores[channel].max()))
                for channel in ("linear", "nonlinear", "combined")
            }
            development_rows.append(
                {
                    "candidate": candidate,
                    "condition": condition,
                    "replicate": replicate,
                    "target_linear": float(scores["linear"][TARGET_INDEX]),
                    "target_nonlinear": float(scores["nonlinear"][TARGET_INDEX]),
                    "target_combined": float(scores["combined"][TARGET_INDEX]),
                    "target_linear_p": target_p["linear"],
                    "target_nonlinear_p": target_p["nonlinear"],
                    "target_combined_p": target_p["combined"],
                    "linear_max_p": maximum_p["linear"],
                    "nonlinear_max_p": maximum_p["nonlinear"],
                    "combined_max_p": maximum_p["combined"],
                }
            )
    write_csv(phase0n_dir / "development_runs.csv", development_rows)
    candidate_gates = []
    for candidate in CANDIDATE_ORDER:
        rows = [row for row in development_rows if row["candidate"] == candidate]
        square = [row for row in rows if row["condition"] == "nonlinear_square"]
        null = [row for row in rows if row["condition"] == "null"]
        direct = [row for row in rows if row["condition"] == "direct_linear"]
        metrics = {
            "square_nonlinear_tpr": sum(row["target_nonlinear_p"] <= ALPHA for row in square) / 100,
            "nonlinear_null_fpr": sum(row["nonlinear_max_p"] <= ALPHA for row in null) / 100,
            "direct_combined_tpr": sum(row["target_combined_p"] <= ALPHA for row in direct) / 100,
            "direct_linear_tpr": sum(row["target_linear_p"] <= ALPHA for row in direct) / 100,
        }
        phase0c_gate = next(row for row in phase0c_metrics if row["candidate"] == candidate)["combined_fwer_pass"]
        checks = {
            "phase0c_fwer_pass": phase0c_gate,
            "square_nonlinear_tpr_pass": metrics["square_nonlinear_tpr"] >= 0.90,
            "nonlinear_null_fpr_pass": metrics["nonlinear_null_fpr"] <= 0.05,
            "direct_combined_tpr_pass": metrics["direct_combined_tpr"] >= 0.90,
            "direct_linear_tpr_pass": metrics["direct_linear_tpr"] >= 0.80,
        }
        candidate_gates.append(
            {
                "candidate": candidate,
                "effective_capacity": EFFECTIVE_CAPACITY[candidate],
                **metrics,
                **checks,
                "candidate_pass": all(checks.values()),
            }
        )
    write_csv(phase0n_dir / "candidate_gate.csv", candidate_gates)
    eligible = [row for row in candidate_gates if row["candidate_pass"]]
    selected = None
    if eligible:
        selected = min(
            eligible,
            key=lambda row: (row["effective_capacity"], CANDIDATE_ORDER.index(row["candidate"])),
        )["candidate"]
    phase0n_decision = "PHASE_0N_PASS" if selected else "STOP_NONLINEAR_DETECTOR_INADEQUATE"
    phase0n_result = {
        "phase": "0N Nonlinear Detector Qualification",
        "decision": phase0n_decision,
        "selected_candidate": selected,
        "selection_rule": "lowest effective capacity, then preregistered tie order",
        "candidate_results": candidate_gates,
    }
    write_json(phase0n_dir / "decision.json", phase0n_result)
    print(f"PHASE_0N_COMPLETE decision={phase0n_decision} selected={selected}", flush=True)
    if not selected:
        final = stopped_result(
            phase0n_decision,
            freeze,
            prereg_sha,
            "PHASE_0N_NONLINEAR_DETECTOR_QUALIFICATION",
            phase0c=phase0c_result,
            phase0n=phase0n_result,
        )
        final["elapsed_seconds"] = time.time() - started
        write_json(output / "final_decision.json", final)
        return final

    calibration_tasks = [
        (representation, selected, replicate)
        for representation in REPRESENTATIONS
        for replicate in range(1, 2000)
    ]
    phase0r_calibration = map_tasks(phase0r_calibration_task, calibration_tasks, workers, chunksize=2)
    write_csv(phase0r_dir / "calibration_maxima.csv", phase0r_calibration)
    print(f"PHASE_0R_CALIBRATION_COMPLETE selected={selected}", flush=True)
    confirmatory_calibrations = {
        representation: calibration_arrays(phase0r_calibration, representation=representation)
        for representation in REPRESENTATIONS
    }

    evaluation_tasks = [
        (representation, selected, condition, replicate)
        for condition in CONDITIONS
        for representation in REPRESENTATIONS
        for replicate in range(1, 201)
    ]
    phase0r_raw = map_tasks(phase0r_evaluation_task, evaluation_tasks, workers, chunksize=1)
    phase0r_rows = []
    for representation, condition, replicate, scores in phase0r_raw:
        calibration = confirmatory_calibrations[representation]
        p_values = {
            channel: pair_p_values(calibration[channel], scores[channel])
            for channel in ("linear", "nonlinear", "combined")
        }
        significant = {channel: p_values[channel] <= ALPHA for channel in p_values}
        phase0r_rows.append(
            {
                "representation": representation,
                "condition": condition,
                "replicate": replicate,
                "target_linear_score": float(scores["linear"][TARGET_INDEX]),
                "target_nonlinear_score": float(scores["nonlinear"][TARGET_INDEX]),
                "target_combined_score": float(scores["combined"][TARGET_INDEX]),
                "target_linear_p": float(p_values["linear"][TARGET_INDEX]),
                "target_nonlinear_p": float(p_values["nonlinear"][TARGET_INDEX]),
                "target_combined_p": float(p_values["combined"][TARGET_INDEX]),
                "linear_any": bool(significant["linear"].any()),
                "nonlinear_any": bool(significant["nonlinear"].any()),
                "combined_any": bool(significant["combined"].any()),
                "target_linear_localized": is_unique_target_max(
                    scores["linear"], bool(significant["linear"][TARGET_INDEX])
                ),
                "target_nonlinear_localized": is_unique_target_max(
                    scores["nonlinear"], bool(significant["nonlinear"][TARGET_INDEX])
                ),
                "target_combined_localized": is_unique_target_max(
                    scores["combined"], bool(significant["combined"][TARGET_INDEX])
                ),
                "combined_significant_pairs": int(significant["combined"].sum()),
                "broad_global_mode": bool(significant["combined"].sum() >= 8),
            }
        )
    write_csv(phase0r_dir / "evaluation_runs.csv", phase0r_rows)

    representation_gates = []
    condition_summary = []
    for representation in REPRESENTATIONS:
        subsets = {}
        for condition in CONDITIONS:
            subset = [
                row for row in phase0r_rows
                if row["representation"] == representation and row["condition"] == condition
            ]
            subsets[condition] = subset
            condition_summary.append(
                {
                    "representation": representation,
                    "condition": condition,
                    "linear_detection_rate": sum(row["target_linear_p"] <= ALPHA for row in subset) / 200,
                    "nonlinear_detection_rate": sum(row["target_nonlinear_p"] <= ALPHA for row in subset) / 200,
                    "combined_detection_rate": sum(row["target_combined_p"] <= ALPHA for row in subset) / 200,
                    "linear_localization_rate": sum(row["target_linear_localized"] for row in subset) / 200,
                    "nonlinear_localization_rate": sum(row["target_nonlinear_localized"] for row in subset) / 200,
                    "combined_localization_rate": sum(row["target_combined_localized"] for row in subset) / 200,
                    "broad_global_mode_rate": sum(row["broad_global_mode"] for row in subset) / 200,
                }
            )
        metrics = {
            "fwer": sum(row["combined_any"] for row in subsets["null"]) / 200,
            "direct_tpr": sum(row["target_combined_p"] <= ALPHA for row in subsets["direct_linear"]) / 200,
            "direct_localization": sum(row["target_combined_localized"] for row in subsets["direct_linear"]) / 200,
            "common_tpr": sum(row["target_combined_p"] <= ALPHA for row in subsets["common_pair"]) / 200,
            "common_localization": sum(row["target_combined_localized"] for row in subsets["common_pair"]) / 200,
            "square_nonlinear_tpr": sum(row["target_nonlinear_p"] <= ALPHA for row in subsets["nonlinear_square"]) / 200,
            "square_nonlinear_localization": sum(row["target_nonlinear_localized"] for row in subsets["nonlinear_square"]) / 200,
            "square_linear_tpr": sum(row["target_linear_p"] <= ALPHA for row in subsets["nonlinear_square"]) / 200,
            "tanh_combined_tpr_diagnostic": sum(row["target_combined_p"] <= ALPHA for row in subsets["nonlinear_tanh"]) / 200,
            "global_broad_mode_rate": sum(row["broad_global_mode"] for row in subsets["global_common"]) / 200,
        }
        checks = {
            "fwer_pass": metrics["fwer"] <= 0.06,
            "direct_tpr_pass": metrics["direct_tpr"] >= 0.80,
            "direct_localization_pass": metrics["direct_localization"] >= 0.80,
            "common_tpr_pass": metrics["common_tpr"] >= 0.80,
            "common_localization_pass": metrics["common_localization"] >= 0.80,
            "square_nonlinear_tpr_pass": metrics["square_nonlinear_tpr"] >= 0.80,
            "square_nonlinear_localization_pass": metrics["square_nonlinear_localization"] >= 0.80,
            "square_linear_control_pass": metrics["square_linear_tpr"] <= 0.20,
            "global_broad_mode_pass": metrics["global_broad_mode_rate"] >= 0.80,
        }
        representation_gates.append(
            {"representation": representation, **metrics, **checks, "representation_pass": all(checks.values())}
        )
    write_csv(phase0r_dir / "condition_summary.csv", condition_summary)
    write_csv(phase0r_dir / "representation_gate.csv", representation_gates)

    null_passing = sum(row["fwer_pass"] for row in representation_gates)
    nonlinear_passing = sum(
        row["square_nonlinear_tpr_pass"]
        and row["square_nonlinear_localization_pass"]
        and row["square_linear_control_pass"]
        for row in representation_gates
    )
    all_passing = sum(row["representation_pass"] for row in representation_gates)
    if null_passing < 3:
        decision = "STOP_NULL_CALIBRATION_INVALID"
    elif nonlinear_passing < 3:
        decision = "STOP_NONLINEAR_DETECTOR_INADEQUATE"
    elif all_passing < 3:
        decision = "STOP_REPRESENTATION_INSTABILITY"
    else:
        decision = "PHASE_0R_PASS"
    phase0r_result = {
        "phase": "0R Confirmatory Representation Robustness",
        "decision": decision,
        "selected_candidate": selected,
        "calibration_replicates_per_representation": 1999,
        "evaluation_replicates_per_condition": 200,
        "null_passing_representations": null_passing,
        "nonlinear_control_passing_representations": nonlinear_passing,
        "all_gate_passing_representations": all_passing,
        "representation_results": representation_gates,
    }
    write_json(phase0r_dir / "decision.json", phase0r_result)
    final = {
        "version": VERSION,
        "source_commit": freeze["source_commit"],
        "phase_reached": "PHASE_0R_CONFIRMATORY_REPRESENTATION_ROBUSTNESS",
        "decision": decision,
        "repository_freeze": freeze["decision"],
        "preregistration_sha256": prereg_sha,
        "seed_namespace": freeze["seed_namespace"],
        "selected_candidate": selected,
        "phase0c": phase0c_result,
        "phase0n": phase0n_result,
        "phase0r": phase0r_result,
        "phase1a_entered": decision == "PHASE_0R_PASS",
        "qualified_theories": [],
        "discovery_candidates": [],
        "post_result_parameter_changes": [],
        "scientific_claim_boundary": "candidate-edge generator only",
        "elapsed_seconds": time.time() - started,
        "next_action": (
            "Phase 1A Adapter Qualification"
            if decision == "PHASE_0R_PASS"
            else f"End v0.2.3 with {decision}; any modification requires a fresh v0.2.4 revision"
        ),
    }
    write_json(output / "final_decision.json", final)
    print(f"PHASE_0R_COMPLETE decision={decision}", flush=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze-decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if args.benchmark:
        started = time.time()
        raw = generate(
            "nonlinear_square",
            dataset_seed("benchmark-not-an-experimental-partition", "R1", "nonlinear_square", 1),
        )
        scores = score_candidates(raw, "R1", CANDIDATE_ORDER)
        print(
            json.dumps(
                {
                    "elapsed_seconds": time.time() - started,
                    "targets": {
                        candidate: {
                            channel: float(value[channel][TARGET_INDEX])
                            for channel in ("linear", "nonlinear", "combined")
                        }
                        for candidate, value in scores.items()
                    },
                },
                indent=2,
            )
        )
        return 0
    result = run(
        args.root.resolve(), args.freeze_decision.resolve(), args.output.resolve(), args.workers
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "PHASE_0R_PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
