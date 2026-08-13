from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VERSION = "Correlon-LX-v0.2.3"
SPEC_REL = Path("specs/correlon_lx/v0.2.3")
PREREG_NAME = "preregistration_v0.2.3.json"
PAYLOADS = {"interface_freeze.json", "README.md", PREREG_NAME}
PATTERN = re.compile(r"^([0-9A-F]{64})  ([^/\\]+)$")
PROTOCOL_SHA = "A0329E539CCE2D3CB23BC021E1943C580443F66800AB2D44B7BC4E8B944ED6AB"
PARENT_FINAL_SHA = "92CADFA903D64CA71885F222E0976825A4C35E9DD02907FAD099E133EF9B8AED"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file():
        return entries, ["manifest_missing"]
    for index, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        match = PATTERN.fullmatch(line)
        if not match:
            errors.append(f"invalid_line_{index}")
            continue
        sha, name = match.groups()
        if name in entries:
            errors.append(f"duplicate:{name}")
        entries[name] = sha
    return entries, errors


def evaluate(root: Path, source_commit: str) -> dict:
    spec = root / SPEC_REL
    manifest = spec / "manifest.sha256"
    entries, manifest_errors = parse_manifest(manifest)
    if set(entries) != PAYLOADS:
        manifest_errors.append("payload_set_mismatch")
    if "manifest.sha256" in entries:
        manifest_errors.append("self_reference")
    observed = {name: digest(spec / name) for name in sorted(PAYLOADS) if (spec / name).is_file()}
    missing = sorted(PAYLOADS - set(observed))
    mismatches = [
        {"path": name, "expected": entries.get(name), "actual": actual}
        for name, actual in observed.items()
        if entries.get(name) != actual
    ]
    parse_errors = []
    objects = {}
    for name in ("interface_freeze.json", PREREG_NAME):
        try:
            objects[name] = json.loads((spec / name).read_text(encoding="utf-8"))
        except Exception as exc:
            parse_errors.append({"path": name, "error": str(exc)})
    interface = objects.get("interface_freeze.json", {})
    prereg = objects.get(PREREG_NAME, {})
    parent_interface = root / "specs/correlon_lx/v0.2.2/interface_freeze.json"
    parent_final = root / "experiments/correlon_lx/v0.2.2/artifacts/final_decision.json"
    experiment_source = root / "experiments/correlon_lx/v0.2.3/src/experiment.py"
    source_text = experiment_source.read_text(encoding="utf-8") if experiment_source.is_file() else ""
    contract = {
        "version": interface.get("version") == prereg.get("version") == VERSION,
        "external_manifest": interface.get("integrity", {}).get("scheme") == "external-manifest-sha256",
        "no_self_digest": interface.get("integrity", {}).get("self_referential_digest_fields") is False,
        "parent_interface_hash": parent_interface.is_file()
        and digest(parent_interface) == interface.get("revision_parent", {}).get("interface_sha256"),
        "parent_final_hash": parent_final.is_file()
        and digest(parent_final) == interface.get("revision_parent", {}).get("final_decision_sha256")
        == PARENT_FINAL_SHA,
        "parent_stop_preserved": interface.get("revision_parent", {}).get("decision")
        == "STOP_REPRESENTATION_INSTABILITY",
        "executable_status": prereg.get("status") == "EXECUTABLE_CALIBRATION_AND_NONLINEAR_FREEZE",
        "protocol_hash": prereg.get("protocol_source_sha256") == PROTOCOL_SHA,
        "calibration_b": prereg.get("conformal", {}).get("calibration_replicates") == 1999,
        "phase0c_n": prereg.get("phase0c", {}).get("fresh_null_evaluation_replicates") == 1000,
        "candidate_ladder": prereg.get("capacity_ladder", {}).get("candidates_in_tie_order")
        == ["rff24", "rff64", "rff128", "ensemble4x32"],
        "synthetic_permutation_prohibited": "block_permute" not in source_text,
        "scientific_boundary": prereg.get("scientific_claim_boundary") == "candidate-edge generator only",
    }
    commit_checks = {"exists": False, "head_matches": False, "tree_clean": False}
    try:
        subprocess.check_call(
            ["git", "-C", str(root), "cat-file", "-e", f"{source_commit}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        commit_checks["exists"] = True
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, encoding="utf-8"
        ).strip()
        commit_checks["head_matches"] = head == source_commit
        status = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True, encoding="utf-8"
        )
        commit_checks["tree_clean"] = not status.strip()
    except Exception:
        pass
    failed = []
    if missing:
        failed.append("F0_payload_missing")
    if manifest_errors or mismatches:
        failed.append("F1_manifest_or_byte_failure")
    if parse_errors:
        failed.append("F3_json_parse_failure")
    if not all(contract.values()):
        failed.append("F4_cross_file_contract_failure")
    if "self_reference" in manifest_errors:
        failed.append("F5_manifest_self_reference")
    if not all(commit_checks.values()):
        failed.append("F6_source_commit_failure")
    decision = "REPOSITORY_FREEZE_COMPLETE" if not failed else "STOP_FREEZE_GATE_FAILURE"
    prereg_sha = observed.get(PREREG_NAME)
    return {
        "version": VERSION,
        "phase": "Cycle 0F v0.2.3 Repository Freeze",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "decision": decision,
        "eligible_for_experiment": not failed,
        "seed_namespace": f"correlon-lx-v0.2.3-{prereg_sha[:12].lower()}" if not failed else None,
        "manifest_sha256": digest(manifest) if manifest.is_file() else None,
        "preregistration_sha256": prereg_sha,
        "manifest_entries": entries,
        "observed_sha256": observed,
        "missing": missing,
        "manifest_errors": manifest_errors,
        "mismatches": mismatches,
        "parse_errors": parse_errors,
        "contract": contract,
        "commit_checks": commit_checks,
        "failed_gates": failed,
        "scientific_claim_boundary": "candidate-edge generator only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.root.resolve(), args.source_commit)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["eligible_for_experiment"] else 2


if __name__ == "__main__":
    sys.exit(main())
