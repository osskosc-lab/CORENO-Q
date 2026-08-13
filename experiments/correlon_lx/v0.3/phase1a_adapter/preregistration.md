# Correlon-LX v0.3 — Phase 1A Adapter Qualification

Status: preregistered before the Phase 1A seed namespace is opened.

## Objective and claim boundary

Test whether each frozen representation adapter preserves the decisions of the
fixed v0.2.3 `rff24` detector without creating null detections, erasing genuine
linear/nonlinear structure, or turning square structure into linear structure.

This is an adapter audit, not detector optimization. No result may change the
adapter, RFF parameters, calibration, generator, sample count, alpha, metric,
or gate. Passing Phase 1A establishes L1 only. L4 causal-link claims remain
prohibited.

## Frozen parent

- parent revision: Correlon-LX v0.2.3
- required parent decision: `PHASE_0R_PASS`
- required stress decision: `STRESS_PASS`
- detector: `rff24`, lags -3..+3, 15 pairs
- adapters: the exact v0.2.3 R1–R4 transformations
- calibration: the exact v0.2.3 Phase 0R per-representation calibration

## Paired design

For every condition and replicate, one raw dataset `X` is generated. For each
representation `r`, the same detector realization (including its frozen RFF
parameters) scores both `X` and `A_r(X)`. Thus only the adapter changes within
the pair. The same raw dataset is also shared across R1–R4.

Conditions: `null`, `direct_linear`, `common_pair`, `nonlinear_square`,
`nonlinear_tanh`, `global_common`. Replicates: 100 per condition. Total paired
evaluations: 4 representations × 6 conditions × 100 = 2,400.

The v0.2.3 Phase 0R calibration is used without recalibration. For null, a
channel decision is family-wise (`any` of 15 pairs). For non-null conditions,
the channel decision is the preregistered H–V target-pair decision.

For every channel `c` in linear, nonlinear, combined, store target and maximum
score distortion `S_c(A_r(X)) - S_c(X)`, before/after p-values, and before/after
decisions.

## Combined semantics (A7, fixed before results)

The v0.2.3 specification defines `combined_pair_score` as the maximum over the
linear and nonlinear channels. This is Case B: an OR-style general detector,
not a conservative detector requiring both channels. Therefore its decision
semantics must satisfy, dataset by dataset:

`combined_decision == (linear_decision OR nonlinear_decision)`.

The existing detector and its separate combined-null calibration are audited
as-is. They are not repaired in Phase 1A. A single mismatch fails A7.

## Gates

- A0: zero nonfinite or out-of-range score failures before and after adapters.
- A1: adapted null combined family-wise rejection rate <= 0.05 in every representation.
- A2: adapted direct-linear target linear sensitivity >= 0.95 in every representation.
- A3: adapted square and tanh target nonlinear sensitivity >= 0.95 in every representation.
- A4: adapted square target linear false-positive rate <= 0.10 in every representation.
- A5: paired decision agreement >= 0.95 for every representation × condition × channel cell.
- A6: maximum minus minimum R1–R4 rate <= 0.10 for each A1–A5 primary performance cell.
- A7: zero OR-semantics mismatches among all adapted decisions.

All A0–A7 must pass for `ADAPTER_QUALIFIED`. If A7 fails, the specific decision
is `STOP_COMBINED_SEMANTICS_MISMATCH`; otherwise any other gate failure is
`STOP_ADAPTER_QUALIFICATION`. A failed Phase 1A prohibits Phase 1B execution.

## Seed namespace

`Correlon-LX-v0.3|phase1a-paired|condition=<condition>|replicate=<1..100>`

The representation is intentionally absent so R1–R4 receive identical raw
data. SHA-256 first eight bytes, unsigned big-endian, seed NumPy PCG64.
