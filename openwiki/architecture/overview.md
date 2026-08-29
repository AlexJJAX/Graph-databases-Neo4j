# Architecture overview

## Portfolio boundary

The root project is a progressively layered Neo4j/AI portfolio. `1-Basic-Graph-Grounded-Chatbot` is the literal, tool-using movie baseline; `2-Hybrid-GraphRAG-Research-Assistant` is the semantic research workbench built on a separate `Research*` schema; `3-Agentic-Temporal-Incident-Response-Copilot` is the bounded, read-only temporal operations investigator built on an isolated `Ops*` schema; and `4-Graph-Native-Fraud-Intelligence-Copilot` is the fraud-investigation capstone built on an isolated `Fraud*` identity, transaction, evidence, and persistent-memory graph. `neo4j_basic/quick_example.py` remains an independent friend-graph demonstration, not a dependency of the applications.

## Movie chatbot components

- `app.py` is the CLI boundary. It loads configuration, verifies Neo4j connectivity, supports one-shot questions, context display, health checks, and an interactive REPL.
- `config.py` loads repository-root environment variables and builds `Neo4jConfig` and `AppConfig`; the default model is `gpt-5.6-luna`.
- `graph.py` owns one long-lived Neo4j driver, schema constraints/index creation, parameterized Cypher retrieval, criteria validation, and conversion to bounded `MovieEvidence`.
- `chatbot.py` orchestrates the OpenAI Responses API two-pass loop: a required `search_movie_graph` call extracts structured filters, then a tool-disabled call answers from returned evidence.
- `seed.py` loads `data/movies.json` into an empty movie database and skips existing catalogs.

## Request boundary

1. The CLI submits a non-empty question to the chatbot.
2. The first model call must request the single search tool with typed title, person, genre, rating, year, and limit filters.
3. Neo4j executes one parameterized, read-routed Cypher query and returns projected movie fields rather than raw nodes.
4. Evidence is assigned IDs such as `[G1]` and sent to the second model call.
5. The final call cannot use tools and is instructed to cite every factual claim and refuse unsupported facts.

The movie retrieval is deliberately literal and bounded; there is no vector, embedding, or hybrid search in Project 1. Project 2 adds a separate path: query embedding, Neo4j vector plus full-text candidates, 65/35 hybrid ranking, semantic gating, graph-neighbor expansion, and a single grounded Responses API call. Its result includes `[R#]` excerpt evidence, a source ledger, metrics, and an evidence-graph projection for the FastAPI/UI layer. Project 3 makes retrieval iterative: the Responses API selects one of seven strict read-only tools per round, the application executes parameterized graph or hybrid retrieval, an `EvidenceLedger` assigns `[E#]` IDs and merges graph/timeline provenance, and a typed report is rejected if citations are unknown or missing. It caps graph traversal at three hops and the investigation at five rounds by default. Project 4 extends the same inspectable boundary to identity and transaction analysis: one of eight read-only tools executes bounded graph patterns or hybrid fraud-evidence retrieval, persistent `FraudInvestigation`/`FraudTurn` memory supplies compact prior summaries, and deterministic review validates the typed report's citations and calibrated risk language. See [Movie graph domain](../domain/movie-graph.md), [Research graph domain](../domain/research-graph.md), [Operations graph domain](../domain/operations-graph.md), [Fraud graph domain](../domain/fraud-graph.md), [Movie-question workflow](../workflows/movie-question.md), [Research assistant workflow](../workflows/research-assistant.md), [Incident-response workflow](../workflows/incident-response.md), and [Fraud-investigation workflow](../workflows/fraud-investigation.md).

## Documentation automation

The generated pages are refreshed by the workflow described in [Update workflow](../operations/update-workflow.md). This architecture page was expanded because commit `9b065fd` introduced the application runtime, graph model, and tests after the initial documentation baseline.
