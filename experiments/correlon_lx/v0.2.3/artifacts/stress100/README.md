Exit code: 0
Wall time: 0.9 seconds
Output:
# v0.2.3 stress100

Decision: `STRESS_PASS`.

This is an engineering stress test, not a replacement confirmatory Phase 0R. It fixes the selected RFF24 candidate and the v0.2.3 confirmatory calibration distributions, then evaluates 100 independent stress iterations over all four representations and six conditions (2,400 datasets total).

- numeric failures: 0
- non-finite detector outputs: 0
- out-of-range detector outputs: 0
- all 2,400 expected rows present
- null target combined rejection: 0.00 across all representations in this stress namespace
- square nonlinear-channel target rejection: 1.00 across all representations
- direct/common/tanh/global target nonlinear rejection: 1.00 across all representations
- square Pearson target rejection: 0.02-0.08 across representations

The existing Phase 0R decision remains the scientific decision. This stress result only supports implementation stability under a disjoint seed namespace.

