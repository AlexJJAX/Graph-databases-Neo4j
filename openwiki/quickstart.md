# Graph_databases repository quickstart

## What this repository contains

This is a Python 3.13+ portfolio of Neo4j-powered AI examples. It now contains four implemented projects: [Basic Graph-Grounded Chatbot](../1-Basic-Graph-Grounded-Chatbot/README.md), a movie assistant that retrieves a bounded Neo4j subgraph; [Hybrid GraphRAG Research Assistant](../2-Hybrid-GraphRAG-Research-Assistant/README.md), a literature workbench combining vector, full-text, and graph retrieval; [Agentic Temporal Incident Response Copilot](../3-Agentic-Temporal-Incident-Response-Copilot/README.md), a read-only operations investigator that iteratively routes across temporal graph, topology, hybrid document, runbook, and postmortem tools; and [Graph-Native Fraud Intelligence & Investigation Copilot](../4-Graph-Native-Fraud-Intelligence-Copilot/README.md), a bounded fraud workbench combining identity and transaction graphs, hybrid evidence retrieval, persistent investigation memory, and citation review. The repository also includes a small standalone Neo4j friend-graph example in `neo4j_basic/quick_example.py`.

Project 1 demonstrates baseline GraphRAG with literal graph filters and tool calling. Project 2 adds semantic retrieval, excerpt-level citations, incremental corpus ingestion, evaluation, and a FastAPI evidence UI. Project 3 adds bounded multi-step hypothesis testing, temporal change correlation, blast-radius analysis, citation-validated incident dossiers, and a control-room UI. Project 4 adds identity resolution, money-flow and cycle analysis, fraud-typology retrieval, persistent Neo4j turn memory, and deterministic citation review without autonomous fraud decisions. All keep the model behind an inspectable evidence boundary.

## Start here

- [Architecture overview](architecture/overview.md) — runtime components and the project-specific grounded request paths.
- [Movie graph domain](domain/movie-graph.md) — labels, relationships, seed data, and retrieval limits.
- [Research graph domain](domain/research-graph.md) — curated corpus, chunks, labels, indexes, and incremental ingestion.
- [Movie-question workflow](workflows/movie-question.md) — CLI modes and grounding behavior.
- [Research assistant workflow](workflows/research-assistant.md) — ingestion, CLI/API questions, evaluation, and evidence behavior.
- [Incident-response workflow](workflows/incident-response.md) — bounded agent investigations through CLI, API, and control-room UI.
- [Operations graph domain](domain/operations-graph.md) — temporal service graph, synthetic corpus, and operational evidence model.
- [Fraud-investigation workflow](workflows/fraud-investigation.md) — alert-scoped investigation through CLI, API, persistent memory, and evidence review.
- [Fraud graph domain](domain/fraud-graph.md) — identity graph, transaction network, hybrid evidence indexes, and safety boundaries.
- [Integration and setup](integrations/setup.md) — Python, Neo4j, OpenAI, and environment configuration for all four projects.
- [Testing guidance](testing/guidance.md) — project-specific commands, fake-based coverage, and boundaries.
- [Operations/update workflow](operations/update-workflow.md) — the GitHub Actions job that maintains this wiki.
- [Source map](source-map.md) — where to continue reading in the repository.

## Run Project 1

From the repository root, create a repository-level `.env` using the variable names shown in `README.md` and the project `.env.example`. Then:

```bash
uv run python 1-Basic-Graph-Grounded-Chatbot/seed.py
uv run python 1-Basic-Graph-Grounded-Chatbot/app.py --check
uv run python 1-Basic-Graph-Grounded-Chatbot/app.py \
  --question "Which Christopher Nolan movies are rated at least 8.5?" \
  --show-context
uv run python 1-Basic-Graph-Grounded-Chatbot/app.py --show-context
```

The seed command creates constraints/indexes and loads the six-record demo catalog only when the target database contains no `Movie` nodes. `--check` verifies configuration and Neo4j without making an OpenAI request. The final command starts the interactive REPL; type `quit` or `exit` to leave.

## Run Project 3

Validate and ingest the synthetic operations graph, then investigate from the terminal or control-room UI:

```bash
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/ingest.py --dry-run
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/ingest.py
uv run python 3-Agentic-Temporal-Incident-Response-Copilot/investigate.py \
  "Investigate INC-104. What changed, what is the leading hypothesis, and what contradicts it?" \
  --show-trace
uv run uvicorn web:app --app-dir 3-Agentic-Temporal-Incident-Response-Copilot \
  --host 127.0.0.1 --port 8133
```

Open `http://127.0.0.1:8133` for topology, incident timeline, cited dossier, evidence ledger, and replayable tool trace. Tools are read-only; the agent cannot execute remediation.

## Run Project 4

Validate and ingest the synthetic fraud network, then investigate from the terminal or entity-circuit workbench:

```bash
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py --dry-run
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py
uv run python 4-Graph-Native-Fraud-Intelligence-Copilot/investigate.py \
  "Investigate ALRT-9001. Trace shared identifiers, fund flows, cycles, and counter-evidence." \
  --show-trace
uv run uvicorn web:app --app-dir 4-Graph-Native-Fraud-Intelligence-Copilot \
  --host 127.0.0.1 --port 8144
```

Open `http://127.0.0.1:8144` for the alert queue, entity circuit, transaction timeline, cited dossier, evidence ledger, and tool trace. The tools are read-only; alerts and graph patterns are signals for human review, not autonomous fraud determinations.

## Run Project 2

Validate and ingest the isolated research corpus, then use the CLI or evidence workbench:

```bash
uv run python 2-Hybrid-GraphRAG-Research-Assistant/ingest.py --dry-run
uv run python 2-Hybrid-GraphRAG-Research-Assistant/ingest.py
uv run python 2-Hybrid-GraphRAG-Research-Assistant/ask.py \
  "How does RAG combine parametric and non-parametric memory?"
uv run uvicorn web:app --app-dir 2-Hybrid-GraphRAG-Research-Assistant \
  --host 127.0.0.1 --port 8123
```

Open `http://127.0.0.1:8123` for ranked excerpts, citations, metrics, source links, and the retrieved evidence graph. Ingestion embeds only changed or previously unembedded chunks; normal operation requires Neo4j and OpenAI credentials.

Run each project’s offline unit tests with:

```bash
uv run python -m unittest discover -s 1-Basic-Graph-Grounded-Chatbot/tests -v
uv run python -m unittest discover -s 2-Hybrid-GraphRAG-Research-Assistant/tests -v
uv run python -m unittest discover -s 3-Agentic-Temporal-Incident-Response-Copilot/tests -v
uv run python -m unittest discover -s 4-Graph-Native-Fraud-Intelligence-Copilot/tests -v
```

## Repository conventions

- Runtime dependencies and the Python version are defined in `pyproject.toml`; `uv.lock` records the resolved environment.
- The application reads the repository-root `.env` without overriding explicitly exported variables. Do not commit secrets.
- `openwiki/INSTRUCTIONS.md` is user-authored control metadata. Generated documentation belongs under `openwiki/`, and the scheduled workflow proposes changes through a pull request.

## Backlog

- **Production deployment and end-to-end runbook** — source anchor: `.github/workflows/openwiki-update.yml` and the three project entry points; no application deployment automation or live integration test is present.

