# Phase 1A run1 — formal result

Decision: `STOP_COMBINED_SEMANTICS_MISMATCH`.

The experiment completed 2,400 paired evaluations (4 representations × 6
conditions × 100 replicates) with zero nonfinite or range failures. Gates A0,
A1, A2, A3, A4, and A6 passed. A5 and A7 failed.

Key results:

- adapted null combined FWER: 0.01–0.02 (A1 PASS)
- direct-linear linear sensitivity: 1.00 in R1–R4 (A2 PASS)
- square and tanh nonlinear sensitivity: 1.00 in R1–R4 (A3 PASS)
- square linear false-positive rate: 0.02–0.09 (A4 PASS)
- minimum before/after decision agreement: 0.94 (A5 FAIL; required >=0.95)
- maximum representation rate spread: 0.07 (A6 PASS; required <=0.10)
- combined OR-semantics mismatches: 401/2,400 (A7 FAIL; required 0)

The mismatch is concentrated in nonlinear-square (375) and null (26). The
nonlinear channel detects every square case, while combined detects only
0.02–0.09 across representations. The fixed combined calibration therefore
does not behave as the preregistered logical OR of calibrated linear and
nonlinear decisions.

Phase 1B was not opened. The achieved claim level remains L0, and no direct
causal interpretation is permitted.
