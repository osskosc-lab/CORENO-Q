from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VERSION = "Correlon-LX-v0.2"
REQUIRED = {
    "README.md": "444B59DEB6E5578A98DF85C556F48CCB24A2265FBA38415B4DBE03A2707835E6",
    "specs/correlon_lx/v0.2/correlon_lx_v0.2_interface_freeze.json": "E6E638D24C3438F4189D82E1737B7EB58869A9FC8E326C927DF0ACD788231206",
    "specs/correlon_lx/v0.2/correlon_lx_v0.2_phase0_pilot_results.json": "D674818B922F924C92FE24482DBF7D2BE15C863BEA3C5BA5C6CC2831DBFEA5C0",
}
REQUIRED_DIRS = [
    "specs/correlon_lx/v0.2",
    "experiments/correlon_lx/v0.2/frozen",
    "experiments/correlon_lx/v0.2/src",
    "experiments/correlon_lx/v0.2/tests",
    "experiments/correlon_lx/v0.2/artifacts/cycle1-run0",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def evaluate(root: Path, source_commit: str | None = None) -> dict:
    observed = {}
    missing = []
    byte_mismatches = []
    for relative, expected in REQUIRED.items():
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        actual = sha256(path)
        observed[relative] = actual
        if actual != expected:
            byte_mismatches.append(
                {"path": relative, "expected": expected, "actual": actual}
            )

    missing_dirs = [d for d in REQUIRED_DIRS if not (root / d).is_dir()]
    parse_errors = []
    interface = None
    pilot = None
    try:
        interface = json.loads(
            (root / "specs/correlon_lx/v0.2/correlon_lx_v0.2_interface_freeze.json").read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:  # audit must record malformed source without repairing it
        parse_errors.append({"file": "interface_freeze", "error": str(exc)})
    try:
        pilot = json.loads(
            (root / "specs/correlon_lx/v0.2/correlon_lx_v0.2_phase0_pilot_results.json").read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        parse_errors.append({"file": "phase0_pilot_results", "error": str(exc)})

    consistency = {}
    claimed_hash = None
    interface_actual = observed.get(
        "specs/correlon_lx/v0.2/correlon_lx_v0.2_interface_freeze.json"
    )
    if interface and pilot:
        claimed_hash = str(interface.get("freeze_sha256", "")).upper()
        consistency = {
            "version": interface.get("version") == VERSION,
            "pilot_version": pilot.get("version") == "Correlon-LX-v0.2-Phase0",
            "rff_features": interface.get("detector", {}).get("rff_features")
            == pilot.get("rff_features")
            == 24,
            "lags": interface.get("detector", {}).get("pairwise_scan")
            == "max over lags -3..+3"
            and pilot.get("lags") == list(range(-3, 4)),
            "pilot_sample_length": pilot.get("T") == 600,
            "scientific_boundary": interface.get("scientific_role")
            == "cross-theory residual discovery service; candidate-edge generator only",
        }

    failed_gates = []
    if missing or missing_dirs:
        failed_gates.append("missing_required_source")
    if byte_mismatches:
        failed_gates.append("source_manifest_byte_mismatch")
    if parse_errors:
        failed_gates.append("source_parse_failure")
    if consistency and not all(consistency.values()):
        failed_gates.append("cross_file_inconsistency")
    if claimed_hash and interface_actual and claimed_hash != interface_actual:
        failed_gates.append("embedded_freeze_sha256_mismatch")

    if "missing_required_source" in failed_gates:
        decision = "STOP_MISSING_FROZEN_INPUT"
    elif "source_manifest_byte_mismatch" in failed_gates:
        decision = "STOP_SOURCE_BYTE_MISMATCH"
    elif "source_parse_failure" in failed_gates:
        decision = "STOP_SOURCE_PARSE_FAILURE"
    elif "cross_file_inconsistency" in failed_gates:
        decision = "STOP_FREEZE_INCONSISTENT"
    elif "embedded_freeze_sha256_mismatch" in failed_gates:
        decision = "STOP_FREEZE_HASH_MISMATCH"
    else:
        decision = "REPOSITORY_FREEZE_COMPLETE"

    preregistration_material = {
        "version": VERSION,
        "source_commit": source_commit,
        "source_sha256": observed,
        "detector": interface.get("detector") if interface else None,
        "gates": interface.get("gates") if interface else None,
        "phase0_threshold": pilot.get("combined_fwer_threshold") if pilot else None,
    }
    preregistration_hash = canonical_sha256(preregistration_material)
    eligible = decision == "REPOSITORY_FREEZE_COMPLETE"
    return {
        "version": VERSION,
        "cycle": "Cycle-0F-Repository-Freeze",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source_truth_commit": source_commit,
        "decision": decision,
        "eligible_for_cycle1": eligible,
        "required_files": list(REQUIRED),
        "observed_sha256": observed,
        "missing_files": missing,
        "missing_directories": missing_dirs,
        "byte_mismatches": byte_mismatches,
        "parse_errors": parse_errors,
        "cross_file_consistency": consistency,
        "embedded_freeze_sha256": claimed_hash,
        "interface_file_sha256": interface_actual,
        "failed_gates": failed_gates,
        "preregistration": {
            "status": "CANDIDATE_NOT_FROZEN" if not eligible else "FROZEN",
            "sha256": preregistration_hash,
            "material": preregistration_material,
        },
        "seed_namespace": None
        if not eligible
        else f"correlon-lx-v0.2-cycle1-run1-{preregistration_hash[:12].lower()}",
        "scientific_claim_boundary": "candidate-edge generator only",
        "next_action": (
            "Provide the hash derivation rule or a byte-identical interface freeze whose embedded freeze_sha256 matches its declared integrity convention; start a new freeze revision without altering this audit record."
            if decision == "STOP_FREEZE_HASH_MISMATCH"
            else "Start Cycle1-run1 from PRECHECK using the reserved namespace."
        ),
    }


def write_outputs(root: Path, result: dict) -> None:
    output = root / "experiments/correlon_lx/v0.2/artifacts/cycle0f"
    output.mkdir(parents=True, exist_ok=True)
    (output / "decision.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "preregistration.json").write_text(
        json.dumps(result["preregistration"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "git_commit.txt").write_text(
        (result["source_truth_commit"] or "null") + "\n", encoding="utf-8"
    )
    (output / "python_version.txt").write_text(
        platform.python_version() + "\n", encoding="utf-8"
    )
    (output / "environment.txt").write_text(
        f"platform={platform.platform()}\npython={platform.python_version()}\n",
        encoding="utf-8",
    )
    (output / "seed_manifest.csv").write_text(
        "namespace,status\n"
        + (
            f"{result['seed_namespace']},RESERVED\n"
            if result["seed_namespace"]
            else ",NOT_RESERVED_CYCLE0F_FAILED\n"
        ),
        encoding="utf-8",
    )
    with (output / "sha256_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "sha256"])
        for path, digest in sorted(result["observed_sha256"].items()):
            writer.writerow([path, digest])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    source_commit = args.source_commit
    if source_commit is None:
        try:
            source_commit = git(root, "rev-parse", "HEAD")
        except Exception:
            source_commit = None
    result = evaluate(root, source_commit)
    if args.write:
        write_outputs(root, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["eligible_for_cycle1"] else 2


if __name__ == "__main__":
    sys.exit(main())

