# Phase 13 End-to-End Engine Proof

Dataset: `sha256:62fe1959cfb80afa02a7addd5a371c5511738758cfd1500b8e41e65cafed31de` (1000 source rows).
Verified resolutions: `1000/1000`; audit records: `13018`.

## Held-out performance

| Run | Recall | False escalation | Brier | ROC-AUC | AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| State-rate baseline | 1.000 | 0.396 | 0.240 | 0.516 | 0.612 |
| Phase 10 V3 logistic model | 0.800 | 0.195 | 0.170 | 0.772 | 0.860 |

Resolution-time error: not applicable: the approved model predicts intervention only, not a duration.

No API, UI, or money-moving integration is required or implemented.
