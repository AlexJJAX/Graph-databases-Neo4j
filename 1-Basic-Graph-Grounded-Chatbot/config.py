"""Configuration loaded from the repository-level .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PROJECT_DIR.parent
OPENAI_MODEL = "gpt-5.6-luna"


class ConfigurationError(ValueError):
    """Raised when a required environment variable is missing."""


def load_repository_env() -> None:
    """Load local secrets without replacing explicitly exported variables."""
    load_dotenv(REPOSITORY_ROOT / ".env", override=False)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
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
            uri=_required("NEO4J_URI"),
            username=_required("NEO4J_USERNAME"),
            password=_required("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
        )


@dataclass(frozen=True, slots=True)
class AppConfig:
    neo4j: Neo4jConfig
    openai_api_key: str
    openai_model: str = OPENAI_MODEL

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_repository_env()
        return cls(
            neo4j=Neo4jConfig.from_env(),
            openai_api_key=_required("OPENAI_API_KEY"),
        )
