const state = {
  answerText: "",
  evidence: [],
  graph: { nodes: [], edges: [] },
};

const form = document.querySelector("#question-form");
const questionInput = document.querySelector("#question");
const askButton = document.querySelector("#ask-button");
const answerPanel = document.querySelector("#answer-panel");
const answerContent = document.querySelector("#answer-content");
const copyButton = document.querySelector("#copy-answer");
const evidenceList = document.querySelector("#evidence-list");
const graphSvg = document.querySelector("#evidence-graph");
const openConstellationButton = document.querySelector("#open-constellation");
const constellationModal = document.querySelector("#constellation-modal");
const expandedGraphStage = document.querySelector("#expanded-graph-stage");
const expandedGraphSvg = document.querySelector("#expanded-evidence-graph");
const graphSelection = document.querySelector("#graph-selection");
const zoomOutput = document.querySelector("#constellation-zoom");
const relationshipLabelsButton = document.querySelector("#toggle-relationship-labels");

const modalView = {
  scale: 1,
  x: 0,
  y: 0,
  viewport: null,
  drag: null,
  relationshipLabelsPinned: false,
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function renderAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(
    /\[(R\d+)\]/g,
    '<button class="citation-link" type="button" data-evidence="$1">[$1]</button>',
  );

  const blocks = html.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      if (lines.every((line) => /^[-•]\s+/.test(line))) {
        return `<ul>${lines.map((line) => `<li>${line.replace(/^[-•]\s+/, "")}</li>`).join("")}</ul>`;
      }
      return `<p>${lines.join("<br>")}</p>`;
    })
    .join("");
}

function setLoading(loading) {
  askButton.disabled = loading;
  askButton.querySelector("span").textContent = loading ? "Tracing evidence…" : "Trace an answer";
  if (loading) {
    answerPanel.classList.remove("is-empty");
    answerContent.innerHTML = '<div class="loading-line"></div><div class="loading-line"></div><div class="loading-line"></div>';
    document.querySelector("#metrics").hidden = true;
  }
}

function highlightEvidence(evidenceId) {
  document.querySelectorAll(".evidence-card").forEach((card) => {
    card.classList.toggle("is-highlighted", card.dataset.evidence === evidenceId);
  });
  const card = document.querySelector(`.evidence-card[data-evidence="${CSS.escape(evidenceId)}"]`);
  card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderEvidence(evidence) {
  document.querySelector("#evidence-total").textContent = evidence.length;
  if (!evidence.length) {
    evidenceList.innerHTML = '<article class="ledger-empty"><span>R—</span><p>No sufficiently relevant evidence was found.</p></article>';
    return;
  }

  evidenceList.innerHTML = evidence
    .map((item) => {
      const topics = item.topics.slice(0, 3).map((topic) => `<span>${escapeHtml(topic)}</span>`).join("");
      const sourceUrl = safeSourceUrl(item.source_url);
      return `
        <article class="evidence-card" data-evidence="${escapeHtml(item.evidence_id)}">
          <div class="evidence-meta">
            <span><b class="evidence-id">${escapeHtml(item.evidence_id)}</b> · ${escapeHtml(item.year)}</span>
            <span>semantic ${Number(item.semantic_score).toFixed(3)} · hybrid ${Number(item.hybrid_score).toFixed(3)}</span>
          </div>
          <h3>${escapeHtml(item.title)}</h3>
          <p class="evidence-section">${escapeHtml(item.section)}</p>
          <p class="evidence-excerpt">${escapeHtml(item.text)}</p>
          <div class="evidence-footer">
            <div class="topic-tags">${topics}</div>
            <a class="source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">Source ↗</a>
          </div>
        </article>`;
    })
    .join("");
}

function nodeColor(type) {
  if (type === "paper") return "#2457f5";
  if (type === "chunk") return "#ff6b5e";
  if (type === "topic") return "#58bd93";
  if (type === "method") return "#8c7cf6";
  if (type === "author") return "#f2b84b";
  return "#8ba0ba";
}

function hashPosition(value, range, offset) {
  let hash = 0;
  for (const character of value) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return offset + (Math.abs(hash) % range);
}

function compareGraphNodes(left, right) {
  const typeOrder = { chunk: 0, paper: 1, topic: 2, method: 3, author: 4 };
  const typeDifference = (typeOrder[left.type] ?? 9) - (typeOrder[right.type] ?? 9);
  return typeDifference || String(left.label).localeCompare(String(right.label));
}

function graphNodeRadius(node, expanded) {
  if (node.type === "paper") return expanded ? 25 : 22;
  if (node.type === "chunk") return expanded ? 16 : 14;
  return expanded ? 19 : 16;
}

function wrapGraphCaption(value, maxCharacters, maxLines = 2) {
  const words = String(value).trim().replace(/\s+/g, " ").split(" ").filter(Boolean);
  const lines = [];

  while (words.length && lines.length < maxLines) {
    let line = "";
    while (words.length) {
      const word = words[0];
      const candidate = line ? `${line} ${word}` : word;
      if (candidate.length <= maxCharacters) {
        line = candidate;
        words.shift();
      } else {
        break;
      }
    }

    if (!line && words.length) {
      const word = words.shift();
      line = word.length > maxCharacters
        ? `${word.slice(0, Math.max(1, maxCharacters - 1))}…`
        : word;
    }
    if (line) lines.push(line);
  }

  if (words.length && lines.length) {
    const lastIndex = lines.length - 1;
    const last = lines[lastIndex].replace(/…$/, "");
    lines[lastIndex] = `${last.slice(0, Math.max(1, maxCharacters - 1))}…`;
  }
  return lines.length ? lines : ["—"];
}

function graphCaptionLines(node) {
  if (node.type === "chunk") return [String(node.label).slice(0, 5)];
  return wrapGraphCaption(node.label, node.type === "paper" ? 12 : 10);
}

function graphLayout(graph, { expanded = false } = {}) {
  const width = expanded ? 960 : 640;
  const height = expanded ? 620 : 420;
  const center = { x: width / 2, y: height / 2 };
  const nodes = (graph?.nodes || []).slice(0, 42).map((node) => ({
    ...node,
    radius: graphNodeRadius(node, expanded),
  }));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges = (graph?.edges || []).filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target));
  const degree = new Map(nodes.map((node) => [node.id, 0]));
  const chunkCount = new Map(nodes.map((node) => [node.id, 0]));
  edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    if (edge.relationship === "HAS_CHUNK") {
      chunkCount.set(edge.source, (chunkCount.get(edge.source) || 0) + 1);
    }
  });

  let primaryPapers = nodes
    .filter((node) => node.type === "paper" && (chunkCount.get(node.id) || 0) > 0)
    .sort((left, right) => (
      (chunkCount.get(right.id) || 0) - (chunkCount.get(left.id) || 0)
      || (degree.get(right.id) || 0) - (degree.get(left.id) || 0)
      || compareGraphNodes(left, right)
    ));
  if (!primaryPapers.length) {
    primaryPapers = nodes.filter((node) => node.type === "paper").sort(compareGraphNodes).slice(0, 1);
  }
  if (!primaryPapers.length && nodes.length) primaryPapers = [nodes[0]];

  const primaryIds = new Set(primaryPapers.map((node) => node.id));
  const primaryIndex = new Map(primaryPapers.map((node, index) => [node.id, index]));
  const primaryAngles = new Map();
  const primaryCount = Math.max(primaryPapers.length, 1);
  const smallestDimension = Math.min(width, height);
  const innerRadius = primaryCount === 1
    ? 0
    : smallestDimension * Math.min(0.19, 0.105 + primaryCount * 0.015);

  primaryPapers.forEach((node, index) => {
    const angle = primaryCount === 1 ? -Math.PI / 2 : -Math.PI / 2 + (index * Math.PI * 2) / primaryCount;
    primaryAngles.set(node.id, angle);
    node.layoutBand = "retrieved-paper";
    node.layoutAngle = angle;
    node.x = center.x + Math.cos(angle) * innerRadius * 1.25;
    node.y = center.y + Math.sin(angle) * innerRadius * 0.82;
  });

  const candidatesByNode = new Map(nodes.map((node) => [node.id, new Set()]));
  edges.forEach((edge) => {
    if (primaryIds.has(edge.source) && !primaryIds.has(edge.target)) {
      candidatesByNode.get(edge.target)?.add(edge.source);
    }
    if (primaryIds.has(edge.target) && !primaryIds.has(edge.source)) {
      candidatesByNode.get(edge.source)?.add(edge.target);
    }
  });

  const bandForNode = (node) => {
    if (primaryIds.has(node.id)) return "retrieved-paper";
    if (node.type === "chunk") return "evidence";
    if (node.type === "paper") return "citation";
    if (node.type === "topic" || node.type === "method") return "concept";
    if (node.type === "author") return "author";
    return "context";
  };
  const assignmentLoad = new Map(primaryPapers.map((paper) => [paper.id, new Map()]));
  const ownerByNode = new Map();
  nodes.filter((node) => !primaryIds.has(node.id)).sort(compareGraphNodes).forEach((node) => {
    const band = bandForNode(node);
    const candidates = [...(candidatesByNode.get(node.id) || [])]
      .sort((left, right) => (primaryIndex.get(left) ?? 99) - (primaryIndex.get(right) ?? 99));
    const owner = candidates.reduce((best, candidate) => {
      if (!best) return candidate;
      const bestLoad = assignmentLoad.get(best)?.get(band) || 0;
      const candidateLoad = assignmentLoad.get(candidate)?.get(band) || 0;
      return candidateLoad < bestLoad ? candidate : best;
    }, null) || primaryPapers[hashPosition(node.id, primaryCount, 0)]?.id;
    if (!owner) return;
    ownerByNode.set(node.id, owner);
    const ownerLoad = assignmentLoad.get(owner);
    ownerLoad.set(band, (ownerLoad.get(band) || 0) + 1);
  });

  const bands = [
    { name: "evidence", rx: width * 0.21, ry: height * 0.21 },
    { name: "citation", rx: width * 0.285, ry: height * 0.29 },
    { name: "concept", rx: width * 0.37, ry: height * 0.37 },
    { name: "context", rx: width * 0.415, ry: height * 0.405 },
    { name: "author", rx: width * 0.46, ry: height * 0.46 },
  ];

  bands.forEach((band) => {
    const groups = new Map(primaryPapers.map((paper) => [paper.id, []]));
    nodes
      .filter((node) => bandForNode(node) === band.name)
      .sort(compareGraphNodes)
      .forEach((node) => groups.get(ownerByNode.get(node.id))?.push(node));

    primaryPapers.forEach((paper) => {
      const group = groups.get(paper.id) || [];
      const baseAngle = primaryAngles.get(paper.id) ?? -Math.PI / 2;
      const sector = (Math.PI * 2) / primaryCount;
      const span = primaryCount === 1 ? Math.PI * 1.82 : Math.min(sector * 0.82, 1.9);
      group.forEach((node, index) => {
        const progress = group.length === 1 ? 0.5 : index / (group.length - 1);
        const angle = baseAngle - span / 2 + span * progress;
        const radialOffset = group.length > 5 && index % 2 ? (expanded ? 9 : 6) : 0;
        node.layoutBand = band.name;
        node.layoutAngle = angle;
        node.x = center.x + Math.cos(angle) * (band.rx + radialOffset);
        node.y = center.y + Math.sin(angle) * (band.ry + radialOffset * 0.7);
      });
    });
  });

  nodes.forEach((node) => {
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) return;
    const angle = (hashPosition(node.id, 628, 0) / 100) % (Math.PI * 2);
    node.layoutBand = "context";
    node.layoutAngle = angle;
    node.x = center.x + Math.cos(angle) * width * 0.415;
    node.y = center.y + Math.sin(angle) * height * 0.405;
  });

  return { nodes, edges, nodeById, width, height };
}

function resetSelectionDetails() {
  graphSelection.innerHTML = "";
  const kicker = document.createElement("span");
  kicker.className = "selection-kicker";
  kicker.textContent = "Inspection point";
  const details = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "Select a node or relationship";
  const description = document.createElement("p");
  description.textContent = "Its role in the retrieved evidence path will appear here.";
  details.append(title, description);
  graphSelection.append(kicker, details);
}

function showSelection(element, kind, titleText, descriptionText) {
  expandedGraphSvg.querySelectorAll(".is-selected").forEach((item) => {
    item.classList.remove("is-selected");
  });
  element.classList.add("is-selected");
  graphSelection.innerHTML = "";
  const kicker = document.createElement("span");
  kicker.className = "selection-kicker";
  kicker.textContent = kind;
  const details = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = titleText;
  const description = document.createElement("p");
  description.textContent = descriptionText;
  details.append(title, description);
  graphSelection.append(kicker, details);
}

function edgeLinePoints(source, target) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.max(Math.hypot(dx, dy), 1);
  const unitX = dx / distance;
  const unitY = dy / distance;
  return {
    x1: source.x + unitX * (source.radius + 3),
    y1: source.y + unitY * (source.radius + 3),
    x2: target.x - unitX * (target.radius + 5),
    y2: target.y - unitY * (target.radius + 5),
  };
}

function renderGraph(graph, targetSvg = graphSvg, { expanded = false } = {}) {
  targetSvg.innerHTML = "";
  const { nodes, edges, nodeById, width, height } = graphLayout(graph, { expanded });
  targetSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  targetSvg.dataset.layout = "evidence-hierarchy";

  if (!nodes.length) {
    targetSvg.innerHTML = '<g class="idle-graph"><path d="M90 230 220 120 355 205 505 100 555 280 390 340 205 315Z"/><circle cx="90" cy="230" r="8"/><circle cx="220" cy="120" r="12"/><circle cx="355" cy="205" r="7"/><circle cx="505" cy="100" r="10"/><circle cx="555" cy="280" r="7"/><circle cx="390" cy="340" r="11"/><circle cx="205" cy="315" r="6"/></g>';
    if (!expanded) {
      document.querySelector("#graph-caption").textContent = "Relationships appear after retrieval.";
    }
    return null;
  }

  const svgNs = "http://www.w3.org/2000/svg";
  const markerId = `${targetSvg.id}-arrowhead`;
  const definitions = document.createElementNS(svgNs, "defs");
  const marker = document.createElementNS(svgNs, "marker");
  marker.setAttribute("id", markerId);
  marker.setAttribute("viewBox", "0 0 10 10");
  marker.setAttribute("refX", "9");
  marker.setAttribute("refY", "5");
  marker.setAttribute("markerWidth", "5");
  marker.setAttribute("markerHeight", "5");
  marker.setAttribute("orient", "auto-start-reverse");
  const arrow = document.createElementNS(svgNs, "path");
  arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
  arrow.setAttribute("fill", "#99aac3");
  marker.append(arrow);
  definitions.append(marker);
  targetSvg.append(definitions);

  const viewport = document.createElementNS(svgNs, "g");
  viewport.setAttribute("class", "graph-viewport");
  const edgeLayer = document.createElementNS(svgNs, "g");
  const relationshipLabelLayer = document.createElementNS(svgNs, "g");
  relationshipLabelLayer.setAttribute("class", "relationship-label-layer");
  edges.forEach((edge, edgeIndex) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    const points = edgeLinePoints(source, target);
    const relationship = document.createElementNS(svgNs, "g");
    relationship.setAttribute("class", "graph-relationship");
    relationship.dataset.edgeId = String(edgeIndex);
    const hitLine = document.createElementNS(svgNs, "line");
    Object.entries(points).forEach(([attribute, value]) => hitLine.setAttribute(attribute, value));
    hitLine.setAttribute("class", "graph-edge-hit");
    const line = document.createElementNS(svgNs, "line");
    Object.entries(points).forEach(([attribute, value]) => line.setAttribute(attribute, value));
    line.setAttribute("class", "graph-edge");
    line.setAttribute("marker-end", `url(#${markerId})`);
    relationship.append(hitLine, line);

    if (expanded) {
      relationship.setAttribute("tabindex", "0");
      relationship.setAttribute("role", "button");
      relationship.setAttribute(
        "aria-label",
        `${source.label} ${edge.relationship} ${target.label}`,
      );
      const label = document.createElementNS(svgNs, "text");
      const edgeDx = target.x - source.x;
      const edgeDy = target.y - source.y;
      const edgeLength = Math.max(Math.hypot(edgeDx, edgeDy), 1);
      const labelSide = hashPosition(`${edge.source}:${edge.target}`, 2, 0) ? 1 : -1;
      const labelOffset = 10 * labelSide;
      label.setAttribute("x", (source.x + target.x) / 2 - (edgeDy / edgeLength) * labelOffset);
      label.setAttribute("y", (source.y + target.y) / 2 + (edgeDx / edgeLength) * labelOffset);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "relationship-label");
      label.dataset.edgeId = String(edgeIndex);
      label.textContent = edge.relationship;
      const activate = () => {
        showSelection(
          relationship,
          "Relationship",
          edge.relationship,
          `${source.label} → ${target.label}`,
        );
        label.classList.add("is-selected");
      };
      const previewLabel = () => label.classList.add("is-previewed");
      const hidePreviewLabel = () => label.classList.remove("is-previewed");
      label.addEventListener("click", activate);
      relationshipLabelLayer.append(label);
      relationship.addEventListener("click", activate);
      relationship.addEventListener("mouseenter", previewLabel);
      relationship.addEventListener("mouseleave", hidePreviewLabel);
      relationship.addEventListener("focus", previewLabel);
      relationship.addEventListener("blur", hidePreviewLabel);
      relationship.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    }
    edgeLayer.append(relationship);
  });
  viewport.append(edgeLayer);
  if (expanded) viewport.append(relationshipLabelLayer);

  nodes.forEach((node) => {
    const group = document.createElementNS(svgNs, "g");
    group.setAttribute("class", `graph-node node-${node.type}`);
    group.setAttribute("transform", `translate(${node.x} ${node.y})`);
    group.dataset.layoutBand = node.layoutBand;
    group.dataset.nodeType = node.type;
    const interactive = expanded || node.type === "chunk";
    if (interactive) {
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.setAttribute("aria-label", `${node.type}: ${node.label}`);
    }
    const title = document.createElementNS(svgNs, "title");
    title.textContent = `${node.type}: ${node.label}`;
    const circle = document.createElementNS(svgNs, "circle");
    circle.setAttribute("r", node.radius);
    circle.setAttribute("fill", nodeColor(node.type));
    const label = document.createElementNS(svgNs, "text");
    label.setAttribute("class", "node-caption");
    label.setAttribute("text-anchor", "middle");
    const captionLines = graphCaptionLines(node);
    label.setAttribute("y", captionLines.length === 1 ? "2.4" : "-2.8");
    captionLines.forEach((captionLine, index) => {
      const tspan = document.createElementNS(svgNs, "tspan");
      tspan.setAttribute("x", "0");
      if (index) tspan.setAttribute("dy", "7.2");
      tspan.textContent = captionLine;
      label.append(tspan);
    });
    group.append(title, circle, label);
    const activate = () => {
      if (expanded) {
        const connected = edges.filter((edge) => edge.source === node.id || edge.target === node.id);
        const relationships = [...new Set(connected.map((edge) => edge.relationship))];
        const metadata = [
          node.year ? `Published ${node.year}` : "",
          node.section ? `Section: ${node.section}` : "",
          relationships.length ? `Connections: ${relationships.join(", ")}` : "No projected connections",
        ].filter(Boolean).join(" · ");
        showSelection(group, node.type, node.label, metadata);
      } else if (node.type === "chunk") {
        highlightEvidence(node.label);
      }
    };
    if (interactive) {
      group.addEventListener("click", activate);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    }
    viewport.append(group);
  });
  targetSvg.append(viewport);
  if (!expanded) {
    document.querySelector("#graph-caption").textContent = `${nodes.length} nodes · ${edges.length} relationships`;
  }
  return viewport;
}

function applyModalView() {
  if (!modalView.viewport) return;
  modalView.viewport.setAttribute(
    "transform",
    `translate(${modalView.x} ${modalView.y}) scale(${modalView.scale})`,
  );
  expandedGraphSvg.classList.toggle(
    "show-all-relationship-labels",
    modalView.relationshipLabelsPinned,
  );
  relationshipLabelsButton.setAttribute(
    "aria-pressed",
    String(modalView.relationshipLabelsPinned),
  );
  zoomOutput.value = `${Math.round(modalView.scale * 100)}%`;
  zoomOutput.textContent = zoomOutput.value;
}

function graphViewCenter() {
  const viewBox = expandedGraphSvg.viewBox.baseVal;
  return { x: viewBox.width / 2, y: viewBox.height / 2 };
}

function zoomConstellation(factor, anchor = graphViewCenter()) {
  const previous = modalView.scale;
  const next = Math.max(0.55, Math.min(3.5, previous * factor));
  modalView.x = anchor.x - ((anchor.x - modalView.x) * next) / previous;
  modalView.y = anchor.y - ((anchor.y - modalView.y) * next) / previous;
  modalView.scale = next;
  applyModalView();
}

function resetModalView() {
  modalView.scale = 1;
  modalView.x = 0;
  modalView.y = 0;
  modalView.relationshipLabelsPinned = false;
  applyModalView();
  resetSelectionDetails();
  expandedGraphSvg.querySelectorAll(".is-selected").forEach((item) => {
    item.classList.remove("is-selected");
  });
}

function clientPointInExpandedGraph(clientX, clientY) {
  const point = expandedGraphSvg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  return point.matrixTransform(expandedGraphSvg.getScreenCTM().inverse());
}

function openConstellation() {
  modalView.viewport = renderGraph(state.graph, expandedGraphSvg, { expanded: true });
  resetModalView();
  constellationModal.showModal();
  window.requestAnimationFrame(() => expandedGraphStage.focus());
}

function renderMetrics(metrics) {
  const element = document.querySelector("#metrics");
  element.hidden = false;
  element.innerHTML = [
    `${metrics.evidence_count} evidence chunks`,
    `${metrics.retrieval_ms} ms retrieval`,
    `${metrics.generation_ms} ms generation`,
    `${metrics.input_tokens} input tokens`,
    `${metrics.output_tokens} output tokens`,
  ].map((value) => `<span>${escapeHtml(value)}</span>`).join("");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

async function loadMetadata() {
  try {
    const [status, metadata] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/meta"),
    ]);
    document.querySelector("#paper-count").textContent = status.paperCount;
    document.querySelector("#chunk-count").textContent = status.chunkCount;
    document.querySelector("#topic-count").textContent = status.topicCount;
    const ready = document.querySelector("#ready-state");
    ready.textContent = status.ready ? "Graph online" : "Run ingestion";
    ready.classList.toggle("is-ready", status.ready);

    const topicSelect = document.querySelector("#topic");
    metadata.topics.forEach((topic) => {
      const option = document.createElement("option");
      option.value = topic.name;
      option.textContent = `${topic.name} (${topic.paperCount})`;
      topicSelect.append(option);
    });
    const examples = document.querySelector("#examples");
    metadata.examples.forEach((example) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "example-chip";
      button.textContent = example;
      button.addEventListener("click", () => {
        questionInput.value = example;
        questionInput.focus();
      });
      examples.append(button);
    });
  } catch (error) {
    document.querySelector("#ready-state").textContent = "Graph unavailable";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading(true);
  try {
    const payload = await fetchJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: questionInput.value.trim(),
        topic: document.querySelector("#topic").value || null,
        year_from: Number(document.querySelector("#year-from").value) || null,
        year_to: Number(document.querySelector("#year-to").value) || null,
        top_k: Number(document.querySelector("#top-k").value),
      }),
    });
    state.answerText = payload.answer;
    state.evidence = payload.evidence;
    state.graph = payload.graph || { nodes: [], edges: [] };
    answerPanel.classList.remove("is-empty");
    answerContent.innerHTML = renderAnswer(payload.answer);
    copyButton.hidden = false;
    renderEvidence(payload.evidence);
    renderGraph(state.graph);
    openConstellationButton.disabled = !(state.graph.nodes || []).length;
    renderMetrics(payload.metrics);
  } catch (error) {
    answerContent.innerHTML = `<p><strong>Could not trace an answer.</strong><br>${escapeHtml(error.message)}</p>`;
    copyButton.hidden = true;
  } finally {
    setLoading(false);
  }
});

answerContent.addEventListener("click", (event) => {
  const citation = event.target.closest("[data-evidence]");
  if (citation) highlightEvidence(citation.dataset.evidence);
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(state.answerText);
  copyButton.textContent = "Copied";
  window.setTimeout(() => { copyButton.textContent = "Copy"; }, 1200);
});

openConstellationButton.addEventListener("click", openConstellation);
document.querySelector("#close-constellation").addEventListener("click", () => {
  constellationModal.close();
});
document.querySelector("#reset-constellation").addEventListener("click", resetModalView);
relationshipLabelsButton.addEventListener("click", () => {
  modalView.relationshipLabelsPinned = !modalView.relationshipLabelsPinned;
  applyModalView();
});
document.querySelector("#zoom-in-constellation").addEventListener("click", () => {
  zoomConstellation(1.22);
});
document.querySelector("#zoom-out-constellation").addEventListener("click", () => {
  zoomConstellation(1 / 1.22);
});

expandedGraphStage.addEventListener("wheel", (event) => {
  event.preventDefault();
  zoomConstellation(
    event.deltaY < 0 ? 1.14 : 1 / 1.14,
    clientPointInExpandedGraph(event.clientX, event.clientY),
  );
}, { passive: false });

expandedGraphStage.addEventListener("pointerdown", (event) => {
  if (
    event.button !== 0
    || event.target.closest(".graph-node, .graph-relationship, .relationship-label")
  ) return;
  modalView.drag = {
    pointerId: event.pointerId,
    point: clientPointInExpandedGraph(event.clientX, event.clientY),
  };
  expandedGraphStage.setPointerCapture(event.pointerId);
});

expandedGraphStage.addEventListener("pointermove", (event) => {
  if (!modalView.drag || modalView.drag.pointerId !== event.pointerId) return;
  const point = clientPointInExpandedGraph(event.clientX, event.clientY);
  modalView.x += point.x - modalView.drag.point.x;
  modalView.y += point.y - modalView.drag.point.y;
  modalView.drag.point = point;
  applyModalView();
});

function finishGraphDrag(event) {
  if (!modalView.drag || modalView.drag.pointerId !== event.pointerId) return;
  if (expandedGraphStage.hasPointerCapture(event.pointerId)) {
    expandedGraphStage.releasePointerCapture(event.pointerId);
  }
  modalView.drag = null;
}

expandedGraphStage.addEventListener("pointerup", finishGraphDrag);
expandedGraphStage.addEventListener("pointercancel", finishGraphDrag);

expandedGraphStage.addEventListener("keydown", (event) => {
  const panStep = event.shiftKey ? 55 : 28;
  if (event.key === "+" || event.key === "=") {
    zoomConstellation(1.22);
  } else if (event.key === "-") {
    zoomConstellation(1 / 1.22);
  } else if (event.key === "0") {
    resetModalView();
  } else if (event.key === "ArrowLeft") {
    modalView.x -= panStep;
    applyModalView();
  } else if (event.key === "ArrowRight") {
    modalView.x += panStep;
    applyModalView();
  } else if (event.key === "ArrowUp") {
    modalView.y -= panStep;
    applyModalView();
  } else if (event.key === "ArrowDown") {
    modalView.y += panStep;
    applyModalView();
  } else {
    return;
  }
  event.preventDefault();
});

constellationModal.addEventListener("click", (event) => {
  if (event.target === constellationModal) constellationModal.close();
});

constellationModal.addEventListener("close", () => {
  modalView.drag = null;
  openConstellationButton.focus();
});

loadMetadata();
