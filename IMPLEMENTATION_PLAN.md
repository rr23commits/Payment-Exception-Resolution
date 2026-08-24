# Recovery Workflow Implementation Plan

## Scope

Build one local, controlled vertical slice:

`gateway timeout → Recovery Opportunity → retry recommendation → operator approve/reject → one simulated retry → simulated success → simulated recovered revenue`

The existing timeout → reversal trajectory remains historical evidence. Its reversal is never counted as recovered revenue.

## 1. Recovery Opportunity

Add a small in-memory `RecoveryOpportunity` record for an existing `EngineRecord`; do not create a second transaction, incident, state machine, or persistence layer.

- Link by `transaction_id` and retain the existing timeout `ExceptionIncident` IDs as supporting evidence.
- Create an opportunity only for a record with `TIMEOUT_TO_REVERSAL` at the prediction cutoff.
- Store: stable opportunity ID, transaction ID, incident IDs, amount, recommended action (`RETRY`), status (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `SIMULATED_SUCCEEDED`), and explicitly simulated origin.
- Preserve the original `ScenarioInstance`, `StateSnapshot`, and `ResolutionCase` unchanged. The opportunity is a recovery attempt beside—not a reinterpretation of—the historical reversal.

## 2. Recommendation

Reuse the existing evidence flow unchanged:

`ScenarioInstance → reconstruct_state → detect_exceptions → feature/model signals → recommend`

For a timeout opportunity, call the existing policy with a new bounded `RETRY` requested operation. Its existing human-approval branch returns `REQUIRE HUMAN APPROVAL`; do not add an AI agent, classifier, or retry heuristic.

The opportunity read model should expose the reconstructed state, timeout incident reasoning, model probability, policy decision, amount, and recommendation reason so the UI can show why retry is proposed.

## 3. Approval and Audit

Reuse `ResolutionCase.record_human_decision` and `ModeledHumanDecision` for approval/rejection. Extend the same append-only audit trail with opportunity creation and the simulated retry outcome.

- Reject: record the decision; leave the opportunity `REJECTED`; no retry or recovered amount.
- Approve: record the decision; perform exactly one simulated retry; append its outcome; no second attempt is possible.
- Add one provenance value for the simulated recovery result rather than marking it as source payment evidence or a real resolution result.

## 4. Simulated Retry

Add a pure deterministic simulator scoped to this one opportunity type. Given an approved timeout opportunity, it returns `SIMULATED_SUCCEEDED` exactly once and records the source amount as simulated recovered revenue.

It must not call a payment provider, alter the original scenario events/final outcome, retrain the model, or use randomness. The deterministic success is a V1 demo rule, not a prediction or real payment confirmation.

## 5. Amount and Metrics

Keep all values in the opportunity read model and label them `simulated`.

- `revenue_at_risk`: source transaction amount while a timeout opportunity is pending approval.
- `recoverable_revenue`: source transaction amount for this eligible retry opportunity.
- `simulated_recovered_revenue`: source amount only after approval and `SIMULATED_SUCCEEDED`; otherwise zero.
- `simulated_recovery_rate`: `simulated_recovered_revenue / recoverable_revenue`, with zero when no recoverable amount exists.

These are V1 workflow values, not the still-open product-wide revenue formulas in `DESIGN.md`.

## 6. Minimum Backend and API

Keep the existing standard-library, local API and its precomputed engine records.

1. Build timeout Recovery Opportunities from the existing records at API startup and keep their local in-memory state for the running server.
2. Add `GET /transactions/{id}/recovery` for the opportunity, recommendation, decision/outcome, and metrics.
3. Add one narrow `POST /transactions/{id}/recovery/decision` accepting only `APPROVE` or `REJECT`.
4. Reject unknown transactions, non-timeout records, invalid decisions, duplicate decisions, and any attempt to execute more than once.
5. Keep all existing read routes unchanged. The new write route changes only the local simulated recovery record and audit; it has no external side effect.

## 7. Minimum UI

Extend the current selected-incident view; do not redesign it.

- Show a Recovery Opportunity card only when the selected timeout transaction is eligible.
- Display evidence/recommendation and explicit controlled-simulation labels.
- Add Approve and Reject buttons only while approval is pending.
- Submit the decision to the narrow API route, reload the recovery data, then show either rejection or one simulated-success outcome and simulated amounts/rate.
- Keep the current timeline and audit; include the new decision and simulated-recovery audit entries.

## 8. Tests

Add small unit tests around the new recovery module and extend API/UI tests.

- Eligible timeout record creates one opportunity linked to its transaction and incident; non-timeout records do not.
- Policy recommendation for retry requires human approval.
- Reject records an audit decision, executes nothing, and recovers zero.
- Approve records one decision, produces one deterministic simulated success, and preserves the original reversal as historical evidence.
- Duplicate decisions/retries fail; amounts and zero-denominator rate are correct.
- API route validation, response serialization, and local-only behavior are covered.
- UI source test confirms simulation labeling, decision controls, and use of only the intended recovery endpoints.

## 9. Implementation Order

1. Define the Recovery Opportunity, outcome, V1 metric read model, and simulated-recovery provenance; write the unit tests first.
2. Add timeout eligibility and policy-gated retry recommendation using existing engine records.
3. Extend `ResolutionCase`/audit with a one-time approved simulated retry and test the immutable historical scenario remains unchanged.
4. Add the in-memory API state plus recovery GET/decision POST routes and API tests.
5. Add the small UI card and approval controls; update UI tests.
6. Run the full suite and the local demo. Confirm one timeout record shows approval → simulated success, while a rejection produces no recovery.

## 10. Non-goals

- Real Razorpay/UPI integration or payment execution.
- Autonomous execution or blind retries.
- A multi-agent framework.
- Multi-transaction incident grouping.
- A full UI redesign.

## Files likely to change

- `src/recovery/__init__.py` — new minimal opportunity and deterministic retry logic.
- `src/policy/__init__.py` — add the bounded retry operation to the existing approval gate.
- `src/provenance.py` — recognize the simulated-recovery audit provenance.
- `src/resolution/__init__.py` — append opportunity/retry records without changing historical verification.
- `src/evaluation/__init__.py` — construct the retry-gated timeout path for existing engine records.
- `src/api/__init__.py` — local recovery state and two narrow routes.
- `ui/index.html`, `ui/app.js`, `ui/styles.css` — one recovery card and pending-decision controls.
- `tests/resolution/test_resolution.py`, `tests/policy/test_policy.py`, `tests/api/test_api.py`, `tests/ui/test_ui.py`, plus a focused `tests/recovery/test_recovery.py`.
- `HANDOVER.md`, `FLOW.md`, and a focused `FEATURES/` record — update continuity after implementation.

## Definition of Done

For a timeout transaction, the local demo displays the existing evidence and retry recommendation; an operator can approve or reject exactly once. Approval creates exactly one deterministic simulated success, records the source amount only as simulated recovered revenue, and appends the decision and outcome to the audit. Rejection makes no retry or recovery. The original timeout → reversal evidence remains visible and is never counted as recovered revenue. All existing and new tests pass, with no real payment integration, autonomous action, new dependency, or UI redesign.
