# Correlon-LX v0.2.3 experiment-run1

Final decision: `PHASE_0R_PASS`.

## Phase results

- Phase 0C: PASS. Fresh generative-null calibration and evaluation were exchangeable; no block permutation was used. RFF24 combined FWER was 0.051 on 1000 fresh null evaluations.
- Phase 0N: PASS. All four preregistered capacities passed; the minimum-capacity rule selected RFF24. Its development square nonlinear TPR was 1.00 and nonlinear null FPR was 0.03.
- Confirmatory Phase 0R: PASS. All four representations passed every gate. FWER was 0.035–0.050, square nonlinear TPR/localization was 1.00/1.00, and square linear TPR was 0.025–0.085.

The raw executable output is retained as `raw_final_decision.json`. It marked `phase1a_entered=true` immediately on Phase 0R PASS. Since this run did not execute adapter qualification, the audited `final_decision.json` corrects only that reporting meaning to `eligible_for_phase1a=true` and `phase1a_entered=false`. No scientific metric or parameter was changed.

This is synthetic detector qualification, not a causal or ontological result. Qualified theories and scientific candidate edges remain zero.
