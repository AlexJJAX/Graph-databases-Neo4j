"""Shared construction of Project 2 runtime services."""

from __future__ import annotations

from openai import OpenAI

from assistant import ResearchAssistant
from config import AppConfig
from embeddings import OpenAI2Embedder
from graph_store import ResearchGraphStore
from retrieval import ResearchRetriever


def build_assistant(
    config: AppConfig,
    graph: ResearchGraphStore,
    client: OpenAI,
) -> ResearchAssistant:
    if not graph.is_ready():
        raise RuntimeError(
            "Research corpus is not ready. Run ingest.py before asking questions."
        )
    embedder = OpenAI2Embedder(
        client,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
    )
    retriever = ResearchRetriever(
        driver=graph.driver,
        database=graph.database,
        embedder=embedder,
        minimum_semantic_score=config.minimum_semantic_score,
    )
    return ResearchAssistant(retriever, client, config.answer_model)
