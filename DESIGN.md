# Payment Operations & Revenue Recovery — Design

## Product overview

This local-first prototype uses controlled, simulated UPI data to help an operator investigate payment exceptions and make a bounded recovery decision. It is not connected to Razorpay, UPI, banks, or payment rails. Simulated outcomes must never be presented as real money movement.

## Implemented

### Evidence and evaluation engine

- Immutable source transactions are supplemented by deterministic lifecycle, merchant, and complaint evidence.
- The engine reconstructs canonical payment state from authority-typed lifecycle evidence, detects deterministic exception incidents, builds cutoff-safe features, evaluates an intervention model against a baseline, recommends a safe policy action, and records an append-only audit trail.
- Historical `ScenarioInstance`, `StateSnapshot`, and `ResolutionCase` semantics remain authoritative. Recovery consumes these engine outputs beside the historical record.
- The existing engine prediction remains evaluated at the first pending-state observation cutoff. Recovery separately reconstructs the original timeout observation cutoff and scores its own cutoff-aligned feature row with the same trained model contract.

### Operator work queue and investigation

- `#queue` is the primary work queue. It shows controlled incidents with transaction ID, time, amount, route, exception reason, lifecycle state, recovery availability, search, and filtering.
- Selecting a row opens `#investigation`, which presents a chronological evidence track, a short diagnosis, and the available controlled recovery decision.
- Human-readable information is shown by default. Raw evidence and audit records are available only in the collapsed `View Raw Payload (JSON)` disclosure.
- Browser hash navigation supports `#queue`, `#investigation`, and `#customer`, including back/forward navigation. The brand link returns to the queue.

### Customer status

- `#customer` is a deliberately simple controlled customer-status view for the selected payment. It shows amount, status, a short progress track, a plain-language explanation, whether action is needed, and a return-to-merchant acknowledgement.
- It does not expose operator policy, model, recovery, or raw technical details.

### Human-approved simulated recovery

The implemented V1 path is:

`timeout → reversal historical evidence → Recovery Opportunity → retry recommendation → operator approve/reject → one deterministic simulated retry → simulated success`

- A `RecoveryOpportunity` is created only for a cutoff-visible `TIMEOUT_TO_REVERSAL` incident and retains the existing incident IDs as evidence.
- The only recommended operation is bounded `RETRY`; existing policy requires human approval.
- Reject records the operator decision and leaves the opportunity rejected.
- Approve records the decision, then performs exactly one deterministic simulated retry. A second decision or retry is rejected.
- `revenue_at_risk`, `recoverable_revenue`, `simulated_recovered_revenue`, and `simulated_recovery_rate` are V1 simulated workflow values only. The original reversal is historical evidence and is never reclassified as recovered revenue.
- API state is local in-memory for the running server. The only write route changes that recovery state and its adjacent audit records; it does not alter engine records or call an external provider.

## Current interfaces

- Static local UI: `ui/index.html`, `ui/app.js`, `ui/styles.css`.
- Read endpoints: incident list, state, incidents, predictions, resolution, audit, evaluation, and recovery read model.
- Narrow write endpoint: `POST /transactions/{id}/recovery/decision` with `APPROVE` or `REJECT` only.

## Explicit non-goals

- Real payment, bank, Razorpay, or UPI integration.
- Autonomous execution, blind retrying, or a recovery agent with authority over payment state.
- Multi-transaction incident grouping, persistence, production authentication, or a product-wide recovery analytics model.
- Prediction of recovery amount or resolution duration.

## Future work

- Define durable, product-wide revenue-at-risk and recovery metrics beyond the controlled V1 opportunity values.
- Add multi-transaction incident grouping and persistence only when a real operating model requires them.
- Define customer communications for additional recovery scenarios without exposing internal evidence.
- Establish production data, authorization, execution, and verification boundaries before considering any real payment integration.
