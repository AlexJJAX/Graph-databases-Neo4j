"""Construction of the fraud graph, retrieval, tools, and agent services."""

from __future__ import annotations

from typing import Any

from agent import FraudInvestigationAgent
from config import AppConfig
from embeddings import OpenAIEmbedder
from graph_store import FraudGraphStore
from retrieval import FraudEvidenceRetriever
from tools import FraudInvestigationTools


def build_agent(config: AppConfig, graph: FraudGraphStore, client: Any) -> FraudInvestigationAgent:
    if not graph.is_ready():
        raise RuntimeError("Fraud graph is not ready. Run ingest.py before investigating.")
    embedder = OpenAIEmbedder(client, model=config.embedding_model, dimensions=config.embedding_dimensions)
    retriever = FraudEvidenceRetriever(
        driver=graph.driver, database=graph.database, embedder=embedder,
        minimum_semantic_score=config.minimum_semantic_score,
    )
    return FraudInvestigationAgent(
        FraudInvestigationTools(graph, retriever), client, config.agent_model,
        max_rounds=config.max_agent_rounds,
    )
