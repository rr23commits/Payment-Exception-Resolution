# Phase 10 V2 Experiment

## Test-set comparison

| Run | Accuracy | Recall | False escalation | Brier | ROC-AUC | AP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| State-rate baseline | 0.604 | 1.000 | 0.396 | 0.240 | 0.516 | 0.612 |
| payment_attributes | 0.570 | 0.856 | 0.342 | 0.253 | 0.494 | 0.613 |
| plus_state | 0.577 | 0.867 | 0.342 | 0.253 | 0.494 | 0.611 |
| plus_event_history_timing | 0.685 | 0.800 | 0.195 | 0.170 | 0.772 | 0.860 |
| plus_merchant_signals | 0.685 | 0.800 | 0.195 | 0.170 | 0.772 | 0.860 |
| plus_complaint_signals | 0.685 | 0.800 | 0.195 | 0.170 | 0.772 | 0.860 |

Split counts: `{'train': 707, 'validation': 144, 'test': 149}`.

No policy, money action, or UI behavior is included.
