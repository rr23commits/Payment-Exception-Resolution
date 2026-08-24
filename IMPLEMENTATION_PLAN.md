# Recovery Workflow Implementation Record

## Implemented scope

The local controlled vertical slice is implemented:

`gateway timeout → Recovery Opportunity → retry recommendation → operator approve/reject → one simulated retry → simulated success → simulated recovered revenue`

The historical timeout-to-reversal trajectory remains engine evidence. Recovery is a separate, adjacent attempt and never changes the source transaction, `ScenarioInstance`, `StateSnapshot`, or historical `ResolutionCase` semantics.

## Implementation

1. `RecoveryOpportunity` is an in-memory record linked to an existing transaction and its cutoff-visible `TIMEOUT_TO_REVERSAL` incident IDs. It carries a stable ID, source amount, `RETRY` recommendation, simulated origin, and one of `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, or `SIMULATED_SUCCEEDED`.
2. Recovery reconstructs the original timeout observation cutoff and uses the matching timeout incidents. Its policy evidence includes a separately scored prediction from features built at that same cutoff; it does not reuse the existing later pending-cutoff engine prediction.
3. Existing policy provides the `RETRY` recommendation and preserves the human-approval gate.
4. Reject records one local operator decision and performs no retry. Approve records one decision, performs one deterministic simulated retry, and records a simulated success. Duplicate decisions and retries fail.
5. V1 metrics are explicitly simulated: pending amount at risk, eligible amount recoverable, amount recovered only after simulated success, and recovered divided by recoverable (zero-safe).
6. At API startup, eligible opportunities are created beside precomputed engine records. `GET /transactions/{id}/recovery` returns the controlled read model. `POST /transactions/{id}/recovery/decision` accepts only `APPROVE` or `REJECT` and mutates only local recovery state and its audit trail.
7. The UI provides a dense queue, selected-incident investigation view, simple customer-status view, recovery controls while pending, and a collapsed raw-payload disclosure. It labels all recovery information as controlled/simulated.

## Verification covered by tests

- Timeout eligibility, incident linkage, policy approval requirement, rejection, one approved retry, one-time guard, and simulated metric calculations.
- Recovery prediction uses the original timeout cutoff and the recovery read model exposes that cutoff-aligned probability.
- API response validation and local-only decision behavior.
- UI source checks for controlled labels, recovery controls, intended endpoints, raw payload disclosure, and hash-navigation hooks.

## Explicitly not implemented

- Real Razorpay/UPI/bank integration, payment execution, or autonomous retrying.
- Persistence beyond the running local server process.
- Multi-transaction incident grouping or aggregate recovery analytics.
- A new frontend framework, routing dependency, or UI redesign.
