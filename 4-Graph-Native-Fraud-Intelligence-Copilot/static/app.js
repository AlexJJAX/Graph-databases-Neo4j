"use strict";

const state = {
  alerts: [], examples: [], selectedAlert: null, sessionId: loadSessionId(),
  graph: {nodes: [], edges: []}, timeline: [], evidence: [],
  transform: {x: 0, y: 0, scale: 1}, drag: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const svgNS = "http://www.w3.org/2000/svg";

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  wireUi();
  if (state.sessionId) $("#threadLabel").textContent = `Graph memory · ${state.sessionId.slice(0, 8)}`;
  try {
    const [status, meta] = await Promise.all([api("/api/status"), api("/api/meta")]);
    renderStatus(status);
    state.alerts = meta.alerts || [];
    state.examples = meta.examples || [];
    renderAlerts();
    renderSuggestions();
    renderStats(status);
    if (state.alerts.length) await selectAlert(state.alerts[0].alertId);
  } catch (error) {
    renderStatus({ready: false});
    showToast(error.message || "Unable to load fraud graph");
  }
}

function wireUi() {
  $("#alertFilter").addEventListener("input", renderAlerts);
  $("#investigationForm").addEventListener("submit", runInvestigation);
  $("#newThreadButton").addEventListener("click", resetThread);
  $$(".tab").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
  $("#zoomInButton").addEventListener("click", () => zoomBy(1.18));
  $("#zoomOutButton").addEventListener("click", () => zoomBy(0.84));
  $("#resetGraphButton").addEventListener("click", resetGraphView);
  const svg = $("#networkSvg");
  svg.addEventListener("wheel", onGraphWheel, {passive: false});
  svg.addEventListener("pointerdown", onGraphPointerDown);
  window.addEventListener("pointermove", onGraphPointerMove);
  window.addEventListener("pointerup", onGraphPointerUp);
  setupResizer($("#leftResizer"), "--left-width", 250, 520, false);
  setupResizer($("#rightResizer"), "--right-width", 320, 650, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { $("#nodeInspector").hidden = true; onGraphPointerUp(); }
  });
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

function renderStatus(status) {
  $("#statusDot").className = `status-dot ${status.ready ? "ready" : "error"}`;
  $("#statusText").textContent = status.ready ? "Graph online" : "Graph unavailable";
  if (status.agent_model) $("#modelName").textContent = status.agent_model;
}

function renderStats(status) {
  const mapping = {personStat: "personCount", accountStat: "accountCount", transactionStat: "transactionCount", caseStat: "caseCount", chunkStat: "chunkCount"};
  Object.entries(mapping).forEach(([id, key]) => { $(`#${id}`).textContent = status[key] ?? "—"; });
}

function renderAlerts() {
  const query = $("#alertFilter").value.trim().toLowerCase();
  const alerts = state.alerts.filter((alert) => !query || JSON.stringify(alert).toLowerCase().includes(query));
  $("#alertCount").textContent = alerts.length;
  const list = $("#alertList");
  list.replaceChildren();
  alerts.forEach((alert) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `alert-card ${state.selectedAlert === alert.alertId ? "selected" : ""}`;
    button.setAttribute("aria-pressed", String(state.selectedAlert === alert.alertId));
    const date = formatDate(alert.createdAt);
    button.innerHTML = `<div class="alert-top"><span class="alert-id">${escapeHtml(alert.alertId)}</span><span class="severity ${escapeHtml(alert.severity)}">${escapeHtml(alert.severity)}</span></div><h3>${escapeHtml(alert.title)}</h3><p>${escapeHtml(alert.reason)}</p><div class="alert-meta"><span>${alert.accountIds.length} accounts</span><span>${escapeHtml(alert.status)} · ${date}</span></div>`;
    button.addEventListener("click", () => selectAlert(alert.alertId));
    list.append(button);
  });
}

async function selectAlert(alertId) {
  state.selectedAlert = alertId;
  renderAlerts();
  $("#networkTitle").textContent = `${alertId} · loading circuit`;
  $("#canvasEmpty").hidden = true;
  try {
    const payload = await api(`/api/network/${encodeURIComponent(alertId)}`);
    state.graph = payload.graph;
    state.timeline = payload.timeline;
    $("#networkTitle").textContent = `${payload.alert.alertId} · ${payload.alert.title}`;
    renderGraph(state.graph);
    renderTimeline(state.timeline);
    const defaultQuestion = alertId === "ALRT-1001"
      ? "What supports a benign household explanation, and what remains uncertain?"
      : "Trace the connected accounts and fund flows. What is observed, inferred, and still missing?";
    $("#questionInput").placeholder = defaultQuestion;
  } catch (error) {
    $("#canvasEmpty").hidden = false;
    showToast(error.message);
  }
}

function renderSuggestions() {
  const container = $("#suggestions");
  container.replaceChildren();
  state.examples.slice(0, 4).forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion";
    button.textContent = example;
    button.addEventListener("click", () => { $("#questionInput").value = example; $("#questionInput").focus(); });
    container.append(button);
  });
}

async function runInvestigation(event) {
  event.preventDefault();
  const question = $("#questionInput").value.trim();
  if (!question) return;
  const button = $("#investigateButton");
  button.disabled = true;
  button.textContent = "Assembling evidence…";
  appendConversation("user", "Analyst", question);
  try {
    const payload = await api("/api/investigate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question, alert_id: state.selectedAlert, session_id: state.sessionId}),
    });
    state.sessionId = payload.session_id;
    try { localStorage.setItem("fraud-investigation-session", state.sessionId); } catch { /* storage can be disabled */ }
    $("#threadLabel").textContent = `Graph memory · ${state.sessionId.slice(0, 8)}`;
    appendConversation("agent", "Grounded assessment", payload.report.executive_summary.claim);
    renderInvestigation(payload);
    $("#questionInput").value = "";
  } catch (error) {
    appendConversation("system", "Investigation failed", error.message);
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = "Run investigation <b aria-hidden=\"true\">↗</b>";
  }
}

function appendConversation(type, label, text) {
  const note = document.createElement("div");
  note.className = `note ${type}`;
  const tag = document.createElement("span"); tag.textContent = label;
  const paragraph = document.createElement("p"); paragraph.textContent = text;
  note.append(tag, paragraph);
  $("#conversation").append(note);
  $("#conversation").scrollTop = $("#conversation").scrollHeight;
}

function renderInvestigation(payload) {
  state.evidence = payload.evidence || [];
  if (payload.graph?.nodes?.length) { state.graph = payload.graph; renderGraph(state.graph); }
  if (payload.timeline?.length) { state.timeline = payload.timeline; renderTimeline(state.timeline); }
  renderReport(payload.report);
  renderEvidence(state.evidence);
  renderTrace(payload.trace || []);
  $("#evidenceBadge").textContent = state.evidence.length;
  $("#traceBadge").textContent = (payload.trace || []).length;
  $("#toolMetric").textContent = payload.metrics.tool_calls;
  $("#sourceMetric").textContent = payload.metrics.evidence_count;
  $("#latencyMetric").textContent = `${(payload.metrics.total_ms / 1000).toFixed(1)}s`;
  $("#dossierFooter").hidden = false;
  activateTab("report");
}

function renderReport(report) {
  $("#emptyReport").hidden = true;
  const container = $("#reportContent");
  container.hidden = false;
  container.replaceChildren();
  $("#reportTitle").textContent = report.title;
  const stamp = $("#riskStamp");
  stamp.className = `risk-stamp ${report.risk_level}`;
  stamp.querySelector("strong").textContent = report.risk_level;
  stamp.querySelector("span").textContent = `${report.confidence} confidence`;
  const summary = document.createElement("div"); summary.className = "report-summary";
  summary.append(renderClaim(report.executive_summary)); container.append(summary);
  addReportSection(container, "Risk assessment", [report.risk_assessment], "pattern");
  const sections = [
    ["Observed facts", report.observed_facts, "facts"],
    ["Derived graph patterns", report.derived_patterns, "pattern"],
    ["Typology matches", report.typology_matches, "pattern"],
    ["Benign or contradictory evidence", report.benign_or_contradictory_evidence, "counter"],
    ["Network exposure", report.network_exposure, "facts"],
    ["Recommended human checks", report.recommended_checks, "checks"],
    ["Limitations", report.limitations, "counter"],
  ];
  sections.forEach(([title, claims, className]) => addReportSection(container, title, claims, className));
}

function addReportSection(container, title, claims, className) {
  if (!claims?.length) return;
  const section = document.createElement("section"); section.className = `report-section ${className}`;
  const heading = document.createElement("h3"); heading.textContent = title;
  const list = document.createElement("ul");
  claims.forEach((claim) => { const item = document.createElement("li"); item.append(renderClaim(claim)); list.append(item); });
  section.append(heading, list); container.append(section);
}

function renderClaim(claim) {
  const fragment = document.createDocumentFragment();
  fragment.append(document.createTextNode(claim.claim + " "));
  (claim.evidence_ids || []).forEach((id) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "citation"; button.dataset.evidenceId = id; button.textContent = `[${id}]`;
    button.addEventListener("click", () => revealEvidence(id)); fragment.append(button);
  });
  return fragment;
}

function renderEvidence(evidence) {
  const list = $("#evidenceList"); list.replaceChildren();
  evidence.forEach((record) => {
    const card = document.createElement("article"); card.className = "evidence-card"; card.dataset.evidenceId = record.evidence_id;
    const score = record.score == null ? "" : ` · semantic ${record.score.toFixed(3)}`;
    card.innerHTML = `<header><strong>${escapeHtml(record.title)}</strong><span>[${escapeHtml(record.evidence_id)}]</span></header><p>${escapeHtml(record.content)}</p><footer>${escapeHtml(record.source_type)} · ${escapeHtml(record.source_id)}${score}</footer>`;
    list.append(card);
  });
}

function renderTrace(trace) {
  const list = $("#traceList"); list.replaceChildren();
  trace.forEach((step) => {
    const item = document.createElement("li");
    item.innerHTML = `<strong>${escapeHtml(step.tool)} · ${escapeHtml(step.status)}</strong><p>${escapeHtml(step.summary)} · ${step.elapsed_ms} ms · ${(step.evidence_ids || []).join(", ") || "no evidence"}</p><code>${escapeHtml(JSON.stringify(step.arguments))}</code>`;
    list.append(item);
  });
}

function activateTab(name) {
  $$(".tab").forEach((button) => { const active = button.dataset.tab === name; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); });
  $$(".tab-panel").forEach((panel) => { const active = panel.id === `${name}Panel`; panel.hidden = !active; panel.classList.toggle("active", active); });
}

function revealEvidence(id) {
  activateTab("evidence");
  requestAnimationFrame(() => {
    const card = document.querySelector(`.evidence-card[data-evidence-id="${CSS.escape(id)}"]`);
    if (!card) return;
    card.classList.remove("highlight"); void card.offsetWidth; card.classList.add("highlight");
    card.scrollIntoView({behavior: "smooth", block: "center"});
  });
}

function renderGraph(graph) {
  const viewport = $("#networkViewport"); viewport.replaceChildren();
  const unique = new Map((graph.nodes || []).filter((node) => node?.id).map((node) => [String(node.id), node]));
  const nodes = [...unique.values()];
  $("#canvasEmpty").hidden = nodes.length > 0;
  const positions = layoutNodes(nodes);
  (graph.edges || []).forEach((edge) => {
    const source = positions.get(String(edge.source)); const target = positions.get(String(edge.target));
    if (!source || !target) return;
    const path = document.createElementNS(svgNS, "path");
    const money = ["TRANSFERRED", "PAID"].includes(edge.relationship);
    path.setAttribute("class", `graph-edge ${money ? "money" : ""}`);
    const curve = Math.max(30, Math.abs(target.x - source.x) * .35);
    path.setAttribute("d", `M${source.x + 58},${source.y} C${source.x + curve},${source.y} ${target.x - curve},${target.y} ${target.x - 58},${target.y}`);
    viewport.append(path);
    if (money) {
      const label = document.createElementNS(svgNS, "text"); label.setAttribute("class", "edge-label");
      label.setAttribute("x", String((source.x + target.x) / 2)); label.setAttribute("y", String((source.y + target.y) / 2 - 5));
      label.textContent = edge.amount != null ? `£${Number(edge.amount).toLocaleString()}` : edge.relationship;
      viewport.append(label);
    }
  });
  nodes.forEach((node) => {
    const position = positions.get(String(node.id));
    const group = document.createElementNS(svgNS, "g"); group.setAttribute("class", `node ${node.type || "unknown"}`); group.setAttribute("transform", `translate(${position.x},${position.y})`); group.setAttribute("tabindex", "0"); group.setAttribute("role", "button"); group.setAttribute("aria-label", `${node.type || "entity"} ${node.label || node.id}`);
    const rect = document.createElementNS(svgNS, "rect"); rect.setAttribute("x", "-58"); rect.setAttribute("y", "-18"); rect.setAttribute("width", "116"); rect.setAttribute("height", "36");
    const text = document.createElementNS(svgNS, "text"); text.setAttribute("y", "4"); text.textContent = truncate(node.label || node.id, 17);
    group.append(rect, text); group.addEventListener("click", (event) => { event.stopPropagation(); inspectNode(node, group); }); group.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); inspectNode(node, group); } });
    viewport.append(group);
  });
  applyTransform();
}

function layoutNodes(nodes) {
  const lane = {person: 130, device: 360, phone: 360, address: 360, alert: 555, account: 610, merchant: 900};
  const groups = new Map();
  nodes.forEach((node) => { const x = lane[node.type] ?? 610; if (!groups.has(x)) groups.set(x, []); groups.get(x).push(node); });
  const positions = new Map();
  groups.forEach((items, x) => {
    items.sort((a, b) => String(a.id).localeCompare(String(b.id)));
    const gap = Math.min(76, 450 / Math.max(items.length - 1, 1));
    const start = 72 + Math.max(0, (440 - gap * (items.length - 1)) / 2);
    items.forEach((node, index) => positions.set(String(node.id), {x, y: node.type === "alert" ? 48 : start + index * gap}));
  });
  return positions;
}

function inspectNode(node, group) {
  $$(".node.selected").forEach((item) => item.classList.remove("selected")); group.classList.add("selected");
  const inspector = $("#nodeInspector"); inspector.hidden = false; inspector.replaceChildren();
  const close = document.createElement("button"); close.type = "button"; close.textContent = "×"; close.setAttribute("aria-label", "Close inspector"); close.addEventListener("click", () => { inspector.hidden = true; group.classList.remove("selected"); });
  const heading = document.createElement("h3"); heading.textContent = node.label || node.id; inspector.append(close, heading);
  Object.entries(node).filter(([key]) => !["label"].includes(key)).forEach(([key, value]) => { const p = document.createElement("p"); p.textContent = `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`; inspector.append(p); });
}

function renderTimeline(events) {
  const strip = $("#timelineStrip"); strip.replaceChildren();
  if (!events?.length) { const empty = document.createElement("span"); empty.className = "timeline-empty"; empty.textContent = "No observed transactions in this evidence set."; strip.append(empty); $("#timelineSummary").textContent = "No observed flows"; return; }
  $("#timelineSummary").textContent = `${events.length} observed events · chronological`;
  [...events].sort((a, b) => String(a.occurredAt).localeCompare(String(b.occurredAt))).forEach((event) => {
    const card = document.createElement("article"); card.className = "timeline-event";
    const time = document.createElement("time"); time.dateTime = event.occurredAt; time.textContent = formatDate(event.occurredAt, true);
    const label = document.createElement("strong"); label.textContent = event.label;
    const detail = document.createElement("span"); detail.textContent = event.detail || event.eventId;
    card.append(time, label, detail); strip.append(card);
  });
}

function onGraphWheel(event) { event.preventDefault(); zoomBy(event.deltaY < 0 ? 1.1 : .9); }
function zoomBy(factor) { state.transform.scale = clamp(state.transform.scale * factor, .55, 2.25); applyTransform(); }
function resetGraphView() { state.transform = {x: 0, y: 0, scale: 1}; applyTransform(); }
function onGraphPointerDown(event) { if (event.target.closest(".node")) return; state.drag = {x: event.clientX, y: event.clientY, startX: state.transform.x, startY: state.transform.y}; $("#networkSvg").classList.add("dragging"); $("#networkSvg").setPointerCapture?.(event.pointerId); }
function onGraphPointerMove(event) { if (!state.drag) return; state.transform.x = state.drag.startX + event.clientX - state.drag.x; state.transform.y = state.drag.startY + event.clientY - state.drag.y; applyTransform(); }
function onGraphPointerUp() { state.drag = null; $("#networkSvg").classList.remove("dragging"); }
function applyTransform() { const {x, y, scale} = state.transform; $("#networkViewport").setAttribute("transform", `translate(${x} ${y}) scale(${scale})`); }

function setupResizer(handle, property, min, max, reverse) {
  const root = document.documentElement;
  const change = (delta) => {
    const current = parseFloat(getComputedStyle(root).getPropertyValue(property));
    root.style.setProperty(property, `${clamp(current + (reverse ? -delta : delta), min, max)}px`);
  };
  handle.addEventListener("pointerdown", (event) => { event.preventDefault(); handle.classList.add("active"); document.body.classList.add("resizing"); const start = event.clientX; const current = parseFloat(getComputedStyle(root).getPropertyValue(property)); const move = (moveEvent) => root.style.setProperty(property, `${clamp(current + (reverse ? start - moveEvent.clientX : moveEvent.clientX - start), min, max)}px`); const stop = () => { handle.classList.remove("active"); document.body.classList.remove("resizing"); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); }; window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop); });
  handle.addEventListener("keydown", (event) => { if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return; event.preventDefault(); change(event.key === "ArrowRight" ? 12 : -12); });
  handle.addEventListener("dblclick", () => root.style.removeProperty(property));
}

async function resetThread() {
  if (state.sessionId) {
    try { await api(`/api/sessions/${encodeURIComponent(state.sessionId)}`, {method: "DELETE"}); } catch (error) { showToast(error.message); }
  }
  state.sessionId = null; $("#threadLabel").textContent = "New graph memory";
  try { localStorage.removeItem("fraud-investigation-session"); } catch { /* storage can be disabled */ }
  $("#conversation").innerHTML = '<div class="note system"><span>Grounding rule</span><p>Observed facts, graph patterns, typology matches, and assessment remain separate.</p></div>';
  showToast("Investigation memory cleared");
}

function formatDate(value, withSeconds = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: withSeconds ? "2-digit" : undefined, hour12: false}).format(date);
}
function escapeHtml(value) { const element = document.createElement("span"); element.textContent = String(value ?? ""); return element.innerHTML; }
function truncate(value, length) { value = String(value ?? ""); return value.length > length ? `${value.slice(0, length - 1)}…` : value; }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function loadSessionId() { try { return localStorage.getItem("fraud-investigation-session"); } catch { return null; } }
let toastTimer;
function showToast(message) { clearTimeout(toastTimer); const toast = $("#toast"); toast.textContent = message; toast.classList.add("show"); toastTimer = setTimeout(() => toast.classList.remove("show"), 3200); }
