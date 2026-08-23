# V1 Deterministic Scenario Contracts

Every scenario starts with a loaded source transaction but ignores its `Status` value for lifecycle and outcome semantics. Lifecycle paths and final outcomes are domain semantics in `__init__.py`. Observation cutoffs, event offsets, and windows are simulated experimental parameters in `config.py`, not Razorpay or UPI SLAs.

| Scenario | Starting conditions | Visible evidence at configured cutoff | Hidden future evidence | Configured timing | Final outcome | Intervention ground truth |
| --- | --- | --- | --- | --- | --- | --- |
| `timeout_to_reversal` | No lifecycle assumed; bank debit is later confirmed. | initiation, bank debit, gateway timeout | reversal requested, reversal confirmed | 10 min window; event offsets finish at 6 min | `REVERSED` | No: timestamp-derived duration is within window. |
| `delayed_stuck_reversal` | Same controlled debit and timeout path. | initiation, bank debit, gateway timeout, reversal requested | reversal confirmed | 10 min window; event offsets finish at 18 min | `REVERSED` | Yes: timestamp-derived duration exceeds window. No explicit human-handling state. |
| `payment_success_order_failure` | No lifecycle assumed; payment success and merchant order failure are later evidenced. | initiation, bank debit, payment success, merchant order failure | refund requested, refund confirmed | 12 min window; event offsets finish at 8 min | `REFUNDED` | No: timestamp-derived duration is within window. Merchant evidence: `ORDER_FAILURE_CONFIRMED`, `REFUND_REQUESTED`. |
| `refund_pending_stuck` | Same controlled payment-success/order-failure path. | initiation, bank debit, payment success, merchant order failure, refund requested | refund confirmed | 12 min window; event offsets finish at 20 min | `REFUNDED` | Yes: timestamp-derived duration exceeds window. No explicit human-handling state. |

The ordered evidence types resolve through the Phase 3 state machine. Their source requirements are inherited from `EVIDENCE_REQUIREMENTS`: bank/payment network for debit, success, reversal/refund confirmation; gateway for timeout/reversal request; merchant for order failure/refund request; and payment-event history for initiation.

`requires_intervention` is deterministic: it is true only when the actual duration derived from configured generated event timestamps exceeds the supplied experimental window, or when a scenario reaches its explicitly configured `human_handling_state`. V1 defines no such state; its two intervention cases are window violations.
