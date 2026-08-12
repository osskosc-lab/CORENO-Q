from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SPEC_REL = Path("specs/correlon_lx/v0.2.2")
PAYLOADS = {
    "interface_freeze.json",
    "phase0_pilot_results.json",
    "README.md",
    "phase0r_preregistration_v0.2.2.json",
}
PATTERN = re.compile(r"^([0-9A-F]{64})  ([^/\\]+)$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    entries, errors = {}, []
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
    entries, manifest_errors = parse_manifest(spec / "manifest.sha256")
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
    for name in ["interface_freeze.json", "phase0_pilot_results.json", "phase0r_preregistration_v0.2.2.json"]:
        try:
            objects[name] = json.loads((spec / name).read_text(encoding="utf-8"))
        except Exception as exc:
            parse_errors.append({"path": name, "error": str(exc)})
    interface = objects.get("interface_freeze.json", {})
    prereg = objects.get("phase0r_preregistration_v0.2.2.json", {})
    parent_path = root / "specs/correlon_lx/v0.2.1/interface_freeze.json"
    contract = {
        "version": interface.get("version") == prereg.get("version") == "Correlon-LX-v0.2.2",
        "external_manifest": interface.get("integrity", {}).get("scheme") == "external-manifest-sha256",
        "no_self_digest": interface.get("integrity", {}).get("self_referential_digest_fields") is False,
        "parent_exists": parent_path.is_file(),
        "parent_hash": parent_path.is_file()
        and digest(parent_path) == interface.get("revision_parent", {}).get("sha256"),
        "executable_status": prereg.get("status") == "EXECUTABLE_REPRESENTATION_FREEZE",
        "protocol_hash": prereg.get("protocol_source_sha256")
        == "3E7152C1034A4FE85A0B0709368D387A0D2AD170A34D20FAEDACDDACE75E2C12",
        "scientific_boundary": prereg.get("scientific_claim_boundary") == "candidate-edge generator only",
    }
    commit = {"exists": False, "head_matches": False}
    try:
        subprocess.check_call(
            ["git", "-C", str(root), "cat-file", "-e", f"{source_commit}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        commit["exists"] = True
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, encoding="utf-8"
        ).strip()
        commit["head_matches"] = head == source_commit
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
    if not all(commit.values()):
        failed.append("F6_source_commit_failure")
    decision = "REPOSITORY_FREEZE_COMPLETE" if not failed else "STOP_FREEZE_GATE_FAILURE"
    prereg_sha = observed.get("phase0r_preregistration_v0.2.2.json")
    return {
        "version": "Correlon-LX-v0.2.2",
        "phase": "Cycle 0F-double-prime",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "decision": decision,
        "eligible_for_phase0r": not failed,
        "seed_namespace": f"correlon-lx-v0.2.2-phase0r-{prereg_sha[:12].lower()}" if not failed else None,
        "manifest_sha256": digest(spec / "manifest.sha256"),
        "preregistration_sha256": prereg_sha,
        "manifest_entries": entries,
        "observed_sha256": observed,
        "missing": missing,
        "manifest_errors": manifest_errors,
        "mismatches": mismatches,
        "parse_errors": parse_errors,
        "contract": contract,
        "commit_checks": commit,
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
    return 0 if result["eligible_for_phase0r"] else 2


if __name__ == "__main__":
    sys.exit(main())
