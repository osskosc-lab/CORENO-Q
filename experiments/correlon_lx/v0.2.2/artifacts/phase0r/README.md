# Phase 0R - Representation Robustness

Decision: `STOP_REPRESENTATION_INSTABILITY`

The frozen v0.2.2 experiment completed 1000 calibration replicates for each of four representations and 200 fresh evaluation replicates for each of six conditions. Zero of four representations passed every gate.

All representations passed direct-linear detection/localization, common-pair detection/localization, tanh detection, and broad-global classification. All failed null FWER and nonlinear-square detection/localization.

No parameter, bandwidth, feature count, lag, winsor rate, block length, or threshold rule was changed after observing the result. Phase 1A was not entered. Any modification requires a fresh v0.2.3 revision.

