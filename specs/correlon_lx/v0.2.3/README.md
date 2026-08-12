# Correlon-LX v0.2.3

This fresh revision audits two distinct failures observed in v0.2.2:

1. calibration/evaluation null non-equivalence caused by calibrating on block-permuted series but evaluating on unpermuted generative AR nulls;
2. lack of direct qualification of the nonlinear channel on the centered-square positive control.

The revision is frozen before experimental seeds are drawn. It uses fresh generative nulls, max-statistic conformal p-values, a preregistered four-candidate RFF capacity ladder on an R1-only development split, and a disjoint confirmatory Phase 0R.

Earlier v0.2, v0.2.1, and v0.2.2 records are immutable. Any result-dependent change after this freeze requires v0.2.4.
