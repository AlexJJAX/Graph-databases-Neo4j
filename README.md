# Neo4j AI Portfolio

[![Run unit Tests | Passing](https://github.com/AlexJJAX/Graph-databases-Neo4j/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/AlexJJAX/Graph-databases-Neo4j/actions/workflows/unit-tests.yml)
![Python](https://img.shields.io/badge/python-3.13%2B-3776AB)
![Neo4j](https://img.shields.io/badge/Neo4j-Cypher%2025-008CC1)
![Retrieval](https://img.shields.io/badge/retrieval-hybrid%20GraphRAG-00796B)
![Grounding](https://img.shields.io/badge/claims-citation%20validated-70880E)
![Safety](https://img.shields.io/badge/tools-read--only-B45309)
![Memory](https://img.shields.io/badge/memory-persistent%20Neo4j-512BD4)

This repository is a progressively layered portfolio showing how graph databases (Neo4j) as a central component to unify knowledge graphs, vector search, & LLMs for accurate, efficient & grounded chatbot interactions. It requires local instance of neo4j to run.

## Projects

1. **[Basic Graph-Grounded Chatbot](1-Basic-Graph-Grounded-Chatbot/README.md)**
   — a tool-using movie assistant that retrieves a bounded knowledge subgraph
   before model writes an answer.

2. **[Hybrid GraphRAG Research Assistant](2-Hybrid-GraphRAG-Research-Assistant/README.md)**
   — an AI-literature workbench combining `semantic vectors`, `full-text ranking`, `graph-neighbor expansion`, `excerpt citations`, `retrieval evaluation`, and an interactive provenance view.

3. **[Agentic Temporal Incident Response Copilot](3-Agentic-Temporal-Incident-Response-Copilot/README.md)**
   — a read-only operations investigator that routes across `temporal graph`,
   topology, hybrid vector/full-text, runbook, and postmortem tools; tests
   competing hypotheses; and returns a citation-validated incident dossier with
   an interactive service map, timeline, evidence ledger, and agent trace.

4. **[Graph-Native Fraud Intelligence & Investigation Copilot](4-Graph-Native-Fraud-Intelligence-Copilot/README.md)**
   — the capstone project that unifies an `identity graph`, `transaction network`, `vector and full-text knowledge retrieval`, a bounded investigation `agent`, `persistent Neo4j conversation memory`, deterministic `citation review`, and an interactive `entity-circuit` workbench.
   Finally, it tests suspicious multi-hop patterns against benign counterexamples without making autonomous fraud determinations.

## Progressive Capabilities of Neo4j across the 4 Projects

### `Core Progression`

| Capability           | Project 1 — Basic Graph-Grounded Chatbot | Project 2 — Hybrid GraphRAG Research Assistant                                                           | Project 3 — Agentic Temporal Incident Response Copilot                                                                      | Project 4 — Graph-Native Fraud Intelligence Copilot                                                                                                                                                          |
| :------------------- | :--------------------------------------- | :------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Domain**           | Movies                                   | AI literature                                                                                            | Service incidents                                                                                                           | Financial-crime investigations                                                                                                                                                                               |
| **Graph role**       | Fact store — static entity look-up       | Semantic expansion — chunk → paper → author/method/dataset                                               | Temporal topology — services, deployments, alerts, incidents                                                                | Unified substrate — identity, money flow, knowledge, memory                                                                                                                                                  |
| **Node types**       | `Movie`, `Person`, `Genre`               | `ResearchPaper`, `ResearchChunk`, `ResearchAuthor`, `ResearchTopic`, `ResearchMethod`, `ResearchDataset` | `OpsService`, `OpsDeployment`, `OpsCommit`, `OpsIncident`, `OpsAlert`, `OpsRunbook`, `OpsPostmortem`, `OpsChunk`, `OpsTeam` | `FraudPerson`, `FraudAccount`, `FraudTransaction`, `FraudMerchant`, `FraudDevice`, `FraudPhone`, `FraudAddress`, `FraudAlert`, `FraudCase`, `FraudDocument`, `FraudChunk`, `FraudInvestigation`, `FraudTurn` |
| **Schema isolation** | `Movie/Person/Genre` labels              | `Research*` prefix — coexists with P1                                                                    | `Ops*` prefix — coexists with P1 + P2                                                                                       | `Fraud*` prefix — coexists with P1 + P2 + P3                                                                                                                                                                 |
| **Constraints**      | 3 uniqueness constraints                 | 7 uniqueness constraints + vector & full-text indexes                                                    | 10 uniqueness constraints + vector & full-text indexes                                                                      | 12 uniqueness constraints + 2 time indexes + vector & full-text indexes                                                                                                                                      |

### `Retrieval`

| Capability             | Project 1                                    | Project 2                                                        | Project 3                                        | Project 4                                                                  |
| :--------------------- | :------------------------------------------- | :--------------------------------------------------------------- | :----------------------------------------------- | :------------------------------------------------------------------------- |
| **Retrieval strategy** | Bounded, parameterized Cypher filters        | Single hybrid pass (65% vector / 35% full-text)                  | Agent-selected tools per round                   | Eight graph-pattern + hybrid evidence tools                                |
| **Vector search**      | ✗ None                                       | ✓ `research_chunk_embedding` (1 536-d cosine)                    | ✓ `ops_chunk_embedding` (1 536-d cosine)         | ✓ `fraud_chunk_embedding` (1 536-d cosine)                                 |
| **Full-text search**   | ✗ None                                       | ✓ `research_chunk_fulltext` (text, section)                      | ✓ `ops_chunk_fulltext` (text, title, section)    | ✓ `fraud_chunk_fulltext` (text, title, section)                            |
| **Hybrid fusion**      | N/A                                          | Linear 65/35 rank via `HybridCypherRetriever`                    | Linear 65/35 rank via `HybridCypherRetriever`    | Linear 65/35 rank via `HybridCypherRetriever` with account-scope filtering |
| **Graph expansion**    | Single Cypher query → bounded scalar results | Chunk → document → authors, topics, methods, datasets, citations | Chunk → document → incident → connected services | Chunk → document → referenced accounts, devices, merchants                 |
| **Semantic gate**      | N/A                                          | ≥ 0.25 minimum similarity threshold                              | Configurable minimum similarity threshold        | Configurable minimum similarity threshold                                  |
| **Tool surface**       | 1 tool (`search_movie_graph`)                | Fixed retrieval pipeline (no tool-calling)                       | 7 read-only tools                                | 8 read-only tools                                                          |

### `Reasoning & Agent`

| Capability            | Project 1                                | Project 2                              | Project 3                                                                              | Project 4                                                                                                                                             |
| :-------------------- | :--------------------------------------- | :------------------------------------- | :------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LLM interaction**   | Two-pass tool loop (force call → answer) | Single-pass — no tool-calling loop     | Multi-round agent loop (≤ 5 rounds)                                                    | Multi-round agent loop (≤ 6 rounds)                                                                                                                   |
| **Reasoning pattern** | Retrieve then answer                     | Retrieve then synthesize               | Hypothesize → test → contradict → refine                                               | Signal triangulation + benign-counterexample review                                                                                                   |
| **Structured output** | Free-text answer with `[G#]` citations   | Free-text answer with `[R#]` citations | Pydantic `IncidentReport` with typed sections                                          | Pydantic `FraudInvestigationDraft` with epistemic sections                                                                                            |
| **Report sections**   | Answer only                              | Answer + source ledger                 | Diagnosis, contributing factors, contradictions, blast radius, next steps, limitations | Observed facts, derived patterns, typology matches, benign/contradictory evidence, network exposure, risk assessment, recommended checks, limitations |

### `Memory & State`

| Capability         | Project 1                  | Project 2                    | Project 3                                                  | Project 4                                                                       |
| :----------------- | :------------------------- | :--------------------------- | :--------------------------------------------------------- | :------------------------------------------------------------------------------ |
| **Memory**         | None — stateless CLI turns | None — independent questions | Process-local — 6-turn session summaries (lost on restart) | Persistent — `FraudInvestigation → FraudTurn` nodes in Neo4j (survive restarts) |
| **Memory storage** | N/A                        | N/A                          | In-process Python dict                                     | Neo4j graph (compact summaries + confidence)                                    |

### `Grounding & Safety`

| Capability              | Project 1                                   | Project 2                                              | Project 3                                                       | Project 4                                                                                                            |
| :---------------------- | :------------------------------------------ | :----------------------------------------------------- | :-------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------- |
| **Citation scheme**     | `[G#]` — graph records                      | `[R#]` — excerpt-level citations with source URLs      | `[E#]` — typed graph, telemetry, timeline, and document records | `[E#]` — epistemic report sections + deterministic citation review                                                   |
| **Citation validation** | LLM instructed to cite only retrieved facts | Post-generation validation rejects missing/unknown IDs | Post-generation validation rejects missing/unknown citations    | Deterministic grounding reviewer rejects any claim with missing or unknown `[E#]` IDs                                |
| **Safety boundary**     | Bounded query — max 8 results               | Fixed retrieval pipeline — no arbitrary Cypher         | Read-only tool allowlist + 3-hop, 5-round budgets               | Read-only tool allowlist + 6-round budget; no account blocking, report filing, customer contact, or arbitrary Cypher |
| **Calibrated language** | Strict grounding; refuses if no evidence    | Rejects if no evidence above semantic gate             | Reports contradictory evidence explicitly                       | Uses "suspected" / "consistent with"; shared identifiers ≠ proof of fraud                                            |

### `Interface & Evaluation`

| Capability        | Project 1                                  | Project 2                                    | Project 3                                                                                  | Project 4                                                                                                          |
| :---------------- | :----------------------------------------- | :------------------------------------------- | :----------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------- |
| **Interface**     | CLI (`--question`, `--show-context`, REPL) | Responsive evidence workbench + CLI          | Control-room topology, timeline, dossier, ledger, agent trace                              | Alert queue, entity circuit, money timeline, dossier, evidence ledger, tool trace                                  |
| **Web port**      | N/A                                        | `localhost:8123`                             | `localhost:8133`                                                                           | `localhost:8144`                                                                                                   |
| **Evaluation**    | Unit-tested interaction (6 tests)          | Hit rate, MRR, negative rejection (26 tests) | Tool-route recall, evidence-source hits, diagnosis terms, bounded investigation (32 tests) | Tool-route recall, evidence-source hits, citation integrity, calibrated language, bounded investigation (32 tests) |
| **Offline tests** | 6 tests (fakes, no Neo4j/OpenAI)           | 26 tests (fakes, no Neo4j/OpenAI)            | 32 tests (fakes, no Neo4j/OpenAI)                                                          | 32 tests (fakes, no Neo4j/OpenAI)                                                                                  |

### `Synthetic Data`

| Capability          | Project 1                                     | Project 2                                              | Project 3                                                                | Project 4                                                                                                |
| :------------------ | :-------------------------------------------- | :----------------------------------------------------- | :----------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------- |
| **Dataset**         | `movies.json` — TMDB movie catalog            | `papers.json` — 8 foundational AI papers, 24 chunks    | `platform.json` — Northstar Commerce: 9 services, 4 incidents, 18 chunks | `fraud_network.json` — Northstar Financial: 10 people, 10 accounts, 13 transactions, 4 alerts, 15 chunks |
| **Embedding model** | N/A                                           | `text-embedding-3-small` (1 536-d)                     | `text-embedding-3-small` (1 536-d)                                       | `text-embedding-3-small` (1 536-d)                                                                       |
| **Ingestion**       | Idempotent seed (skip if `Movie` nodes exist) | Content-hash gated — re-embeds only new/changed chunks | Content-hash gated — re-embeds only new/changed chunks                   | Content-hash gated — re-embeds only new/changed chunks                                                   |

## Shared environment

The examples use the repository-level `.env` file and the root `uv` project.
Secrets are never committed. Create the local file from the tracked example:

```bash
cp .env.example .env
```

The shared settings are:

```dotenv
OPENAI_API_KEY=...
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j
```

- `NEO4J_DATABASE` is optional and defaults to `neo4j`.
- Project 2 also accepts an optional `RESEARCH_MIN_SEMANTIC_SCORE` (default `0.25`) to tune out-of-domain rejection after evaluation.
- Project 3 accepts `OPS_MIN_SEMANTIC_SCORE` (default `0.22`) and `OPS_MAX_AGENT_ROUNDS` (default `5`, range `2`–`8`).
- Project 4 accepts `FRAUD_MIN_SEMANTIC_SCORE` (default `0.24`) and `FRAUD_MAX_AGENT_ROUNDS` (default `6`, range `3`–`8`).

## Unit tests

Install the locked development dependencies and run each project's isolated,
offline test suite:

```bash
uv sync --locked --dev
uv run --no-sync pytest -q 1-Basic-Graph-Grounded-Chatbot/tests
uv run --no-sync pytest -q 2-Hybrid-GraphRAG-Research-Assistant/tests
uv run --no-sync pytest -q 3-Agentic-Temporal-Incident-Response-Copilot/tests
uv run --no-sync pytest -q 4-Graph-Native-Fraud-Intelligence-Copilot/tests
```

## Limitations

⚠️ Disclamer: This Demo Is Intended For Demonstartion Purposes Only. Runnable behavior and integration tests do not imply production readiness. Retention, trust, security, reproducibility, cleanup, metrics, and lifecycle choices are illustrative—not production guarantees. Production adoption requires independent security, governance, reliability, scalability, privacy, and operational design. ⚠️
