# Project 4 — Graph-Native Fraud Intelligence & Investigation Copilot

![Tests](https://img.shields.io/badge/tests-32%20passing-2E7D32)
![Graph](https://img.shields.io/badge/graph-identity%20%2B%20money%20flows-008CC1)
![Retrieval](https://img.shields.io/badge/retrieval-hybrid%20GraphRAG-00796B)
![Grounding](https://img.shields.io/badge/claims-citation%20validated-70880E)
![Safety](https://img.shields.io/badge/tools-read--only-B45309)
![Memory](https://img.shields.io/badge/memory-persistent%20Neo4j-512BD4)

The portfolio's final project is a financial-crime investigation workbench in which
Neo4j is the shared substrate for an identity graph, transaction network,
document knowledge graph, vector retrieval, agent tool routing, provenance,
and persistent investigation memory. A financial-crime investigation workbench that combines transaction-network analysis, identity resolution, graph algorithms, semantic retrieval, and an evidence-grounded LLM agent.

The system identifies suspicious patterns, investigates alerts, retrieves relevant fraud typologies and historical cases, tests benign explanations, and produces a cited investigator dossier.

## How Project 4 builds on previous projects

| Capability | Project 1      | Project 2          | Project 3            | Project 4                                                           |
| ---------- | -------------- | ------------------ | -------------------- | ------------------------------------------------------------------- |
| Domain     | Movies         | AI literature      | Service incidents    | Financial-crime investigations                                      |
| Graph role | Fact retrieval | Semantic expansion | Temporal topology    | Identity resolution, money flow, knowledge, and memory              |
| Retrieval  | Bounded Cypher | One hybrid pass    | Agent-selected tools | Eight graph-pattern and hybrid evidence tools                       |
| Reasoning  | Answer         | Synthesis          | Hypothesis testing   | Signal triangulation with benign-counterexample review              |
| Memory     | None           | None               | Process-local        | Persistent `FraudInvestigation` / `FraudTurn` graph                 |
| Grounding  | `[G#]`         | `[R#]`             | `[E#]`               | Epistemic report sections plus deterministic citation review        |
| Interface  | CLI            | Evidence UI        | Incident fieldroom   | Alert queue, entity circuit, money timeline, dossier, ledger, trace |

Project 4 is the culmination of the portfolio, synthesizing and extending every capability introduced in the prior three projects:

- **Project 1 → Scaled tool routing** — Takes the bounded Cypher fact retrieval from the Basic Graph-Grounded Chatbot (movies domain) and scales it to eight specialized read-only tools.
- **Project 2 → Deeper hybrid retrieval** — Adopts the hybrid vector + full-text semantic retrieval from the Hybrid GraphRAG Research Assistant (AI literature) and deepens it with a `HybridCypherRetriever` that expands chunks through document–entity graph relationships.
- **Project 3 → Multi-signal reasoning** — Inherits the agentic tool-selection loop, temporal graph reasoning, and hypothesis-testing workflow from the Agentic Temporal Incident Response Copilot (service incidents) and advances them into signal triangulation with explicit benign-counterexample review.
- **New in Project 4** — Adds entirely new layers that none of the previous projects had:
  - **Persistent investigation memory** — `FraudInvestigation → FraudTurn` nodes in Neo4j that survive restarts.
  - **Deterministic citation reviewer** — Rejects any claim whose `[E#]` ID doesn't resolve to real retrieved evidence.
  - **Identity-resolution graph** — People → accounts → devices / phones / addresses → transactions → merchants.
  - **Browser workbench** — Alert queue, entity circuit diagram, transaction timeline, cited dossier, evidence ledger, and tool trace.
  - **Strict safety boundary** — The agent can never take an action; it only surfaces and cites evidence using calibrated language.

## Architecture Overview

| File             | Role                                                                                                                                                                                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`      | Loads `NEO4J_*` and `OPENAI_API_KEY` from `.env`; defines `AppConfig` / `Neo4jConfig` dataclasses, model defaults (`gpt-5.6-luna`, `text-embedding-3-small`), and bounded tuning knobs                                                               |
| `graph_store.py` | Neo4j access layer — schema creation (12 uniqueness constraints, 2 time indexes, vector + full-text indexes), MERGE-based ingestion queries, bounded Cypher fraud-pattern queries, and graph memory                                                  |
| `corpus.py`      | Validates the synthetic `fraud_network.json` dataset for referential integrity and deterministically chunks documents with content-hash–gated embedding                                                                                              |
| `embeddings.py`  | `Embedder`-compatible OpenAI adapter — batched `text-embedding-3-small` calls with dimension validation, used by both ingestion and `neo4j-graphrag` retrieval                                                                                       |
| `ingest.py`      | CLI entry point that loads, validates, embeds, and idempotently upserts the fraud graph + document vectors into Neo4j (`--dry-run` validates without network calls)                                                                                  |
| `evidence.py`    | Typed `EvidenceRecord` / `ToolResult` dataclasses and the `EvidenceLedger` — a deduplicating, append-only register that accumulates evidence, graph fragments, and timeline events across tool calls                                                 |
| `retrieval.py`   | Hybrid vector + full-text retrieval via `neo4j-graphrag` `HybridCypherRetriever` — expands chunks through `FraudDocument` relationships and filters by source type and account scope                                                                 |
| `tools.py`       | Eight strict, read-only tools exposed to the agent — `list_alerts`, `get_alert_context`, `find_shared_identifiers`, `trace_fund_flows`, `detect_transaction_cycles`, `measure_merchant_concentration`, `search_fraud_evidence`, `find_similar_cases` |
| `agent.py`       | Bounded tool loop (≤ 6 rounds) with the OpenAI Responses API — produces a `FraudInvestigationDraft` Pydantic report with epistemic sections, then validates every claim's `[E#]` citations                                                           |
| `memory.py`      | Neo4j-backed multi-turn investigation memory — stores compact `FraudInvestigation → FraudTurn` summaries and feeds prior-turn context into subsequent investigations                                                                                 |
| `runtime.py`     | Dependency wiring — constructs `OpenAIEmbedder`, `FraudEvidenceRetriever`, `FraudInvestigationTools`, and `FraudInvestigationAgent` from `AppConfig`                                                                                                 |
| `investigate.py` | CLI entry point — accepts a question, runs the agent, prints the cited dossier and optional `--show-trace` tool-call log                                                                                                                             |
| `web.py`         | FastAPI server (`localhost:8144`) — `/api/investigate` (POST), `/api/network/{alert_id}`, `/api/meta`, `/api/status`, session management, and static-file serving                                                                                    |
| `evaluate.py`    | Eval harness — runs `evals/questions.json` through the agent and scores tool-route recall, evidence-source hit rate, citation integrity, calibrated language, and bounded investigation                                                              |
| `static/`        | Browser UI — alert queue, entity circuit diagram, transaction timeline, investigation dossier with cited sections, evidence ledger, and tool trace                                                                                                   |
| `data/`          | Synthetic Northstar Financial dataset (`fraud_network.json`) — 10 people, 10 accounts, 13 transactions, 4 alerts, fraud typologies, policies, and case reports                                                                                       |
| `evals/`         | Evaluation question set (`questions.json`) with expected tools, source IDs, terms, and max tool-call bounds                                                                                                                                          |
| `tests/`         | Five pytest modules covering agent memory, corpus/config/embeddings, evidence/tools, graph-store/retrieval, and the web API                                                                                                                          |

## Overview

An analyst picks a fraud alert from a queue and asks natural-language questions like "Who controls these flagged accounts? Do they share a device? Did money cycle between them?" — and the system answers by querying a Neo4j graph and validating every claim against real evidence.

### The core loop:

1. Analyst selects an alert (e.g. ALRT-9001) in a browser UI or CLI.

2. The LLM agent autonomously picks from 8 read-only tools — each one runs a bounded, parameterised Cypher query against Neo4j (no arbitrary Cypher allowed):
   - list_alerts / get_alert_context — pull alert metadata
   - find_shared_identifiers — find accounts sharing a device, phone, or address
   - trace_fund_flows — follow money between accounts
   - detect_transaction_cycles — find rapid 3-account circular transfers
   - measure_merchant_concentration — check if spend is funnelling to one merchant
   - search_fraud_evidence — hybrid vector + full-text retrieval over fraud typologies, policies, and historical case reports
   - find_similar_cases — semantic similarity search for historical precedents

3. Up to 6 rounds of tool calls, then the agent produces a Pydantic-structured report with sections: observed facts, derived patterns, typology matches, benign/contradictory evidence, network exposure, risk assessment, recommended checks, limitations.

4. Every claim must cite an [E#] evidence ID — a deterministic citation reviewer rejects any claim that references a missing or unknown ID.

5. Investigation memory persists across restarts: compact turn summaries are stored as FraudInvestigation → FraudTurn nodes in Neo4j.

### The graph model

Neo4j holds an identity graph + transaction network + document knowledge graph all in one:

- People → Accounts → Transactions → Merchants (the money flow)
- People → Devices / Phones / Addresses (the identity signals)
- Alerts → Accounts / Transactions, Cases → Alerts (the operational layer)
- Documents → Chunks with vector embeddings (the retrieval layer)

### The safety boundary

The agent is strictly read-only — it can never block an account, file a report, contact a customer, or run arbitrary Cypher. It uses calibrated language ("consistent with", "warrants review") and is explicitly told that shared identifiers and graph proximity are signals, not proof of fraud.

### The browser UI

The UI at localhost:8144 has an alert queue, entity circuit diagram (people ↔ accounts ↔ devices), transaction timeline, investigation dossier with cited report sections, an evidence ledger where you can click any [E#] to see the raw evidence, and a tool trace showing exactly which tools the agent called and in what order.

### The dataset

Everything runs on a small synthetic "Northstar Financial" dataset (`fraud_network.json).

10 people, 10 accounts, 13 transactions, 4 alerts. One alert (ALRT-9001) is seeded with a suspicious cycle + shared devices; another (ALRT-1001) is a benign household counterexample. It's an architecture demo, not production data.

The synthetic **Northstar Financial** dataset lets an analyst move naturally
from:

```text
Person → Account → Transaction → Account / Merchant
  ├────→ Device
  ├────→ Phone
  └────→ Address
```

to questions such as:

> Find accounts that share a device, address, or phone number, have transferred
> money between one another, and complete a rapid multi-hop cycle.

This is deliberately a single-domain system rather than a multitenant SaaS
demo. Fraud investigation is already relationally and operationally complex;
tenant routing would add isolation machinery without improving the central
graph reasoning story.

The design demonstrates that vectors and a knowledge graph are complementary:
vectors discover relevant policy, typologies, and historical narratives;
explicit graph patterns establish which people, identifiers, accounts,
transactions, and merchants are actually connected.

## Use cases that shaped the graph

1. Resolve the people controlling the accounts flagged by an alert.
2. Find accounts sharing a device, phone, or address.
3. Determine whether those accounts transferred money among themselves.
4. Detect an exact three-account directed cycle inside a bounded interval.
5. Measure how much selected-account outgoing value reached one merchant.
6. Compare observed behaviour with relevant typology and policy passages.
7. Find semantically similar historical cases without treating similarity as an outcome.
8. Surface facts supporting a benign household explanation.
9. Preserve compact prior-turn findings across application restarts.
10. Produce a risk assessment in which every claim resolves to retrieved evidence.

## Graph model

```text
(:FraudPerson)-[:CONTROLS]->(:FraudAccount)
(:FraudPerson)-[:USES_DEVICE]->(:FraudDevice)
(:FraudPerson)-[:USES_PHONE]->(:FraudPhone)
(:FraudPerson)-[:LIVES_AT]->(:FraudAddress)

(:FraudAccount)-[:INITIATED]->(:FraudTransaction)
(:FraudTransaction)-[:CREDITED]->(:FraudAccount)
(:FraudTransaction)-[:AT_MERCHANT]->(:FraudMerchant)
(:FraudTransaction)-[:FROM_DEVICE]->(:FraudDevice)

(:FraudAlert)-[:FLAGS_ACCOUNT]->(:FraudAccount)
(:FraudAlert)-[:FLAGS_TRANSACTION]->(:FraudTransaction)
(:FraudCase)-[:CONTAINS_ALERT]->(:FraudAlert)

(:FraudDocument)-[:HAS_FRAUD_CHUNK]->(:FraudChunk {embedding})
(:FraudDocument)-[:REFERENCES_ACCOUNT]->(:FraudAccount)
(:FraudDocument)-[:REFERENCES_DEVICE]->(:FraudDevice)
(:FraudDocument)-[:REFERENCES_MERCHANT]->(:FraudMerchant)

(:FraudInvestigation)-[:HAS_TURN]->(:FraudTurn)
```

A transaction is a node, not a relationship, because it has its own identity,
time, amount, channel, device, alert links, and merchant/counterparty endpoint.
Embeddings live only on `FraudChunk` nodes—not people, accounts, or payments.
Every ingested node used by `MERGE` has a uniqueness constraint; timestamps use
native Neo4j datetimes normalized to UTC. All labels and index names use the
`Fraud*` / `fraud_*` family to coexist with the first three projects.

## Bounded agent workflow

```text
Question + selected alert + six persisted turn summaries
    → model selects one strict read-only tool
    → application validates arguments
    → parameterized Cypher 25 or HybridCypherRetriever executes
    → evidence is typed and assigned a stable [E#] ledger ID
    → graph fragments and transaction events merge into the visual provenance
    → repeat for at most six rounds
    → Pydantic-structured report
    → deterministic grounding reviewer rejects missing or unknown citations
    → report + graph + timeline + evidence + exact tool trace
    → compact turn summary persists in Neo4j
```

The final report explicitly separates:

- observed facts;
- application-derived graph patterns;
- retrieved typology matches;
- benign or contradictory evidence;
- network exposure;
- the calibrated risk assessment;
- recommended human checks and limitations.

An alert, shared identifier, cycle, graph path, or similar case is never treated
as proof of fraud. The system uses suspected/consistent-with language and has no
tool for blocking accounts, filing reports, contacting customers, running
arbitrary Cypher, or taking an external action.

### Tool allowlist

| Tool                             | Evidence boundary                                              |
| -------------------------------- | -------------------------------------------------------------- |
| `list_alerts`                    | Known alert IDs, rule reason, status, and flagged accounts     |
| `get_alert_context`              | Alert, controlling people, accounts, and flagged transactions  |
| `find_shared_identifiers`        | Shared device, phone, and address signals                      |
| `trace_fund_flows`               | Observed transfers and merchant payments in a capped window    |
| `detect_transaction_cycles`      | Exact directed three-account cycles in a capped interval       |
| `measure_merchant_concentration` | Bounded outgoing-value aggregation by merchant                 |
| `search_fraud_evidence`          | Hybrid typology, policy, and graph-filtered case-report chunks |
| `find_similar_cases`             | Historical case-report similarity as a lead only               |

## Synthetic corpus and retrieval

`data/fraud_network.json` contains:

- 10 people, 10 accounts, eight devices, nine masked addresses, and eight masked phones;
- 13 transactions and four merchants;
- four alerts and two cases;
- six documents split into 15 deterministic chunks.

`ALRT-9001` contains a seeded three-account rapid circulation pattern, shared
device/phone signals, fan-in, and a digital-goods destination. `ALRT-1001` is a
benign household counterexample with long-tenure accounts, distinct phones,
ordinary spend, and one regular household transfer. A historical mule case and
its decision caveat enable comparison without leaking the outcome into the
current case.

`fraud_chunk_embedding` is a 1,536-dimensional cosine vector index.
`fraud_chunk_fulltext` indexes text, title, and section. The
`HybridCypherRetriever` uses a 65/35 vector/full-text rank, then expands chunks
to their document and referenced fraud entities. Ingestion hashes chunks and
re-embeds only new, changed, or previously unembedded content.

## Architecture

| File             | Responsibility                                                                       |
| ---------------- | ------------------------------------------------------------------------------------ |
| `config.py`      | Shared `.env`, model/index constants, semantic and round budgets                     |
| `corpus.py`      | Cross-reference, timestamp, ownership, and document validation                       |
| `graph_store.py` | Isolated schema, idempotent ingestion, bounded pattern queries, graph memory         |
| `retrieval.py`   | Neo4j hybrid vector/full-text retrieval with graph metadata                          |
| `evidence.py`    | Typed evidence, stable IDs, deduplication, graph/timeline merge                      |
| `tools.py`       | Eight strict read-only function schemas and evidence adapters                        |
| `agent.py`       | Responses API loop, typed report, deterministic grounding reviewer                   |
| `memory.py`      | Persistent compact investigation-turn adapter                                        |
| `runtime.py`     | Runtime composition and readiness boundary                                           |
| `ingest.py`      | Offline dry-run and idempotent graph/vector ingestion                                |
| `investigate.py` | One-shot CLI investigator                                                            |
| `evaluate.py`    | Route, source, term, citation, language, and budget metrics                          |
| `web.py`         | FastAPI endpoints, selected-alert scope, and graph memory coordination               |
| `static/`        | Responsive alert queue, entity circuit, transaction timeline, dossier, ledger, trace |
| `tests/`         | 32 offline tests using fakes—no Neo4j or OpenAI calls                                |

## Run it

The project reads the repository-level `.env` documented in the root README.
Optional Project 4 settings are in `.env.example`.

```bash
uv sync

# Validate every ID, ownership rule, timestamp, and document reference offline.
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py --dry-run

# Create Fraud* constraints/indexes, embed changed chunks, and ingest the graph.
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py

# Investigate from the terminal.
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/investigate.py \
  "Investigate ALRT-9001. Trace shared identifiers, fund flows, cycles, and counter-evidence." \
  --show-trace

# Start the browser workbench.
uv run uvicorn web:app \
  --app-dir 4-Graph-Native-Fraud-Intelligence-Copilot \
  --host 127.0.0.1 --port 8144
```

Open `http://127.0.0.1:8144`. Select an alert, inspect its entity circuit and
transaction sequence, ask a scoped question, then open any `[E#]` citation to
see the exact evidence. The Evidence and Agent trace tabs expose provenance and
the model-selected route. Column edges are draggable; the network supports
pan, zoom, keyboard-selectable nodes, responsive layouts, and reduced motion.

## Evaluation and tests

Run the live four-case evaluation after ingestion:

```bash
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/evaluate.py
```

It measures required-tool recall, expected-source hits, expected terminology,
citation integrity, calibrated risk language, and bounded-investigation rate.

Run the offline suite:

```bash
uv run python -m unittest discover \
  -s 4-Graph-Native-Fraud-Intelligence-Copilot/tests -v
```

## Limits

1. The corpus is synthetic and intentionally small; it is an architecture demonstration.
2. Shared infrastructure and transactions do not establish beneficial ownership or intent.
3. Similarity retrieval discovers evidence but does not validate a case outcome.
4. The project does not implement transaction blocking, regulatory filing, customer contact, or autonomous decisioning.
5. Production use would require access control, encryption, retention/deletion policy, model-risk governance, drift monitoring, and jurisdiction-specific legal review.
6. Persistent memory stores compact model-produced summaries plus confidence; the next turn must still retrieve source evidence for its claims.
