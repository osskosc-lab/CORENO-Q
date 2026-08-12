from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VERSION = "Correlon-LX-v0.2.1"
SPEC_RELATIVE = Path("specs/correlon_lx/v0.2.1")
EXPECTED_PAYLOADS = {
    "interface_freeze.json",
    "phase0_pilot_results.json",
    "README.md",
}
LINE_PATTERN = re.compile(r"^([0-9A-Fa-f]{64})  ([^/\\]+)$")


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


def parse_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file():
        return entries, ["manifest_missing"]
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        match = LINE_PATTERN.fullmatch(line)
        if not match:
            errors.append(f"manifest_line_{number}_invalid")
            continue
        digest, name = match.groups()
        if name in entries:
            errors.append(f"manifest_duplicate:{name}")
        entries[name] = digest.upper()
    return entries, errors


def evaluate(root: Path, source_commit: str | None) -> dict:
    spec = root / SPEC_RELATIVE
    manifest = spec / "manifest.sha256"
    entries, errors = parse_manifest(manifest)
    listed = set(entries)
    if listed != EXPECTED_PAYLOADS:
        errors.append("manifest_payload_set_mismatch")
    if "manifest.sha256" in listed or "preregistration.json" in listed:
        errors.append("manifest_self_or_envelope_reference")

    missing = sorted(name for name in EXPECTED_PAYLOADS if not (spec / name).is_file())
    mismatches = []
    observed = {}
    for name in sorted(EXPECTED_PAYLOADS - set(missing)):
        actual = sha256(spec / name)
        observed[name] = actual
        if entries.get(name) != actual:
            mismatches.append(
                {"path": name, "expected": entries.get(name), "actual": actual}
            )

    parse_errors = []
    interface = None
    pilot = None
    preregistration = None
    for name, target in [
        ("interface_freeze.json", "interface"),
        ("phase0_pilot_results.json", "pilot"),
        ("preregistration.json", "preregistration"),
    ]:
        try:
            value = json.loads((spec / name).read_text(encoding="utf-8"))
            if target == "interface":
                interface = value
            elif target == "pilot":
                pilot = value
            else:
                preregistration = value
        except Exception as exc:
            parse_errors.append({"file": name, "error": str(exc)})

    contract = {}
    if interface and pilot and preregistration:
        contract = {
            "interface_version": interface.get("version") == VERSION,
            "fresh_revision_parent": interface.get("revision_parent")
            == "Correlon-LX-v0.2",
            "external_manifest_scheme": interface.get("integrity", {}).get("scheme")
            == "external-manifest-sha256",
            "no_self_referential_hash": "freeze_sha256" not in interface
            and interface.get("integrity", {}).get("self_referential_digest_fields")
            is False,
            "legacy_pilot_provenance_preserved": pilot.get("version")
            == "Correlon-LX-v0.2-Phase0",
            "rff_features": interface.get("detector", {}).get("rff_features")
            == pilot.get("rff_features")
            == preregistration.get("phase0r", {}).get("rff_features")
            == 24,
            "lags": pilot.get("lags")
            == preregistration.get("phase0r", {}).get("lags")
            == list(range(-3, 4)),
            "scientific_boundary": interface.get("scientific_role")
            == "cross-theory residual discovery service; candidate-edge generator only"
            and preregistration.get("scientific_claim_boundary")
            == "candidate-edge generator only",
        }

    commit_checks = {
        "source_commit_supplied": bool(source_commit),
        "head_matches_source_commit": False,
        "source_commit_exists": False,
    }
    if source_commit:
        try:
            commit_checks["head_matches_source_commit"] = (
                git(root, "rev-parse", "HEAD") == source_commit
            )
            subprocess.check_call(
                ["git", "-C", str(root), "cat-file", "-e", f"{source_commit}^{{commit}}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            commit_checks["source_commit_exists"] = True
        except Exception:
            pass

    failed_gates = []
    if missing:
        failed_gates.append("F0_payload_missing")
    if errors:
        failed_gates.append("F1_manifest_invalid")
    if mismatches:
        failed_gates.append("F1_raw_byte_sha256_mismatch")
    if parse_errors:
        failed_gates.append("F3_json_parse_failure")
    if contract and not all(contract.values()):
        failed_gates.append("F4_cross_file_contract_failure")
    if not contract and not parse_errors:
        failed_gates.append("F4_cross_file_contract_unavailable")
    if "manifest.sha256" in listed or "preregistration.json" in listed:
        failed_gates.append("F5_manifest_self_reference")
    if not all(commit_checks.values()):
        failed_gates.append("F6_source_commit_not_fixed")

    decision = (
        "REPOSITORY_FREEZE_COMPLETE" if not failed_gates else "STOP_FREEZE_GATE_FAILURE"
    )
    eligible = decision == "REPOSITORY_FREEZE_COMPLETE"
    prereg_sha = sha256(spec / "preregistration.json") if (spec / "preregistration.json").is_file() else None
    namespace = (
        f"correlon-lx-v0.2.1-cycle1-run1-{prereg_sha[:12].lower()}"
        if eligible and prereg_sha
        else None
    )
    return {
        "version": VERSION,
        "phase": "0F-prime External Manifest Freeze",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "decision": decision,
        "eligible_for_cycle1": eligible,
        "manifest_sha256": sha256(manifest) if manifest.is_file() else None,
        "preregistration_sha256": prereg_sha,
        "seed_namespace": namespace,
        "manifest_entries": entries,
        "observed_sha256": observed,
        "missing_payloads": missing,
        "manifest_errors": errors,
        "byte_mismatches": mismatches,
        "parse_errors": parse_errors,
        "cross_file_contract": contract,
        "source_commit_checks": commit_checks,
        "failed_gates": failed_gates,
        "scientific_claim_boundary": "candidate-edge generator only",
        "next_action": "Run Phase 0R preregistration completeness precheck."
        if eligible
        else "Create a new revision; do not repair this freeze after observing its result.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.root.resolve(), args.source_commit)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["eligible_for_cycle1"] else 2


if __name__ == "__main__":
    sys.exit(main())
