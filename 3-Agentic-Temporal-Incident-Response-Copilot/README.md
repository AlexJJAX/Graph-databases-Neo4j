# Project 3 — Agentic Temporal Incident Response Copilot

![Tests](https://img.shields.io/badge/tests-32%20passing-2E7D32)
![Retrieval](https://img.shields.io/badge/retrieval-agentic%20hybrid%20GraphRAG-00796B)
![Safety](https://img.shields.io/badge/tools-read--only-B45309)
![Isolation](https://img.shields.io/badge/project%20isolation-tested-512BD4)
![Model](https://img.shields.io/badge/model-gpt--5.6--luna-412991)
![Neo4j](https://img.shields.io/badge/Neo4j-Cypher%2025-008CC1)

A read-only incident-investigation workbench that uses Neo4j as the central
reasoning surface connecting: `service topology overview`, `ownership`, `deployments`, `commits`,
`alerts`, `incidents`, `runbooks`, `postmortems`, `vector search`, and an OpenAI tool-using
agent.

The synthetic **Northstar Commerce** platform gives the copilot enough temporal
and relational structure to investigate what changed, trace a plausible blast
radius, compare historical incidents, find the applicable runbook, report
contradictory evidence, and propose the next safe diagnostic check. Every report
claim is bound to an evidence-ledger ID. The agent cannot run arbitrary Cypher
or execute a remediation.

## How Project 3 builds on previous projects

| Capability | Project 1             | Project 2                 | Project 3                                                         |
| ---------- | --------------------- | ------------------------- | ----------------------------------------------------------------- |
| Domain     | Movie facts           | AI literature             | Time-varying service operations                                   |
| Retrieval  | Literal graph filters | One hybrid GraphRAG pass  | Agent routes across seven bounded tools                           |
| Graph role | Structured evidence   | Semantic result expansion | Topology, time, change correlation, and blast radius              |
| Reasoning  | Retrieve then answer  | Retrieve then synthesize  | Hypothesize, test, contradict, refine                             |
| State      | CLI turn              | Independent UI questions  | Six-turn process-local investigation memory                       |
| Grounding  | `[G#]` facts          | `[R#]` excerpts           | Typed `[E#]` graph, telemetry, timeline, and document records     |
| Safety     | Bounded query tool    | Fixed retrieval pipeline  | Read-only allowlist, 3-hop and 5-round budgets                    |
| Interface  | CLI                   | Research evidence UI      | Control-room topology, timeline, dossier, ledger, and agent trace |

Project 2 proved that vectors, full text, and graph expansion improve retrieval.

Project 3 makes retrieval iterative: the model chooses which evidence it
needs next and the application—not the model—executes parameterized, read-only
operations.

## Questions the graph must answer

The model was designed from these concrete use cases:

1. What changed in the minutes before an incident began?
2. Which services show observed impact, and which are only topologically exposed?
3. Which upstream or downstream service paths form the plausible blast radius?
4. Which historical postmortem best matches the current symptoms and topology?
5. Which runbook sections apply to the affected services?
6. Which evidence supports or contradicts the leading diagnosis?
7. What safe, non-mutating diagnostic check should an operator perform next?

## Knowledge graph

```text
(:OpsService)-[:DEPENDS_ON {criticality}]->(:OpsService)
(:OpsService)-[:OWNED_BY]->(:OpsTeam)

(:OpsDeployment)-[:DEPLOYED_TO]->(:OpsService)
(:OpsDeployment)-[:BUILT_FROM]->(:OpsCommit)
(:OpsIncident)-[:PRECEDED_BY]->(:OpsDeployment)

(:OpsIncident)-[:IMPACTED]->(:OpsService)
(:OpsAlert)-[:TRIGGERED_FOR]->(:OpsService)
(:OpsAlert)-[:SIGNALS]->(:OpsIncident)

(:OpsRunbook)-[:APPLIES_TO]->(:OpsService)
(:OpsRunbook)-[:HAS_OPS_CHUNK]->(:OpsChunk {embedding})
(:OpsPostmortem)-[:DOCUMENTS]->(:OpsIncident)
(:OpsPostmortem)-[:HAS_OPS_CHUNK]->(:OpsChunk {embedding})
```

Every `MERGE` target has a unique constraint. Operational timestamps are native
Neo4j zoned datetimes normalized to UTC. Embeddings live only on dedicated
`OpsChunk` nodes. The `Ops*` label family and `ops_*` index names isolate this
project from Project 1's movie graph and Project 2's `Research*` graph.

## Agentic request flow

```text
Question + up to six prior turn summaries
    -> model selects one bounded read tool
    -> application validates JSON arguments
    -> parameterized Cypher or HybridCypherRetriever runs
    -> typed graph/document evidence enters the [E#] ledger
    -> tool output and all model reasoning items return to Responses API
    -> repeat for at most five rounds
    -> Pydantic-structured incident report
    -> reject unknown or missing citations
    -> report + topology + timeline + evidence + replayable tool trace
```

`parallel_tool_calls=False` keeps the trace deterministic and easy to audit.
Response storage is disabled. If the model spends the whole tool budget, the
application removes the tool surface and requires a final bounded synthesis.

### Tool allowlist

| Tool                          | Evidence boundary                                                      |
| ----------------------------- | ---------------------------------------------------------------------- |
| `list_incidents`              | Known case IDs and status                                              |
| `get_incident_context`        | Incident, observed services, and alerts                                |
| `get_recent_changes`          | Deployments to impacted or adjacent services in a capped time window   |
| `trace_blast_radius`          | Incoming dependency paths, maximum three hops                          |
| `search_operational_evidence` | Hybrid runbook/postmortem search, optionally graph-filtered by service |
| `find_similar_incidents`      | Postmortem similarity constrained by affected-service overlap          |
| `get_runbooks`                | Runbook chunks explicitly connected to selected services               |

## Corpus and retrieval

`data/platform.json` is a fully synthetic, inspectable fixture containing:

- 9 services and 4 owning teams;
- 7 deployments and their commits;
- 4 incidents and 9 alerts;
- 4 runbooks and 3 historical postmortems;
- 18 deterministic document chunks.

Ingestion hashes each chunk and embeds only new, changed, or previously
unembedded content. `ops_chunk_embedding` is a 1,536-dimensional cosine vector
index. `ops_chunk_fulltext` indexes chunk text, title, and section. The
`HybridCypherRetriever` uses a 65/35 vector/full-text linear rank, then expands
each result to its document, incident, and connected services. A configurable
semantic gate rejects weak candidates.

## Architecture

| File             | Responsibility                                                             |
| ---------------- | -------------------------------------------------------------------------- |
| `config.py`      | Repository `.env`, fixed model/index settings, safety budgets              |
| `corpus.py`      | Cross-reference validation, stable hashes, incremental chunk rows          |
| `embeddings.py`  | OpenAI 2.x adapter for the Neo4j GraphRAG embedder protocol                |
| `graph_store.py` | One Neo4j driver, Cypher 25 schema/writes, read-only investigation queries |
| `retrieval.py`   | Hybrid semantic/lexical retrieval and graph filters                        |
| `evidence.py`    | Evidence IDs, deduplication, graph/timeline provenance merge               |
| `tools.py`       | Seven strict function schemas and read-only dispatch                       |
| `agent.py`       | Responses API tool loop, typed report, citation validation                 |
| `memory.py`      | Thread-safe, process-local six-turn session summaries                      |
| `ingest.py`      | Dry-run and idempotent ingestion CLI                                       |
| `investigate.py` | One-shot command-line investigation client                                 |
| `evaluate.py`    | Route, evidence, diagnosis-term, and budget evaluation                     |
| `web.py`         | FastAPI API, session coordination, and static host                         |
| `static/`        | Responsive control-room UI with topology pan/zoom and timeline             |
| `tests/`         | 32 offline tests using fakes—no Neo4j or OpenAI calls                      |

## Setup and ingestion

The project reads the repository-level `.env`. The optional settings are shown
in this folder's `.env.example`.

From the repository root:

```bash
uv sync

# Validate all IDs, references, timestamps, and document sections offline.
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/ingest.py --dry-run

# Create the isolated Ops* schema, embed changed chunks, and ingest.
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/ingest.py
```

Expected first ingestion:

```text
Ingested 9 services, 4 incidents, and 18 chunks (18 embedded, 0 reused).
Graph totals: 7 deployments, 9 alerts, 18 evidence chunks.
```

Re-running the command should report all 18 embeddings as reused.

## Run it

Terminal investigation:

```bash
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/investigate.py \
  "Investigate INC-104. What changed, what is the leading hypothesis, and what contradicts it?" \
  --show-trace
```

Control-room workbench:

```bash
uv run uvicorn web:app \
  --app-dir 3-Agentic-Temporal-Incident-Response-Copilot \
  --host 127.0.0.1 \
  --port 8133
```

Open `http://127.0.0.1:8133`. The center desk shows the complete service
topology and selected incident timeline. Drag to pan, use the wheel or buttons
to zoom, select a node for ownership/dependency details, and select a timeline
event to locate its service. The dossier separates the report, evidence ledger,
and exact agent tool trace. Selecting an `[E#]` citation opens and highlights
its evidence card.

**New investigation** clears the process-local turn memory. Restarting the web
process also clears sessions; persistent organizational memory is intentionally
reserved for Project 4.

## Evaluation

```bash
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/evaluate.py
```

The five-case live evaluation reports:

- required tool-route recall;
- expected evidence-source hit rate;
- diagnosis-term accuracy;
- bounded-investigation rate.

The exact model-selected route can vary, so evaluation treats expected tools as
a recall set instead of requiring one brittle sequence.

Latest live verification with the included five-case fixture:

| Metric                            | Score |
| --------------------------------- | ----: |
| Required tool-route recall        |  1.00 |
| Expected evidence-source hit rate |  1.00 |
| Diagnosis-term accuracy           |  0.80 |
| Bounded-investigation rate        |  1.00 |

## Offline tests

```bash
uv run python -m unittest discover \
  -s 3-Agentic-Temporal-Incident-Response-Copilot/tests -v
```

The suite covers corpus integrity, cross-references, incremental embeddings,
configuration bounds, OpenAI embedding order, isolated Cypher 25 schema,
parameterized ingestion, hybrid retrieval parameters, semantic rejection,
evidence deduplication, tool contracts, exposure-versus-impact language,
agent-loop item preservation, citation validation, bounded memory, evaluation
metrics, API behavior, and accessible responsive UI contracts.

## Grounding and limitations

1. Temporal adjacency and a graph path are evidence, not automatic proof of
   causation or impact. The report schema makes those distinctions explicit.
2. Aggregate alert metrics cannot replace request traces, configuration diffs,
   or provider-level latency distributions. Missing evidence must be reported.
3. Hybrid similarity improves discovery but does not validate a diagnosis;
   evidence IDs and post-generation validation enforce the grounding boundary.
4. The corpus and incidents are synthetic and deliberately small. This is an
   architectural portfolio project, not a production incident-management tool.
5. Web session memory is in-process and stores only compact prior conclusions.
6. No tool can mutate Neo4j or another system. Human approval and action
   execution are outside Project 3's scope.
