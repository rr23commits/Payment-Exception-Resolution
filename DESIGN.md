# Payment Operations & Revenue Recovery — Design

## 1. Product Overview

This Razorpay Buildathon project evolves a transaction/issue view into a payment-operations and revenue-recovery product. It should help an operator understand ambiguous payment exceptions, identify recoverable opportunities, obtain approval for consequential action, and measure the result.

The product is local-first and uses controlled, simulated UPI data. It is not connected to Razorpay or UPI and must never represent simulated outcomes as real recovered money.

**Implemented:** a deterministic payment-exception engine, controlled evaluation, and a read-only local demo.

**Planned direction:** add the product concepts and workflow needed to manage revenue recovery, while retaining the existing engine as the evidence and decision foundation.

## 2. Current State

The repository has a complete controlled-engine MVP for 1,000 rows from the Kaggle UPI Payment Transactions Dataset. The source CSV has transaction attributes and a final `SUCCESS`/`FAILED` status, but no lifecycle events. The project therefore generates deterministic lifecycle, merchant, and complaint evidence without changing source data.

**Implemented behavior**

- Reconstructs a canonical payment state from cutoff-safe, authority-typed lifecycle evidence; the source status and complaints do not determine financial state.
- Detects per-transaction exception incidents: timeout-to-reversal, payment-success/merchant-order mismatch, delayed reversal, refund pending, and contradictory evidence.
- Supports four controlled scenarios: timeout → reversal, delayed/stuck reversal, payment success + merchant/order failure, and refund pending/stuck.
- Predicts the controlled `requires_intervention` target with a train/test-evaluated logistic model, compared with a state-rate baseline. The current held-out report shows ROC-AUC `0.772` and Brier `0.170` for the model, versus `0.516` and `0.240` for the baseline.
- Produces safe recommendations only: monitor, recheck/reconcile, notify, escalate, or require human approval. There is no executor or real money movement.
- Records observed evidence, predictions, policy, modeled human decisions when applicable, revealed future evidence, and verification in an append-only audit trail.
- Serves a local read-only API and one static V0 page. The page selects a per-transaction incident and shows a timeline, reconstructed state, detected exception, baseline and ML intervention signals, recommendation, modeled approval state, revealed resolution, and audit history.

The current page is operator-oriented only. It has no customer flow, revenue metrics, incident grouping across transactions, recovery-opportunity object, action approval UI, or execution controls.

## 3. Target Product

The target product is an operations workspace that turns payment exceptions into accountable recovery work:

`Transaction → Incident (when a common problem affects multiple transactions) → Recovery Opportunity → AI recommendation → Human approval → bounded execution → measured outcome`

An operator should be able to move from revenue at risk, to an incident or individual transaction, to evidence-backed analysis, to a recommended recovery action and its recorded result. A customer should see only their payment status, a simple explanation, and an appropriate next step.

**Planned:** revenue-at-risk, recoverable-revenue, recovered-revenue, and recovery-rate metrics. Their formulas are intentionally open until the recovery semantics and measurement rules are defined.

## 4. User Roles

### Customer

**Planned:** sees payment status, a simple failure explanation, and a retry/recovery next action when appropriate. The customer does not see internal incident, policy, model, or AI-analysis information.

### Operator

**Implemented in V0:** can inspect individual controlled transaction incidents, their evidence, model/baseline signals, recommendation, final controlled resolution, and audit history.

**Planned:** sees revenue at risk, active incidents, recovery opportunities, affected transactions, AI investigation, recommended actions, approvals, outcomes, and audit history in an operator workflow.

## 5. Core Concepts

### Transaction

One individual payment. **Implemented:** immutable source transaction plus separately generated lifecycle and complaint evidence.

### Incident

A payment problem requiring operational attention. **Implemented:** an `ExceptionIncident` is a per-transaction deterministic finding. **Planned:** one incident may link many affected transactions when the system identifies a shared pattern; that grouping does not yet exist.

### Recovery Opportunity

A transaction or group of transactions where a bounded intervention may recover revenue. **Planned:** this does not yet exist as a domain object, queue, or UI element.

### AI Recovery Agent

An evidence-driven decision loop, not a chatbot. **Partly implemented:** reconstruction, prediction, and policy provide the observe/investigate/recommend portions. **Planned:** the product-level agent workflow, opportunity management, approval handoff, execution adapter, and recovery measurement.

## 6. Core Workflow

The product workflow is:

1. **Observe** — ingest transaction and available payment, gateway, merchant, and complaint evidence.
2. **Investigate** — reconstruct state, surface conflicts/exceptions, and determine whether revenue may be at risk.
3. **Recommend** — create a recovery opportunity and recommend a bounded action with its supporting evidence.
4. **Human approval** — record approve/reject before any consequential action.
5. **Execute** — perform only the approved, policy-permitted action; real payment operations remain out of scope for the local demo.
6. **Measure** — record the verified outcome and whether the amount is simulated or real; update revenue metrics only under their future agreed definitions.

**Implemented path:** controlled evidence → reconstruction → exception detection → intervention prediction → safe policy recommendation → optional modeled human decision → controlled future reveal and verification → audit.

**Planned MVP path:** select one recovery workflow that carries an operator from an identified opportunity through approval, simulated execution, and an explicitly simulated outcome. The existing engine supports controlled resolution scenarios but does not currently model a retry that succeeds or revenue recovered.

## 7. AI Agent

The AI Recovery Agent may observe, investigate, rank, predict, recommend, and explain. It must not be a separate conversational interface or an authority over payment state.

**Implemented**

- Deterministic state reconstruction and exception rules remain authoritative for payment state.
- A logistic model predicts the controlled intervention target from time-safe features; it does not predict recovery amount or resolution duration.
- Policy consumes established evidence and an optional prediction, returning only a closed safe action catalogue.

**Planned**

- Turn evidence, deterministic findings, and predictions into a reviewable recovery-opportunity recommendation.
- Explain why the action is recommended, including the evidence and uncertainty available at the decision cutoff.
- Support only bounded actions approved by policy and, where required, by an operator.

## 8. MVP

The MVP is one complete, demonstrable recovery workflow—not a multi-agent system.

It must show:

1. a failed/ambiguous payment is identified as a possible recovery opportunity;
2. the agent presents the evidence and a recommended bounded recovery action;
3. an operator approves or rejects it;
4. the system simulates the approved action and records its outcome;
5. the UI and audit distinguish simulated recovery from real recovered revenue.

**Implemented foundation:** four controlled exception-resolution scenarios, policy guardrails, modeled human-decision records, and verified controlled outcomes.

**Not implemented:** a recovery-opportunity model, approval interface, action execution/simulation for an approved recovery action, recovery amount accounting, or a defined primary recovery scenario. These are the smallest missing pieces to select and build first.

## 9. UI Direction

The current static V0 UI is preserved. Do not redesign it as part of this document's adoption.

**Current V0:** a local read-only incident selector with summary cards, evidence timeline, and audit history. It fetches precomputed API records and contains no business logic, forms, payment buttons, or write requests.

**Eventual operator hierarchy:**

`Revenue at risk → active incidents → recovery opportunities → individual transactions → AI investigation → recovery action → outcome`

**Eventual customer hierarchy:**

`Payment status → simple explanation → next action`

The future UI consumes established engine and recovery records; it must not duplicate state, policy, model, or execution logic in the browser.

## 10. Guardrails

- Human approval is required for consequential or money-moving actions.
- Recovery actions are bounded by a closed policy catalogue; no blind retries.
- AI proposes; deterministic rules constrain; humans authorize money movement.
- Canonical state comes from authority-typed lifecycle evidence, not a model, complaint, or source CSV status.
- Record the recommendation, supporting evidence, operator decision, action attempt, and verified outcome.
- Existing policy has no financial executor; refunds, captures, transfers, releases, and cancellations remain non-executable in this prototype.
- Clearly label all current data, windows, actions, and outcomes as controlled/simulated. Never claim simulated money as real recovered money.

## 11. Current → Target Gaps

| Current implementation | Target capability | Gap |
| --- | --- | --- |
| Per-transaction deterministic exception incidents | Multi-transaction incidents and linked affected transactions | No grouping, relationship, or incident-level workflow. |
| State, exception, prediction, and safe recommendation | Recovery Opportunity | No object, lifecycle, prioritization, or queue. |
| Optional modeled human decision in the audit | Operator approval workflow | No approval surface or operator action handoff. |
| Read-only policy recommendations | Bounded simulated execution | No executor/simulation record for an approved recovery action. |
| Controlled final resolution verification | Revenue recovery measurement | No recovery amount or metric definitions; resolution is not automatically recovered revenue. |
| Operator-oriented V0 evidence page | Customer status/explanation/next action | No customer view or information boundary in UI/API. |
| Static individual incident selector | Revenue-at-risk to outcome navigation | No aggregate metrics or target hierarchy. |

## 12. Open Questions

1. Which one recovery scenario and action should define the first product MVP, given that the existing four scenarios are exception-resolution paths rather than an approved retry/recovery flow?
2. What conditions make an amount revenue at risk, recoverable, or recovered, and what are the formulas for recovery rate?
3. What bounded actions are allowed in the simulation, and which require approval versus only logging/monitoring?
4. What evidence and rule should group individual transaction incidents into a single multi-transaction incident?
5. What result proves an action executed successfully in the simulation, independently of the original controlled lifecycle outcome?
6. Which customer next actions are appropriate for each approved recovery workflow, without exposing internal operational or AI data?
