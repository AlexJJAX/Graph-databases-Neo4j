# Research assistant workflow

## Prepare the graph

From the repository root, run `uv run python 2-Hybrid-GraphRAG-Research-Assistant/ingest.py --dry-run` to validate the corpus without network or database I/O. Run `ingest.py` normally to create the isolated schema, wait for vector/full-text indexes, incrementally embed chunks, and upsert the graph. A ready graph has populated `ResearchChunk` nodes and both search indexes online.

## Retrieve and answer

`ask.py` accepts a question plus optional `--topic`, `--year-from`, `--year-to`, and `--top-k` filters. `ResearchRetriever` embeds the question, sanitizes it for Lucene, retrieves up to three times the requested count (capped at 24), and uses linear hybrid ranking with 65% vector and 35% full-text weight. It deduplicates chunks, rejects semantic scores below the configured threshold (default `0.25`), expands graph neighbors, and assigns `[R1]`, `[R2]`, … evidence IDs.

`ResearchAssistant` sends one JSON evidence package to `gpt-5.6-luna`; unlike Project 1, there is no tool-calling loop. The model must use only supplied evidence and cite factual claims. Unknown citations, uncited answers when evidence exists, and empty model output raise errors. With no qualifying evidence, the assistant returns a deterministic limitation message and does not call the answer model.

## Web workbench

Start the UI with:

```bash
uv run uvicorn web:app --app-dir 2-Hybrid-GraphRAG-Research-Assistant \
  --host 127.0.0.1 --port 8123
```

`GET /api/status` reports readiness, model names, and graph counts. `GET /api/meta` exposes topics and examples. `POST /api/ask` accepts a 3–1200 character question, optional topic/year filters, and `top_k` from 1 to 8, returning the answer, evidence ledger, projected graph, and timing/token metrics. The browser renders citations, source links, ranked signals, and an inspectable evidence constellation; that graph is only the retrieved projection, not unrestricted database browsing.

## Evaluate retrieval

Run `uv run python 2-Hybrid-GraphRAG-Research-Assistant/evaluate.py --top-k 5` after ingestion. The ten-case set measures hit rate, mean reciprocal rank, and rejection of negative/out-of-domain questions. It evaluates retrieval rather than generated-answer factuality, citation correctness, or graph quality. Scores depend on the embedding model and semantic threshold, so inspect positive and negative cases before tuning `RESEARCH_MIN_SEMANTIC_SCORE`.

Source anchors: `ingest.py`, `retrieval.py`, `assistant.py`, `ask.py`, `web.py`, `evaluate.py`, `evals/questions.json`, and the project README.