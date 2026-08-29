"""Construction of Project 3's graph, retrieval, tools, and agent services."""

from __future__ import annotations

from typing import Any

from agent import IncidentInvestigationAgent
from config import AppConfig
from embeddings import OpenAIEmbedder
from graph_store import OperationsGraphStore
from retrieval import OperationalRetriever
from tools import InvestigationTools


def build_agent(
    config: AppConfig,
    graph: OperationsGraphStore,
    client: Any,
) -> IncidentInvestigationAgent:
    if not graph.is_ready():
        raise RuntimeError(
            "Operations graph is not ready. Run ingest.py before investigating."
        )
    embedder = OpenAIEmbedder(
        client,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
    )
    retriever = OperationalRetriever(
        driver=graph.driver,
        database=graph.database,
        embedder=embedder,
        minimum_semantic_score=config.minimum_semantic_score,
    )
    tools = InvestigationTools(graph, retriever)
    return IncidentInvestigationAgent(
        tools,
        client,
        config.agent_model,
        max_rounds=config.max_agent_rounds,
    )
