const select = document.querySelector("#incident-select");
const error = document.querySelector("#error");
const summary = document.querySelector("#summary");
const timeline = document.querySelector("#timeline");
const audit = document.querySelector("#audit");

const text = (value) => value ?? "Not available";
const percent = (value) => `${(value * 100).toFixed(1)}%`;

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("The local API could not load this record.");
  return response.json();
}

function card(label, value, detail = "") {
  return `<article><p>${label}</p><strong>${text(value)}</strong><small>${detail}</small></article>`;
}

function eventLabel(record) {
  const payload = record.payload || {};
  const name = payload.event_type || payload.complaint_type || payload.state || record.record_type;
  const time = payload.event_time || "";
  return `<li><strong>${name}</strong><span>${record.record_type}${time ? ` · ${time}` : ""}</span></li>`;
}

async function loadIncident(transactionId) {
  error.textContent = "";
  try {
    const [state, incidents, predictions, resolution, auditData, evaluation] = await Promise.all([
      get(`/transactions/${transactionId}/state`),
      get(`/transactions/${transactionId}/incidents`),
      get(`/transactions/${transactionId}/predictions`),
      get(`/transactions/${transactionId}/resolution`),
      get(`/transactions/${transactionId}/audit`),
      get("/evaluation"),
    ]);
    const model = predictions.model_prediction;
    const baseline = predictions.baseline_prediction;
    const policy = predictions.policy_decision;
    const verification = resolution.verification;
    const exceptionNames = incidents.incidents.map((incident) => incident.kind).join(", ") || "No detected exception";
    summary.innerHTML = [
      card("Reconstructed state", state.snapshot.state, "Cutoff-safe state from observed evidence"),
      card("Detected exception", exceptionNames, policy.reasoning),
      card("Baseline intervention", baseline.requires_intervention ? "Yes" : "No", percent(baseline.intervention_probability)),
      card("ML intervention", model.requires_intervention ? "Yes" : "No", percent(model.probability)),
      card("Priority / recommendation", policy.action, "Policy-constrained; no execution"),
      card("Human approval", resolution.human_decision?.decision || "Not required", "Modeled record only"),
      card("Final revealed resolution", verification.final_outcome, verification.requires_intervention ? "Intervention required" : "No intervention required"),
      card("Resolution estimate", "Not available", evaluation.resolution_time_error),
    ].join("");
    const evidence = auditData.records.filter((record) => record.record_type.includes("EVIDENCE") || record.record_type.includes("COMPLAINT"));
    timeline.innerHTML = evidence.map(eventLabel).join("");
    audit.innerHTML = auditData.records.map(eventLabel).join("");
  } catch (loadError) {
    error.textContent = loadError.message;
  }
}

async function start() {
  try {
    const data = await get("/incidents");
    select.innerHTML = data.incidents.map((incident) => `<option value="${incident.transaction_id}">${incident.transaction_id}</option>`).join("");
    select.addEventListener("change", () => loadIncident(select.value));
    await loadIncident(select.value);
  } catch (loadError) {
    error.textContent = loadError.message;
  }
}

start();
