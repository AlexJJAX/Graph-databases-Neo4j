# Fraud-investigation workflow

## Prepare the graph

Validate the synthetic corpus without external I/O, then ingest it into an isolated `Fraud*` schema:

```bash
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py --dry-run
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py
```

Ingestion validates references and timestamps, waits for indexes, embeds changed document chunks, and performs idempotent upserts. Normal operation requires the repository-level Neo4j and OpenAI configuration.

## Bounded investigation

`investigate.py` sends a question, optionally scoped to an alert, to an agent that selects one strict read-only tool per round. The eight tools cover alert resolution/context, shared identifiers, fund flows, exact three-account cycles, merchant concentration, hybrid fraud-evidence search, and similar historical cases. Arguments are validated before parameterized Cypher or hybrid retrieval executes; arbitrary Cypher, account blocking, regulatory filing, customer contact, and other external actions are unavailable.

Evidence receives stable `[E#]` IDs and is merged into graph and transaction-timeline views. The agent runs for at most six rounds by default (configurable from 3–8), then produces a typed report separating observed facts, derived patterns, retrieved typologies, benign/contradicting evidence, network exposure, calibrated risk, human checks, and limitations. Deterministic review rejects missing or unknown citations, and compact turn summaries persist as `FraudInvestigation`/`FraudTurn` graph memory.

```bash
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/investigate.py \
  "Investigate ALRT-9001. Trace shared identifiers, fund flows, cycles, and counter-evidence." \
  --show-trace
```

## FastAPI workbench

Start with:

```bash
uv run uvicorn web:app --app-dir 4-Graph-Native-Fraud-Intelligence-Copilot \
  --host 127.0.0.1 --port 8144
```

Open `http://127.0.0.1:8144`. `GET /api/status` reports readiness and graph counts; `/api/meta` lists alerts, cases, and example questions; `/api/network/{alert_id}` returns the alert graph and transaction timeline; `POST /api/investigate` accepts a 3–1800-character question plus optional alert/session IDs; and `DELETE /api/sessions/{session_id}` clears persistent history. The UI provides an alert queue, entity circuit, money timeline, dossier, evidence ledger, and exact tool trace, with pan/zoom and responsive layouts.

## Evaluate and test

```bash
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/evaluate.py
uv run python -m unittest discover -s 4-Graph-Native-Fraud-Intelligence-Copilot/tests -v
```

The four-case evaluation measures tool-route recall, expected evidence-source hits, terminology, citation integrity, calibrated risk language, and bounded-investigation rate. Offline tests use fakes and do not verify live Neo4j/OpenAI behavior.

Source anchors: `agent.py`, `tools.py`, `evidence.py`, `memory.py`, `graph_store.py`, `investigate.py`, `web.py`, `evaluate.py`, and `static/`.
