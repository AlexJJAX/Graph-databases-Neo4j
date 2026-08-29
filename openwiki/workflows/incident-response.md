# Incident-response workflow

## Prepare the graph

From the repository root, validate the synthetic corpus without external I/O:

```bash
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/ingest.py --dry-run
```

Run ingestion against a disposable Neo4j/OpenAI environment with `ingest.py` to create the isolated `Ops*` schema, wait for search indexes, incrementally embed chunks, and upsert topology, temporal records, runbooks, and postmortems. Re-running should reuse unchanged chunk embeddings.

## Bounded investigation

`investigate.py` submits a question to `IncidentInvestigationAgent`. The model may select only one of seven strict tools at a time: list incidents, retrieve incident context, find recent changes, trace blast radius, search operational evidence, find similar incidents, or retrieve runbooks. The application validates arguments and dispatches parameterized read-only Neo4j or hybrid retrieval operations; it never exposes arbitrary Cypher or remediation actions.

The agent preserves model reasoning/tool-output items, assigns deduplicated evidence records per investigation as `[E1]`, `[E2]`, and so on, merges graph and timeline provenance, and repeats for at most five rounds by default. If the budget is exhausted, it removes the tool surface and requires a final typed report. Pydantic validation requires a summary, leading hypothesis, confidence, supporting/contradicting evidence, blast radius, safe next checks, and limitations. `validate_report` rejects unknown or missing evidence citations.

Use:

```bash
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/investigate.py \
  "Investigate INC-104. What changed, what is the leading hypothesis, and what contradicts it?" \
  --show-trace
```

## FastAPI control room

Start the server with `uv run uvicorn web:app --app-dir 3-Agentic-Temporal-Incident-Response-Copilot --host 127.0.0.1 --port 8133`. The API provides readiness/stats at `GET /api/status`, incidents/services/examples at `/api/meta`, topology and timeline at `/api/topology`, investigations at `POST /api/investigate`, and session deletion at `DELETE /api/sessions/{session_id}`. Questions must be 3–1600 characters; session IDs are optional and history is compact, thread-safe, process-local memory capped at six turns.

The static UI renders the renamed Investigation Pane, Service topology overview, Temporal Context, dossier, evidence ledger, citations, and exact tool trace. On wide screens, keyboard-focusable separators let users resize the investigation and dossier columns; a timeline separator resizes temporal context, and double-click resets a pane. The topology renderer uses responsive client/core/dependency bands and schedules redraws after layout changes. A selected citation highlights its evidence card. No endpoint mutates the graph or executes an operational action.

## Evaluate and interpret results

Run `uv run python 3-Agentic-Temporal-Incident-Response-Copilot/evaluate.py`. The five-case live evaluation reports required tool-route recall, expected evidence-source hit rate, diagnosis-term accuracy, and bounded-investigation rate. Model-selected routes can vary, so expected tools are evaluated as a recall set rather than a single sequence. Synthetic data, model variability, and the distinction between temporal correlation and causation limit what these scores establish.

Source anchors: `agent.py`, `tools.py`, `evidence.py`, `memory.py`, `investigate.py`, `web.py`, `evaluate.py`, and `static/`.