"""Configuration for the graph-native fraud intelligence copilot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PROJECT_DIR.parent
AGENT_MODEL = "gpt-5.6-luna"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
VECTOR_INDEX_NAME = "fraud_chunk_embedding"
FULLTEXT_INDEX_NAME = "fraud_chunk_fulltext"
MAX_AGENT_ROUNDS = 6
MAX_GRAPH_HOPS = 4


class ConfigurationError(ValueError):
    """Raised when required environment configuration is unavailable."""


def load_repository_env() -> None:
    load_dotenv(REPOSITORY_ROOT / ".env", override=False)


def _required(name: str) -> str:
    value = os.getenv(name, "")
    if not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True, slots=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        load_repository_env()
        return cls(
            uri=_required("NEO4J_URI").strip(),
            username=_required("NEO4J_USERNAME").strip(),
            password=_required("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
        )


@dataclass(frozen=True, slots=True)
class AppConfig:
    neo4j: Neo4jConfig
    openai_api_key: str
    agent_model: str = AGENT_MODEL
    embedding_model: str = EMBEDDING_MODEL
    embedding_dimensions: int = EMBEDDING_DIMENSIONS
    minimum_semantic_score: float = 0.24
    max_agent_rounds: int = MAX_AGENT_ROUNDS

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_repository_env()
        try:
            threshold = float(os.getenv("FRAUD_MIN_SEMANTIC_SCORE", "0.24"))
        except ValueError as exc:
            raise ConfigurationError("FRAUD_MIN_SEMANTIC_SCORE must be a number") from exc
        if not 0 <= threshold <= 1:
            raise ConfigurationError("FRAUD_MIN_SEMANTIC_SCORE must be between 0 and 1")
        try:
            rounds = int(os.getenv("FRAUD_MAX_AGENT_ROUNDS", str(MAX_AGENT_ROUNDS)))
        except ValueError as exc:
            raise ConfigurationError("FRAUD_MAX_AGENT_ROUNDS must be an integer") from exc
        if not 3 <= rounds <= 8:
            raise ConfigurationError("FRAUD_MAX_AGENT_ROUNDS must be between 3 and 8")
        return cls(
            neo4j=Neo4jConfig.from_env(),
            openai_api_key=_required("OPENAI_API_KEY"),
            minimum_semantic_score=threshold,
            max_agent_rounds=rounds,
        )
