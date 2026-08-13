# Correlon-LX v0.3

This revision implements the three-stage falsification chain specified for
Correlon-LX v0.3. Each phase is frozen and decided before the next phase may be
opened.

Current phase: **Phase 1A — Adapter Qualification**.

The claim ceiling is shared-structure discovery (L3). This revision does not
license a direct-causality claim (L4).

Parent evidence is immutable Correlon-LX v0.2.3:

- confirmatory decision: `PHASE_0R_PASS`
- engineering stress decision: `STRESS_PASS`
- fixed detector capacity: `rff24`

Phase 1B is not opened unless Phase 1A records `ADAPTER_QUALIFIED` and its
decision artifact is frozen.
