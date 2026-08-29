"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

const TOPOLOGY_GEOMETRY = Object.freeze({
  viewBoxWidth: 940,
  viewBoxHeight: 470,
  nodeWidth: 144,
  nodeHeight: 54,
  horizontalPadding: 12,
});

const TOPOLOGY_BANDS = Object.freeze([
  Object.freeze({ id: "client", start: 0, end: 0.34, includes: (layer) => layer === 0 }),
  Object.freeze({ id: "core", start: 0.34, end: 0.68, includes: (layer) => layer === 1 || layer === 2 }),
  Object.freeze({ id: "dependencies", start: 0.68, end: 1, includes: (layer) => layer >= 3 }),
]);

const state = {
  status: null,
  meta: { incidents: [], services: [], examples: [] },
  graph: { nodes: [], edges: [] },
  timeline: [],
  sessionId: null,
  result: null,
  evidenceNodeIds: new Set(),
  evidenceEdgeKeys: new Set(),
  transform: { x: 0, y: 0, scale: 1 },
  dragging: false,
  dragPoint: null,
  resize: null,
  panelWidths: { caseFile: null, dossier: null },
};

const resizeLimits = {
  caseFileMin: 260,
  dossierMin: 280,
  topologyMin: 480,
  timelineMin: 150,
  topologyHeightMin: 280,
  keyboardStep: 16,
};

const desktopColumns = window.matchMedia("(min-width: 1121px)");

const elements = {
  fieldroom: document.querySelector(".fieldroom"),
  caseFilePanel: document.querySelector("#caseFilePanel"),
  topologyPanel: document.querySelector("#topologyPanel"),
  dossierPanel: document.querySelector("#dossierPanel"),
  caseFileResizer: document.querySelector("#caseFileResizer"),
  dossierResizer: document.querySelector("#dossierResizer"),
  timelinePanel: document.querySelector("#timelinePanel"),
  timelineResizer: document.querySelector("#timelineResizer"),
  deskHeader: document.querySelector(".desk-header"),
  deskStats: document.querySelector(".desk-stats"),
  statusLight: document.querySelector("#statusLight"),
  statusText: document.querySelector("#statusText"),
  modelName: document.querySelector("#modelName"),
  incidentSelect: document.querySelector("#incidentSelect"),
  caseSummary: document.querySelector("#caseSummary"),
  promptSuggestions: document.querySelector("#promptSuggestions"),
  form: document.querySelector("#investigationForm"),
  questionInput: document.querySelector("#questionInput"),
  investigateButton: document.querySelector("#investigateButton"),
  conversationLog: document.querySelector("#conversationLog"),
  newSessionButton: document.querySelector("#newSessionButton"),
  topologySvg: document.querySelector("#topologySvg"),
  topologyViewport: document.querySelector("#topologyViewport"),
  nodeInspector: document.querySelector("#nodeInspector"),
  timelineTrack: document.querySelector("#timelineTrack"),
  timelineRange: document.querySelector("#timelineRange"),
  zoomInButton: document.querySelector("#zoomInButton"),
  zoomOutButton: document.querySelector("#zoomOutButton"),
  resetGraphButton: document.querySelector("#resetGraphButton"),
  serviceCount: document.querySelector("#serviceCount"),
  incidentCount: document.querySelector("#incidentCount"),
  deploymentCount: document.querySelector("#deploymentCount"),
  chunkCount: document.querySelector("#chunkCount"),
  reportTitle: document.querySelector("#reportTitle"),
  reportEmpty: document.querySelector("#reportEmpty"),
  reportContent: document.querySelector("#reportContent"),
  evidenceList: document.querySelector("#evidenceList"),
  traceList: document.querySelector("#traceList"),
  evidenceBadge: document.querySelector("#evidenceBadge"),
  traceBadge: document.querySelector("#traceBadge"),
  copyReportButton: document.querySelector("#copyReportButton"),
  dossierMetrics: document.querySelector("#dossierMetrics"),
  toolCallMetric: document.querySelector("#toolCallMetric"),
  evidenceMetric: document.querySelector("#evidenceMetric"),
  latencyMetric: document.querySelector("#latencyMetric"),
  toast: document.querySelector("#toast"),
};

let topologyRenderFrame = null;

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function currentPanelWidths() {
  return {
    caseFile: elements.caseFilePanel.getBoundingClientRect().width,
    dossier: elements.dossierPanel.getBoundingClientRect().width,
  };
}

function columnBounds(widths = currentPanelWidths()) {
  const total = elements.fieldroom.getBoundingClientRect().width;
  return {
    total,
    caseFileMax: total - widths.dossier - resizeLimits.topologyMin,
    dossierMax: total - widths.caseFile - resizeLimits.topologyMin,
  };
}

function applyColumnWidths(caseFileWidth, dossierWidth, resizedPane = null) {
  const total = elements.fieldroom.getBoundingClientRect().width;
  let caseFile;
  let dossier;
  if (resizedPane === "caseFile") {
    dossier = clamp(dossierWidth, resizeLimits.dossierMin, total - resizeLimits.caseFileMin - resizeLimits.topologyMin);
    caseFile = clamp(caseFileWidth, resizeLimits.caseFileMin, total - dossier - resizeLimits.topologyMin);
  } else {
    caseFile = clamp(caseFileWidth, resizeLimits.caseFileMin, total - resizeLimits.dossierMin - resizeLimits.topologyMin);
    dossier = clamp(dossierWidth, resizeLimits.dossierMin, total - caseFile - resizeLimits.topologyMin);
  }
  elements.fieldroom.style.setProperty("--case-file-width", `${Math.round(caseFile)}px`);
  elements.fieldroom.style.setProperty("--dossier-width", `${Math.round(dossier)}px`);
  state.panelWidths = { caseFile, dossier };
  updateResizeValues();
  scheduleTopologyRender();
}

function timelineBounds() {
  const graphHeight = elements.topologyPanel.getBoundingClientRect().height;
  const fixedHeight = elements.deskHeader.getBoundingClientRect().height
    + elements.deskStats.getBoundingClientRect().height;
  return {
    minimum: resizeLimits.timelineMin,
    maximum: graphHeight - fixedHeight - resizeLimits.topologyHeightMin,
  };
}

function applyTimelineHeight(height) {
  const bounds = timelineBounds();
  const nextHeight = clamp(height, bounds.minimum, bounds.maximum);
  elements.topologyPanel.style.setProperty("--timeline-panel-height", `${Math.round(nextHeight)}px`);
  updateResizeValues();
  scheduleTopologyRender();
}

function updateResizeValues() {
  const widths = currentPanelWidths();
  const bounds = columnBounds(widths);
  const topologyWidth = elements.topologyPanel.getBoundingClientRect().width;
  const timelineHeight = elements.timelinePanel.getBoundingClientRect().height;
  const timelineRange = timelineBounds();

  elements.caseFileResizer.setAttribute("aria-valuemin", String(resizeLimits.caseFileMin));
  elements.caseFileResizer.setAttribute("aria-valuemax", String(Math.max(resizeLimits.caseFileMin, Math.round(bounds.caseFileMax))));
  elements.caseFileResizer.setAttribute("aria-valuenow", String(Math.round(widths.caseFile)));
  elements.caseFileResizer.setAttribute("aria-valuetext", `Investigation Pane ${Math.round(widths.caseFile)} pixels, Service topology overview ${Math.round(topologyWidth)} pixels`);

  const dossierDivider = bounds.total - widths.dossier;
  elements.dossierResizer.setAttribute("aria-valuemin", String(Math.round(widths.caseFile + resizeLimits.topologyMin)));
  elements.dossierResizer.setAttribute("aria-valuemax", String(Math.round(bounds.total - resizeLimits.dossierMin)));
  elements.dossierResizer.setAttribute("aria-valuenow", String(Math.round(dossierDivider)));
  elements.dossierResizer.setAttribute("aria-valuetext", `Service topology overview ${Math.round(topologyWidth)} pixels, Agent Dossier ${Math.round(widths.dossier)} pixels`);

  const timelineTop = elements.timelinePanel.getBoundingClientRect().top
    - elements.topologyPanel.getBoundingClientRect().top;
  elements.timelineResizer.setAttribute("aria-valuemin", String(Math.round(elements.deskHeader.getBoundingClientRect().height + resizeLimits.topologyHeightMin)));
  elements.timelineResizer.setAttribute("aria-valuemax", String(Math.round(elements.topologyPanel.getBoundingClientRect().height - elements.deskStats.getBoundingClientRect().height - resizeLimits.timelineMin)));
  elements.timelineResizer.setAttribute("aria-valuenow", String(Math.round(timelineTop)));
  elements.timelineResizer.setAttribute("aria-valuetext", `Temporal Context ${Math.round(timelineHeight)} pixels high; minimum ${timelineRange.minimum}, maximum ${Math.max(timelineRange.minimum, Math.round(timelineRange.maximum))}`);
}

function beginResize(kind, event) {
  if (event.button !== 0) return;
  if (kind !== "timeline" && !desktopColumns.matches) return;
  event.preventDefault();
  event.currentTarget.focus();
  const widths = currentPanelWidths();
  state.resize = {
    kind,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startCaseFile: widths.caseFile,
    startDossier: widths.dossier,
    startTimeline: elements.timelinePanel.getBoundingClientRect().height,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
  event.currentTarget.classList.add("active");
  document.body.classList.add(kind === "timeline" ? "resizing-timeline" : "resizing-columns");
}

function continueResize(event) {
  if (!state.resize || event.pointerId !== state.resize.pointerId) return;
  const deltaX = event.clientX - state.resize.startX;
  const deltaY = event.clientY - state.resize.startY;
  if (state.resize.kind === "caseFile") {
    applyColumnWidths(state.resize.startCaseFile + deltaX, state.resize.startDossier, "caseFile");
  } else if (state.resize.kind === "dossier") {
    applyColumnWidths(state.resize.startCaseFile, state.resize.startDossier - deltaX, "dossier");
  } else {
    applyTimelineHeight(state.resize.startTimeline - deltaY);
  }
}

function endResize(event) {
  if (!state.resize || (event.pointerId !== undefined && event.pointerId !== state.resize.pointerId)) return;
  const handle = state.resize.kind === "caseFile"
    ? elements.caseFileResizer
    : state.resize.kind === "dossier"
      ? elements.dossierResizer
      : elements.timelineResizer;
  if (handle.hasPointerCapture?.(state.resize.pointerId)) {
    handle.releasePointerCapture(state.resize.pointerId);
  }
  handle.classList.remove("active");
  document.body.classList.remove("resizing-columns", "resizing-timeline");
  state.resize = null;
}

function resizeWithKeyboard(kind, event) {
  const widths = currentPanelWidths();
  const step = event.shiftKey ? resizeLimits.keyboardStep * 2 : resizeLimits.keyboardStep;
  if (kind === "timeline" && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    event.preventDefault();
    applyTimelineHeight(elements.timelinePanel.getBoundingClientRect().height + (event.key === "ArrowUp" ? step : -step));
  } else if (kind === "caseFile" && desktopColumns.matches && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
    event.preventDefault();
    applyColumnWidths(widths.caseFile + (event.key === "ArrowRight" ? step : -step), widths.dossier, "caseFile");
  } else if (kind === "dossier" && desktopColumns.matches && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
    event.preventDefault();
    applyColumnWidths(widths.caseFile, widths.dossier + (event.key === "ArrowLeft" ? step : -step), "dossier");
  }
}

function resetResize(kind) {
  if (kind === "caseFile") {
    elements.fieldroom.style.removeProperty("--case-file-width");
    state.panelWidths.caseFile = null;
  } else if (kind === "dossier") {
    elements.fieldroom.style.removeProperty("--dossier-width");
    state.panelWidths.dossier = null;
  } else {
    elements.topologyPanel.style.removeProperty("--timeline-panel-height");
  }
  window.requestAnimationFrame(updateResizeValues);
}

function syncResizableLayout() {
  if (desktopColumns.matches && (state.panelWidths.caseFile !== null || state.panelWidths.dossier !== null)) {
    const widths = currentPanelWidths();
    applyColumnWidths(
      state.panelWidths.caseFile ?? widths.caseFile,
      state.panelWidths.dossier ?? widths.dossier,
    );
  }
  const currentTimelineHeight = elements.timelinePanel.getBoundingClientRect().height;
  const timelineRange = timelineBounds();
  if (currentTimelineHeight > timelineRange.maximum) applyTimelineHeight(currentTimelineHeight);
  updateResizeValues();
  scheduleTopologyRender();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message, type = "info") {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", type === "error");
  elements.toast.classList.add("visible");
  window.setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function formatTime(value) {
  if (!value) return "—";
  const date = parseTimestamp(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date) + " UTC";
}

function parseTimestamp(value) {
  // Neo4j can serialize zoned datetimes as `...Z[UTC]`; JavaScript Date
  // understands the ISO offset but not the bracketed IANA zone suffix.
  return new Date(String(value).replace(/\[[^\]]+\]$/, ""));
}

function setRuntimeStatus(status) {
  state.status = status;
  elements.statusLight.className = `status-light ${status.ready ? "ready" : "error"}`;
  elements.statusText.textContent = status.ready ? "Graph ready" : "Ingestion required";
  elements.modelName.textContent = status.agent_model || "Agent unavailable";
  elements.serviceCount.textContent = status.serviceCount ?? "—";
  elements.incidentCount.textContent = status.incidentCount ?? "—";
  elements.deploymentCount.textContent = status.deploymentCount ?? "—";
  elements.chunkCount.textContent = status.chunkCount ?? "—";
}

function populateMeta(meta) {
  state.meta = meta;
  elements.incidentSelect.innerHTML = meta.incidents
    .map((incident) => `<option value="${escapeHtml(incident.incidentId)}">${escapeHtml(incident.incidentId)} · ${escapeHtml(incident.title)}</option>`)
    .join("");
  elements.promptSuggestions.innerHTML = meta.examples
    .slice(0, 4)
    .map((example, index) => `<button class="suggestion-button" type="button" data-example-index="${index}" title="${escapeHtml(example)}">${escapeHtml(example)}</button>`)
    .join("");
  const firstInvestigating = meta.incidents.find((incident) => incident.status === "investigating");
  if (firstInvestigating) elements.incidentSelect.value = firstInvestigating.incidentId;
  renderCaseSummary();
}

function selectedIncident() {
  return state.meta.incidents.find(
    (incident) => incident.incidentId === elements.incidentSelect.value,
  );
}

function renderCaseSummary() {
  const incident = selectedIncident();
  if (!incident) {
    elements.caseSummary.textContent = "No incidents are available.";
    return;
  }
  elements.caseSummary.innerHTML = `
    <p><strong>${escapeHtml(incident.severity)}</strong> · ${escapeHtml(incident.status)} · ${escapeHtml(formatTime(incident.startedAt))}</p>
    <p>${escapeHtml(incident.summary)}</p>
    <div class="case-chips">${incident.serviceIds.map((serviceId) => `<span class="case-chip">${escapeHtml(serviceId)}</span>`).join("")}</div>
  `;
}

async function loadTopology(incidentId) {
  const payload = await api(`/api/topology${incidentId ? `?incident_id=${encodeURIComponent(incidentId)}` : ""}`);
  state.graph = payload.graph;
  state.timeline = payload.timeline;
  state.transform = { x: 0, y: 0, scale: 1 };
  renderTopology();
  renderTimeline(state.timeline);
}

function createSvg(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
  return node;
}

function normalizedTopologyLayer(value) {
  const layer = Number(value ?? 0);
  return Number.isFinite(layer) ? Math.max(0, Math.trunc(layer)) : 0;
}

function topologyBandForLayer(layer) {
  return TOPOLOGY_BANDS.find((band) => band.includes(layer)) ?? TOPOLOGY_BANDS[0];
}

function topologyBandViewBoxSpan(band) {
  const rect = elements.topologySvg.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return {
      start: band.start * TOPOLOGY_GEOMETRY.viewBoxWidth,
      end: band.end * TOPOLOGY_GEOMETRY.viewBoxWidth,
    };
  }
  const scale = Math.min(
    rect.width / TOPOLOGY_GEOMETRY.viewBoxWidth,
    rect.height / TOPOLOGY_GEOMETRY.viewBoxHeight,
  );
  const horizontalOffset = (rect.width - TOPOLOGY_GEOMETRY.viewBoxWidth * scale) / 2;
  return {
    start: clamp((band.start * rect.width - horizontalOffset) / scale, 0, TOPOLOGY_GEOMETRY.viewBoxWidth),
    end: clamp((band.end * rect.width - horizontalOffset) / scale, 0, TOPOLOGY_GEOMETRY.viewBoxWidth),
  };
}

function topologyLayerCenters(layers) {
  const centers = new Map();
  const halfNodeWidth = TOPOLOGY_GEOMETRY.nodeWidth / 2;
  TOPOLOGY_BANDS.forEach((band) => {
    const bandLayers = layers.filter((layer) => band.includes(layer)).sort((a, b) => a - b);
    if (!bandLayers.length) return;
    const { start: bandStart, end: bandEnd } = topologyBandViewBoxSpan(band);
    if (bandLayers.length === 1) {
      centers.set(bandLayers[0], (bandStart + bandEnd) / 2);
      return;
    }
    const firstCenter = bandStart + halfNodeWidth + TOPOLOGY_GEOMETRY.horizontalPadding;
    const lastCenter = bandEnd - halfNodeWidth - TOPOLOGY_GEOMETRY.horizontalPadding;
    const step = (lastCenter - firstCenter) / (bandLayers.length - 1);
    bandLayers.forEach((layer, index) => centers.set(layer, firstCenter + step * index));
  });
  return centers;
}

function scheduleTopologyRender() {
  if (!state.graph.nodes.length || topologyRenderFrame !== null) return;
  topologyRenderFrame = window.requestAnimationFrame(() => {
    topologyRenderFrame = null;
    renderTopology();
  });
}

function nodePositions(nodes) {
  const byLayer = new Map();
  nodes.forEach((node) => {
    const layer = normalizedTopologyLayer(node.layer);
    if (!byLayer.has(layer)) byLayer.set(layer, []);
    byLayer.get(layer).push(node);
  });
  const layerCenters = topologyLayerCenters([...byLayer.keys()]);
  const positions = new Map();
  [...byLayer.entries()].forEach(([layer, layerNodes]) => {
    layerNodes.sort((a, b) => a.label.localeCompare(b.label));
    const span = Math.min(360, Math.max(100, (layerNodes.length - 1) * 104));
    const start = 235 - span / 2;
    layerNodes.forEach((node, index) => {
      positions.set(node.id, {
        x: layerCenters.get(layer),
        y: start + (layerNodes.length === 1 ? span / 2 : index * (span / (layerNodes.length - 1))),
      });
    });
  });
  return positions;
}

function edgeKey(edge) {
  return `${edge.source}|${edge.target}|${edge.relationship}`;
}

function renderTopology() {
  const viewport = elements.topologyViewport;
  viewport.replaceChildren();
  const positions = nodePositions(state.graph.nodes);
  const halfNodeWidth = TOPOLOGY_GEOMETRY.nodeWidth / 2;
  const halfNodeHeight = TOPOLOGY_GEOMETRY.nodeHeight / 2;

  state.graph.edges.forEach((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return;
    const line = createSvg("line", {
      x1: source.x + halfNodeWidth,
      y1: source.y,
      x2: target.x - halfNodeWidth,
      y2: target.y,
      class: [
        "topology-edge",
        edge.criticality === "critical" ? "critical" : "",
        state.evidenceEdgeKeys.has(edgeKey(edge)) ? "evidence" : "",
      ].filter(Boolean).join(" "),
    });
    viewport.append(line);
  });

  state.graph.nodes.forEach((node) => {
    const position = positions.get(node.id);
    if (!position) return;
    const group = createSvg("g", {
      class: [
        "service-node",
        node.impacted ? "impacted" : "",
        state.evidenceNodeIds.has(node.id) ? "evidence" : "",
      ].filter(Boolean).join(" "),
      transform: `translate(${position.x - halfNodeWidth} ${position.y - halfNodeHeight})`,
      tabindex: "0",
      role: "button",
      "aria-label": `${node.label}, tier ${node.tier}, owned by ${node.team}`,
      "data-node-id": node.id,
      "data-topology-band": topologyBandForLayer(normalizedTopologyLayer(node.layer)).id,
    });
    group.append(createSvg("rect", { width: TOPOLOGY_GEOMETRY.nodeWidth, height: TOPOLOGY_GEOMETRY.nodeHeight, rx: 5 }));
    group.append(createSvg("rect", { class: "node-accent", width: 5, height: TOPOLOGY_GEOMETRY.nodeHeight, rx: 2 }));
    const title = createSvg("text", { x: 15, y: 22 });
    title.textContent = node.label;
    const meta = createSvg("text", { class: "node-meta", x: 15, y: 39 });
    meta.textContent = `T${node.tier} · ${node.team}`;
    group.append(title, meta);
    group.addEventListener("click", () => inspectNode(node, group));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        inspectNode(node, group);
      }
    });
    viewport.append(group);
  });
  applyTransform();
}

function inspectNode(node, group) {
  elements.topologyViewport.querySelectorAll(".service-node").forEach((item) => item.classList.remove("highlighted"));
  group.classList.add("highlighted");
  const outgoing = state.graph.edges.filter((edge) => edge.source === node.id).length;
  const incoming = state.graph.edges.filter((edge) => edge.target === node.id).length;
  elements.nodeInspector.innerHTML = `<strong>${escapeHtml(node.label)}</strong><span>${escapeHtml(node.id)} · tier ${escapeHtml(node.tier)}</span><p>${escapeHtml(node.team)} owns this service. ${outgoing} dependencies, ${incoming} dependants.</p>`;
  elements.nodeInspector.hidden = false;
}

function applyTransform() {
  const { x, y, scale } = state.transform;
  elements.topologyViewport.setAttribute("transform", `translate(${x} ${y}) scale(${scale})`);
}

function zoomGraph(delta) {
  state.transform.scale = Math.max(0.65, Math.min(1.75, state.transform.scale + delta));
  applyTransform();
}

function renderTimeline(events) {
  elements.timelineTrack.replaceChildren();
  if (!events.length) {
    elements.timelineRange.textContent = "No temporal events for this case.";
    return;
  }
  const times = events.map((event) => parseTimestamp(event.occurredAt).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const range = Math.max(max - min, 1);
  elements.timelineRange.textContent = `${formatTime(new Date(min).toISOString())} → ${formatTime(new Date(max).toISOString())}`;
  const placed = [];
  events.forEach((event, index) => {
    const x = 7 + ((times[index] - min) / range) * 86;
    const occupiedLanes = new Set(
      placed.filter((item) => Math.abs(item.x - x) < 13).map((item) => item.lane),
    );
    let lane = 0;
    while (occupiedLanes.has(lane)) lane += 1;
    placed.push({ x, lane });
    const button = document.createElement("button");
    button.type = "button";
    button.className = `timeline-event ${event.type}`;
    button.style.left = `${x}%`;
    button.style.setProperty("--timeline-lane", `${lane * 30}px`);
    button.title = `${event.label} · ${event.detail || ""}`;
    button.innerHTML = `<time>${escapeHtml(formatTime(event.occurredAt).replace(" UTC", ""))}</time><strong>${escapeHtml(event.label)}</strong>`;
    button.addEventListener("click", () => {
      elements.timelineTrack.querySelectorAll(".timeline-event").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      if (event.serviceId) highlightService(event.serviceId);
    });
    elements.timelineTrack.append(button);
  });
}

function highlightService(serviceId) {
  const group = elements.topologyViewport.querySelector(`[data-node-id="${CSS.escape(serviceId)}"]`);
  if (!group) return;
  elements.topologyViewport.querySelectorAll(".service-node").forEach((item) => item.classList.remove("highlighted"));
  group.classList.add("highlighted");
}

function addMessage(role, text) {
  const message = document.createElement("article");
  message.className = `message message-${role}`;
  message.innerHTML = `<span class="message-label">${role === "user" ? "Operator" : "Investigator"}</span><p>${escapeHtml(text)}</p>`;
  elements.conversationLog.append(message);
  elements.conversationLog.scrollTop = elements.conversationLog.scrollHeight;
}

function claimHtml(claim) {
  const citations = (claim.evidence_ids || [])
    .map((id) => `<button type="button" class="citation-link" data-evidence-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`)
    .join("");
  return `${escapeHtml(claim.claim)} ${citations}`;
}

function claimList(title, claims, extraClass = "") {
  if (!claims?.length) return "";
  return `<section class="report-section ${extraClass}"><h3>${escapeHtml(title)}</h3><ul class="claim-list">${claims.map((claim) => `<li>${claimHtml(claim)}</li>`).join("")}</ul></section>`;
}

function renderReport(result) {
  state.result = result;
  const report = result.report;
  elements.reportTitle.textContent = report.title;
  elements.reportEmpty.hidden = true;
  elements.reportContent.hidden = false;
  elements.reportContent.innerHTML = `
    <div class="confidence-row"><span class="eyebrow">Grounded assessment</span><span class="confidence-pill ${escapeHtml(report.confidence)}">${escapeHtml(report.confidence)} confidence</span></div>
    <p class="report-lede">${claimHtml(report.summary)}</p>
    <section class="report-section"><h3>Leading hypothesis</h3><div class="hypothesis-card">${claimHtml(report.leading_hypothesis)}</div></section>
    ${claimList("Supporting evidence", report.supporting_evidence)}
    ${claimList("Contradicting evidence", report.contradicting_evidence, "contradictions")}
    ${claimList("Blast radius", report.blast_radius)}
    ${claimList("Next safe checks", report.next_checks)}
    ${claimList("Limitations", report.limitations, "contradictions")}
  `;
  renderEvidence(result.evidence);
  renderTrace(result.trace);
  elements.evidenceBadge.textContent = result.evidence.length;
  elements.traceBadge.textContent = result.trace.length;
  elements.toolCallMetric.textContent = result.metrics.tool_calls;
  elements.evidenceMetric.textContent = result.metrics.evidence_count;
  elements.latencyMetric.textContent = `${(result.metrics.total_ms / 1000).toFixed(1)}s`;
  elements.dossierMetrics.hidden = false;
  elements.copyReportButton.disabled = false;

  state.evidenceNodeIds = new Set((result.graph.nodes || []).map((node) => node.id));
  state.evidenceEdgeKeys = new Set((result.graph.edges || []).map(edgeKey));
  renderTopology();
  if (result.timeline?.length) renderTimeline(result.timeline);
}

function renderEvidence(records) {
  elements.evidenceList.innerHTML = records.map((record) => `
    <article class="evidence-card ${escapeHtml(record.kind)}" id="evidence-${escapeHtml(record.evidence_id)}">
      <header><h3>${escapeHtml(record.title)}</h3><span class="evidence-id">${escapeHtml(record.evidence_id)}</span></header>
      <p>${escapeHtml(record.content)}</p>
      <div class="evidence-meta"><span>${escapeHtml(record.source_type)}</span>${record.occurred_at ? `<span>${escapeHtml(formatTime(record.occurred_at))}</span>` : ""}${record.score !== null ? `<span>semantic ${Number(record.score).toFixed(3)}</span>` : ""}</div>
    </article>
  `).join("");
}

function renderTrace(trace) {
  elements.traceList.innerHTML = trace.map((item) => `
    <li class="trace-item">
      <h3>${escapeHtml(item.tool)}</h3>
      <p>${escapeHtml(item.summary)}</p>
      <span class="trace-meta">${escapeHtml(item.status)} · ${escapeHtml(item.elapsed_ms)} ms · ${escapeHtml(item.evidence_ids.join(", ") || "no new evidence")}</span>
    </li>
  `).join("");
}

function activateTab(name) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const active = panel.id === `${name}Panel`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function focusEvidence(evidenceId) {
  activateTab("evidence");
  const card = document.querySelector(`#evidence-${CSS.escape(evidenceId)}`);
  if (!card) return;
  card.scrollIntoView({ block: "center", behavior: "smooth" });
  card.classList.remove("flash");
  window.requestAnimationFrame(() => card.classList.add("flash"));
}

function setLoading(loading) {
  elements.investigateButton.disabled = loading;
  elements.questionInput.disabled = loading;
  elements.investigateButton.querySelector("span").textContent = loading ? "Investigating…" : "Investigate";
}

async function investigate(question) {
  addMessage("user", question);
  setLoading(true);
  try {
    const result = await api("/api/investigate", {
      method: "POST",
      body: JSON.stringify({ question, session_id: state.sessionId }),
    });
    state.sessionId = result.session_id;
    renderReport(result);
    addMessage("agent", `${result.report.summary.claim} (${result.report.confidence} confidence; ${result.metrics.tool_calls} tool calls.)`);
  } catch (error) {
    addMessage("agent", `Investigation stopped: ${error.message}`);
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function clearSession() {
  if (state.sessionId) {
    try {
      await api(`/api/sessions/${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
    } catch (_error) {
      // A local UI reset remains useful if the process-local session expired.
    }
  }
  state.sessionId = null;
  state.result = null;
  state.evidenceNodeIds.clear();
  state.evidenceEdgeKeys.clear();
  elements.reportTitle.textContent = "Awaiting investigation";
  elements.reportEmpty.hidden = false;
  elements.reportContent.hidden = true;
  elements.reportContent.replaceChildren();
  elements.evidenceList.replaceChildren();
  elements.traceList.replaceChildren();
  elements.evidenceBadge.textContent = "0";
  elements.traceBadge.textContent = "0";
  elements.dossierMetrics.hidden = true;
  elements.copyReportButton.disabled = true;
  elements.conversationLog.innerHTML = `<article class="message message-system"><span class="message-label">Field note</span><p>New investigation started. Prior conclusions are no longer in the agent's turn memory.</p></article>`;
  renderTopology();
  showToast("New investigation started");
}

function wireEvents() {
  [
    [elements.caseFileResizer, "caseFile"],
    [elements.dossierResizer, "dossier"],
    [elements.timelineResizer, "timeline"],
  ].forEach(([handle, kind]) => {
    handle.addEventListener("pointerdown", (event) => beginResize(kind, event));
    handle.addEventListener("keydown", (event) => resizeWithKeyboard(kind, event));
    handle.addEventListener("dblclick", () => resetResize(kind));
  });
  window.addEventListener("pointermove", continueResize);
  window.addEventListener("pointerup", endResize);
  window.addEventListener("pointercancel", endResize);
  let resizeFrame = null;
  window.addEventListener("resize", () => {
    if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      syncResizableLayout();
    });
  });
  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = elements.questionInput.value.trim();
    if (!question) return;
    investigate(question);
  });
  elements.incidentSelect.addEventListener("change", async () => {
    renderCaseSummary();
    elements.questionInput.value = `Investigate ${elements.incidentSelect.value}. What changed, what is the leading hypothesis, and what contradicts it?`;
    try {
      await loadTopology(elements.incidentSelect.value);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  elements.promptSuggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-example-index]");
    if (!button) return;
    elements.questionInput.value = state.meta.examples[Number(button.dataset.exampleIndex)];
    elements.questionInput.focus();
  });
  elements.newSessionButton.addEventListener("click", clearSession);
  elements.zoomInButton.addEventListener("click", () => zoomGraph(0.15));
  elements.zoomOutButton.addEventListener("click", () => zoomGraph(-0.15));
  elements.resetGraphButton.addEventListener("click", () => {
    state.transform = { x: 0, y: 0, scale: 1 };
    elements.nodeInspector.hidden = true;
    applyTransform();
  });
  elements.topologySvg.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomGraph(event.deltaY < 0 ? 0.1 : -0.1);
  }, { passive: false });
  elements.topologySvg.addEventListener("pointerdown", (event) => {
    if (event.target.closest?.(".service-node")) return;
    state.dragging = true;
    state.dragPoint = { x: event.clientX, y: event.clientY };
    elements.topologySvg.classList.add("panning");
    elements.topologySvg.setPointerCapture(event.pointerId);
  });
  elements.topologySvg.addEventListener("pointermove", (event) => {
    if (!state.dragging) return;
    state.transform.x += event.clientX - state.dragPoint.x;
    state.transform.y += event.clientY - state.dragPoint.y;
    state.dragPoint = { x: event.clientX, y: event.clientY };
    applyTransform();
  });
  elements.topologySvg.addEventListener("pointerup", () => {
    state.dragging = false;
    elements.topologySvg.classList.remove("panning");
  });
  document.querySelector(".dossier-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (button) activateTab(button.dataset.tab);
  });
  elements.reportContent.addEventListener("click", (event) => {
    const citation = event.target.closest("[data-evidence-id]");
    if (citation) focusEvidence(citation.dataset.evidenceId);
  });
  elements.copyReportButton.addEventListener("click", async () => {
    if (!state.result) return;
    await navigator.clipboard.writeText(state.result.answer);
    showToast("Report copied");
  });
}

async function boot() {
  wireEvents();
  syncResizableLayout();
  try {
    const [status, meta] = await Promise.all([api("/api/status"), api("/api/meta")]);
    setRuntimeStatus(status);
    populateMeta(meta);
    const incident = selectedIncident();
    if (incident) {
      elements.questionInput.value = `Investigate ${incident.incidentId}. What changed, what is the leading hypothesis, and what contradicts it?`;
      await loadTopology(incident.incidentId);
    }
  } catch (error) {
    elements.statusLight.className = "status-light error";
    elements.statusText.textContent = "Connection failed";
    elements.caseSummary.textContent = error.message;
    showToast(error.message, "error");
  }
}

boot();
