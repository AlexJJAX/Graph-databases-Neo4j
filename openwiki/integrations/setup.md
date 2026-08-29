# Integration and setup

## Shared Python project

The root `pyproject.toml` requires Python `>=3.13` and the locked `uv` environment now includes `neo4j`, `openai`, `python-dotenv`, `neo4j-graphrag`, `fastapi`, and `uvicorn`. Use the repository's `uv` project and lockfile for repeatable commands.

## Movie chatbot configuration

Create a repository-level `.env` with these names; do not commit values:

- `OPENAI_API_KEY`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- optional `NEO4J_DATABASE` (defaults to `neo4j`)

`config.py` loads this file without overriding explicitly exported variables. `app.py --check` verifies that required configuration is present and the configured Neo4j database is reachable. The chatbot uses the default model `gpt-5.6-luna`.

The normal Project 1 integration sequence is: seed a local Neo4j instance, run `--check`, then ask questions through `app.py`. Project 2 uses the same repository-level Neo4j/OpenAI credentials, but creates `Research*` schema objects and requires its vector and full-text indexes to be online before retrieval. Its fixed models are `text-embedding-3-small` at 1,536 dimensions and `gpt-5.6-luna`; `RESEARCH_MIN_SEMANTIC_SCORE` is optional and defaults to `0.25`. The `OpenAI2Embedder` adapter bridges the OpenAI 2.x SDK to `neo4j-graphrag` without using that package's incompatible optional OpenAI extra.

Project 2’s normal sequence is `ingest.py --dry-run`, `ingest.py`, then `ask.py`, `evaluate.py`, or the FastAPI server. It owns one Neo4j driver for its runtime lifetime and closes it when the web lifespan ends.

Project 3 uses the same credentials and creates an isolated `Ops*` schema with `ops_chunk_embedding` and `ops_chunk_fulltext` indexes. It fixes the agent model at `gpt-5.6-luna`, uses `text-embedding-3-small` with 1,536 dimensions, defaults `OPS_MIN_SEMANTIC_SCORE` to `0.22`, and bounds `OPS_MAX_AGENT_ROUNDS` to 2–8 (default 5). Run `3-Agentic-Temporal-Incident-Response-Copilot/ingest.py --dry-run` before live ingestion; normal operation requires both Neo4j and OpenAI. Its FastAPI lifespan verifies connectivity and closes the graph driver on shutdown. Web session memory is process-local and is not persistent organizational memory.

Project 4 uses the same credentials and creates an isolated `Fraud*` schema with `fraud_chunk_embedding` and `fraud_chunk_fulltext` indexes. It fixes the agent model at `gpt-5.6-luna`, uses `text-embedding-3-small` with 1,536 dimensions, defaults `FRAUD_MIN_SEMANTIC_SCORE` to `0.24`, and bounds `FRAUD_MAX_AGENT_ROUNDS` to 3–8 (default 6). Run `4-Graph-Native-Fraud-Intelligence-Copilot/ingest.py --dry-run` before live ingestion. Its FastAPI lifespan verifies connectivity and closes the graph driver; investigation summaries persist in Neo4j rather than process-local web memory.

## Separate quick example

`neo4j_basic/quick_example.py` is a minimal `Person`/`KNOWS` example. It defaults to `bolt://localhost:7687`, hardcodes database `neo4j`, loads `.env` with `override=True`, creates Arthur's links to Guinevere, Lancelot, and Merlin, and prints sorted friends. Its environment precedence therefore differs from the movie chatbot; it is a standalone demonstration rather than shared application infrastructure.

Source anchors: `pyproject.toml`, `README.md`, `1-Basic-Graph-Grounded-Chatbot/.env.example`, `1-Basic-Graph-Grounded-Chatbot/config.py`, and `neo4j_basic/quick_example.py`.