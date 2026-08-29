"""FastAPI application serving the research assistant and evidence workbench."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from config import AppConfig, ConfigurationError, PROJECT_DIR
from graph_store import ResearchGraphStore
from retrieval import SearchFilters
from runtime import build_assistant


STATIC_DIR = PROJECT_DIR / "static"


class AskRequest(BaseModel):
    question: Annotated[str, Field(min_length=3, max_length=1200)]
    topic: str | None = Field(default=None, max_length=100)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    top_k: int = Field(default=5, ge=1, le=8)


class WebRuntime:
    def __init__(self, config: AppConfig, graph: ResearchGraphStore, client: OpenAI):
        self.config = config
        self.graph = graph
        self.client = client
        self._assistant = None

    def assistant(self):
        if self._assistant is None:
            self._assistant = build_assistant(self.config, self.graph, self.client)
        return self._assistant


def create_app(runtime_factory: Callable[[], WebRuntime] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = runtime_factory() if runtime_factory else _default_runtime()
        runtime.graph.verify_connectivity()
        app.state.runtime = runtime
        yield
        runtime.graph.close()

    app = FastAPI(
        title="Research Signal — Hybrid GraphRAG",
        version="2.0.0",
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        stats = runtime.graph.stats()
        return {
            "ready": runtime.graph.is_ready(),
            "answer_model": runtime.config.answer_model,
            "embedding_model": runtime.config.embedding_model,
            **stats,
        }

    @app.get("/api/meta")
    def metadata() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {
            "topics": runtime.graph.topics(),
            "examples": [
                "How does retrieval-augmented generation combine memory and generation?",
                "Why can evidence in the middle of a long prompt be overlooked?",
                "Compare DPR's dense retrieval with GraphRAG's community summaries.",
                "How do ReAct and Toolformer approach external actions differently?",
            ],
        }

    @app.post("/api/ask")
    def ask(request: AskRequest) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        try:
            filters = SearchFilters(request.topic, request.year_from, request.year_to)
            return runtime.assistant().ask(
                request.question,
                top_k=request.top_k,
                filters=filters,
            ).as_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 503 if "not ready" in str(exc).lower() else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except (DriverError, Neo4jError, OpenAIError) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"A retrieval dependency failed: {exc}",
            ) from exc

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _default_runtime() -> WebRuntime:
    try:
        config = AppConfig.from_env()
    except ConfigurationError as exc:
        raise RuntimeError(str(exc)) from exc
    graph = ResearchGraphStore(config.neo4j)
    client = OpenAI(api_key=config.openai_api_key)
    return WebRuntime(config, graph, client)


app = create_app()
