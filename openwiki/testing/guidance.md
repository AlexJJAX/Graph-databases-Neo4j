# Testing guidance

## Project 1

Run the six unit tests from the repository root:

```bash
uv run python -m unittest discover -s 1-Basic-Graph-Grounded-Chatbot/tests -v
```

`tests/test_chatbot.py` uses fake OpenAI responses and a fake graph to verify the required search call, evidence return, citation-shaped output, and rejection of empty questions. `tests/test_graph.py` verifies criteria normalization and bounds, invalid year-range rejection, JSON-safe evidence projection, and parameterized Cypher against the configured database.

## Project 2

Run its offline suite separately:

```bash
uv run python -m unittest discover -s 2-Hybrid-GraphRAG-Research-Assistant/tests -v
```

The tests use fakes rather than live Neo4j or OpenAI calls. They cover corpus validation, deterministic overlapping chunks and hashes, incremental embeddings and dimension checks, Lucene sanitization, hybrid ranking parameters, filters and semantic rejection, evaluation scoring, grounded answer/citation enforcement, no-evidence refusal, evidence graph projection, Cypher 25 and `Research*` isolation, API validation, and UI graph/modal contracts. The repository README reports 26 Project 2 tests; the current root badge reports 96 tests across the four-project portfolio.

## Project 3

Run its 32-test offline suite separately:

```bash
uv run python -m unittest discover -s 3-Agentic-Temporal-Incident-Response-Copilot/tests -v
```

The fakes cover corpus cross-references and incremental embeddings, configuration bounds, Cypher 25 isolation, hybrid retrieval and semantic rejection, evidence deduplication, the seven-tool contract, agent-loop preservation and citation validation, bounded session memory, evaluation metrics, FastAPI behavior, and accessible responsive UI contracts.

## Project 4

Run its 32-test offline suite separately:

```bash
uv run python -m unittest discover -s 4-Graph-Native-Fraud-Intelligence-Copilot/tests -v
```

The fakes cover corpus/configuration/embedding contracts, isolated `Fraud*` graph queries, hybrid retrieval, evidence and eight-tool contracts, agent citation and memory behavior, evaluation metrics, FastAPI endpoints, and the entity-circuit UI. The four-case live evaluation also checks route recall, evidence-source hits, terminology, citation integrity, calibrated risk language, and bounded investigations.

Neither suite covers live connectivity, real embeddings/model behavior, index readiness, or end-to-end grounding. When changing a retrieval query, schema, grounding contract, or API shape, update the focused fake-based tests and manually run the relevant ingestion/check command against a disposable Neo4j database. For Project 2, inspect positive and negative evaluation cases when changing `RESEARCH_MIN_SEMANTIC_SCORE`; for Project 3, inspect route recall, evidence-source hits, diagnosis terms, and bounded-investigation rate when changing `OPS_MIN_SEMANTIC_SCORE` or agent-round limits; for Project 4, inspect expected source hits, citation integrity, calibrated risk language, and bounded-investigation rate when changing `FRAUD_MIN_SEMANTIC_SCORE`, graph-pattern queries, or agent-round limits.

Source anchors: `1-Basic-Graph-Grounded-Chatbot/tests/`, `2-Hybrid-GraphRAG-Research-Assistant/tests/`, `3-Agentic-Temporal-Incident-Response-Copilot/tests/`, `4-Graph-Native-Fraud-Intelligence-Copilot/tests/`, and the project READMEs.