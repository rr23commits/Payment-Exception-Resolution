const error = document.querySelector("#error");
const queueBody = document.querySelector("#queue-body");
const queueSearch = document.querySelector("#queue-search");
const queueFilter = document.querySelector("#queue-filter");
const queueSummary = document.querySelector("#queue-summary");
const timeline = document.querySelector("#timeline");
const rawPayload = document.querySelector("#raw-payload");
const diagnosis = document.querySelector("#diagnosis");
const recovery = document.querySelector("#recovery");

let incidents = [];
let selectedId = null;

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character]);
const money = (value) => `₹${value ?? "—"}`;
const shortId = (value) => `${value.slice(0, 8)}…${value.slice(-4)}`;
const stamp = (value) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
const percent = (value) => `${(value * 100).toFixed(1)}%`;
const readable = (value) => String(value ?? "").toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("The local API could not load this record.");
  return response.json();
}

async function getOptional(path) {
  const response = await fetch(path);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("The local API could not load this record.");
  return response.json();
}

function badge(value, kind = "quiet") {
  return `<span class="badge ${kind}">${escapeHtml(readable(value))}</span>`;
}

function exceptionReason(incident) {
  return incident.incidents.map((item) => readable(item.kind)).join(", ") || (incident.recovery_available ? "Gateway timeout" : "Exception review");
}

function recoveryBadge(incident) {
  return incident.recovery_available ? badge("Retry recovery available", "recovery") : badge("No recovery path", "quiet");
}

function stateBadge(state) {
  const kind = state.includes("PENDING") ? "pending" : state.includes("FAILED") ? "alert" : "quiet";
  return badge(state, kind);
}

function filteredIncidents() {
  const query = queueSearch.value.trim().toLowerCase();
  return incidents.filter((incident) => {
    const haystack = [incident.transaction_id, incident.route, incident.state, exceptionReason(incident)].join(" ").toLowerCase();
    const filterMatch = queueFilter.value === "all" || (queueFilter.value === "recovery" && incident.recovery_available) || (queueFilter.value === "attention" && !incident.recovery_available);
    return filterMatch && haystack.includes(query);
  });
}

function renderQueue() {
  const rows = filteredIncidents();
  queueSummary.textContent = `${rows.length} visible · ${incidents.filter((item) => item.recovery_available).length} recovery eligible`;
  queueBody.innerHTML = rows.length ? rows.map((incident) => `<tr data-transaction-id="${escapeHtml(incident.transaction_id)}">
    <td class="technical" title="${escapeHtml(incident.transaction_id)}">${escapeHtml(shortId(incident.transaction_id))}</td><td class="muted">${escapeHtml(stamp(incident.timestamp))}</td><td>${escapeHtml(money(incident.amount))}</td><td class="technical">${escapeHtml(incident.route)}</td><td>${escapeHtml(exceptionReason(incident))}</td><td>${stateBadge(incident.state)}</td><td>${recoveryBadge(incident)}</td><td><span class="action-link">Investigate</span></td></tr>`).join("") : '<tr><td colspan="8" class="muted">No controlled incidents match this view.</td></tr>';
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `${name}-view`; });
  document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("is-active", button.dataset.view === name));
  window.location.hash = name;
}

function eventName(record) {
  const source = record.payload || {};
  return readable(source.event_type || source.complaint_type || source.state || record.record_type);
}

function renderCustomer(state, recoveryData) {
  const amount = recoveryData?.opportunity?.amount || incidents.find((item) => item.transaction_id === selectedId)?.amount;
  document.querySelector("#customer-amount").textContent = `Your payment of ${money(amount)} is being resolved`;
  document.querySelector("#customer-state").textContent = readable(state.snapshot.state);
  const phases = ["Payment started", "Bank debit confirmed", "Status being resolved"];
  document.querySelector("#customer-timeline").innerHTML = phases.map((phase) => `<li>${phase}</li>`).join("");
  const eligible = Boolean(recoveryData);
  document.querySelector("#customer-explanation").textContent = eligible ? "We detected a temporary payment-status issue after your bank debit. Your payment is being checked in this controlled demo." : "Your payment status is being checked in this controlled demo.";
  document.querySelector("#customer-action").textContent = "You do not need to take any action right now.";
  document.querySelector("#customer-outcome").textContent = eligible ? "The payment may be resolved after a controlled operator review. This is not a real payment confirmation." : "The current status will remain visible while the payment is being resolved.";
}

function renderRecovery(transactionId, data) {
  recovery.hidden = !data;
  if (!data) return;
  const opportunity = data.opportunity;
  const metrics = data.metrics;
  const pending = opportunity.status === "PENDING_APPROVAL";
  recovery.innerHTML = `<p class="eyebrow">CONTROLLED RECOVERY</p><h2>Recoverable amount</h2><p class="recovery-amount">${money(metrics.recoverable_revenue)}</p><p class="recovery-copy">${escapeHtml(data.timeout_reasoning.join(" "))} ${escapeHtml(data.recommendation_reason)}</p><p class="recovery-copy"><strong>Proposed action:</strong> ${escapeHtml(readable(opportunity.recommended_action))}. ${pending ? "Approval produces one deterministic simulated retry success." : escapeHtml(readable(opportunity.status))} This is not a real payment action.</p>${pending ? '<div class="recovery-actions"><button class="decision-button primary" type="button" data-decision="APPROVE">Approve simulated retry</button><button class="decision-button" type="button" data-decision="REJECT">Reject / maintain reversal</button></div>' : ""}`;
  recovery.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => decideRecovery(transactionId, button.dataset.decision)));
}

async function decideRecovery(transactionId, decision) {
  const response = await fetch(`/transactions/${transactionId}/recovery/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) });
  if (!response.ok) throw new Error((await response.json()).error || "The recovery decision could not be recorded.");
  await loadIncident(transactionId);
}

async function loadIncident(transactionId) {
  error.textContent = "";
  selectedId = transactionId;
  try {
    const [state, incidentData, auditData, recoveryData] = await Promise.all([
      get(`/transactions/${transactionId}/state`), get(`/transactions/${transactionId}/incidents`), get(`/transactions/${transactionId}/audit`), getOptional(`/transactions/${transactionId}/recovery`),
    ]);
    const selected = incidents.find((item) => item.transaction_id === transactionId);
    document.querySelector("#incident-title").textContent = `${shortId(transactionId)} · ${money(selected?.amount)}`;
    const records = auditData.records;
    const evidence = records.filter((record) => record.record_type.includes("EVIDENCE"));
    timeline.innerHTML = evidence.map((record) => `<li><strong>${escapeHtml(eventName(record))}</strong><span>${escapeHtml(stamp(record.payload?.event_time))}</span></li>`).join("");
    rawPayload.textContent = JSON.stringify({ evidence: evidence.map((record) => record.payload), audit: records }, null, 2);
    const finding = incidentData.incidents.map((item) => item.reasoning).join(" ") || "The payment is being monitored through its controlled resolution path.";
    const nextStep = recoveryData ? "An operator may approve or reject the controlled recovery action shown above." : "No controlled recovery action is available for this payment.";
    diagnosis.innerHTML = `<p><strong>Current status</strong>${stateBadge(state.snapshot.state)}</p><p><strong>What we found</strong>${escapeHtml(finding)}</p><p><strong>Next step</strong>${escapeHtml(nextStep)}</p>`;
    renderRecovery(transactionId, recoveryData);
    renderCustomer(state, recoveryData);
  } catch (loadError) { error.textContent = loadError.message; }
}

async function start() {
  try {
    incidents = (await get("/incidents")).incidents;
    renderQueue();
    const preferred = incidents.find((item) => item.recovery_available) || incidents[0];
    if (preferred) await loadIncident(preferred.transaction_id);
    const initial = window.location.hash.slice(1);
    if (["queue", "investigation", "customer"].includes(initial)) showView(initial); else showView("queue");
  } catch (loadError) { error.textContent = loadError.message; }
}

queueSearch.addEventListener("input", renderQueue);
queueFilter.addEventListener("change", renderQueue);
queueBody.addEventListener("click", (event) => { const row = event.target.closest("tr[data-transaction-id]"); if (row) { loadIncident(row.dataset.transactionId); showView("investigation"); } });
document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelector("#return-merchant").addEventListener("click", () => { document.querySelector("#customer-return-note").hidden = false; });
start();
