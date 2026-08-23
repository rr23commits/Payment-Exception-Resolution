# Canonical Payment State Machine

This machine is the deterministic financial-state authority. It consumes only ordered evidence types; source CSV `Status`, complaints, and ML output cannot create or override a state.

| State | Meaning | Required incoming evidence |
| --- | --- | --- |
| `INITIATED` | Payment initiation is recorded. | Payment event history: initiation record |
| `AUTHORIZED` | Payment-network authorization is confirmed. | Bank/payment network: authorization confirmation |
| `BANK_DEBITED` | Debit is confirmed by the bank/payment network. | Bank/payment network: debit confirmation |
| `GATEWAY_TIMEOUT` | Gateway recorded a timeout after debit evidence. | Gateway: timeout record |
| `PAYMENT_SUCCESS` | Payment success is confirmed by the bank/payment network. | Bank/payment network: success confirmation |
| `ORDER_FAILED` | Merchant confirms the order failed after payment success. | Merchant: order failure confirmation |
| `CAPTURED` | Gateway confirms capture. | Gateway: capture confirmation |
| `SETTLED` | Bank/payment network confirms settlement. | Bank/payment network: settlement confirmation |
| `REVERSAL_PENDING` | Gateway records the reversal request. | Gateway: reversal request |
| `REVERSED` | Bank/payment network confirms reversal. | Bank/payment network: reversal confirmation |
| `REFUND_PENDING` | Merchant records the refund request. | Merchant: refund request |
| `REFUNDED` | Bank/payment network confirms refund. | Bank/payment network: refund confirmation |

Allowed transitions are encoded in `TRANSITIONS`. Terminal states (`SETTLED`, `REVERSED`, `REFUNDED`) have no outgoing transitions. Any other transition is invalid.
