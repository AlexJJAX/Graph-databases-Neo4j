"""FastAPI control-room workbench for multi-turn incident investigations."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from config import AppConfig, ConfigurationError, PROJECT_DIR
from graph_store import OperationsGraphStore
from memory import SessionMemory
from runtime import build_agent


STATIC_DIR = PROJECT_DIR / "static"


class InvestigateRequest(BaseModel):
    question: Annotated[str, Field(min_length=3, max_length=1600)]
    session_id: str | None = Field(default=None, min_length=8, max_length=100)


class WebRuntime:
    def __init__(
        self,
        config: AppConfig,
        graph: OperationsGraphStore,
        client: Any,
        memory: SessionMemory | None = None,
    ):
        self.config = config
        self.graph = graph
        self.client = client
        self.memory = memory or SessionMemory()
        self._agent = None

    def agent(self):
        if self._agent is None:
            self._agent = build_agent(self.config, self.graph, self.client)
        return self._agent


def create_app(runtime_factory: Callable[[], WebRuntime] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = runtime_factory() if runtime_factory else _default_runtime()
        runtime.graph.verify_connectivity()
        app.state.runtime = runtime
        yield
        runtime.graph.close()

    app = FastAPI(
        title="Northstar Ops — Agentic Temporal GraphRAG",
        version="3.0.0",
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {
            "ready": runtime.graph.is_ready(),
            "agent_model": runtime.config.agent_model,
            "embedding_model": runtime.config.embedding_model,
            "read_only_tools": True,
            **runtime.graph.stats(),
        }

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {
            "incidents": runtime.graph.incidents(),
            "services": runtime.graph.services(),
            "examples": [
                "Investigate INC-104. What changed, what is the leading hypothesis, and what contradicts it?",
                "What is the plausible blast radius if payment-api is degraded during INC-104?",
                "Which historical incident is most similar to INC-104 and why?",
                "Which safe checks should the operator run next for INC-104?",
            ],
        }

    @app.get("/api/topology")
    def topology(
        incident_id: Annotated[str | None, Query(max_length=40)] = None,
    ) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        graph = runtime.graph.topology(incident_id)
        return {
            "graph": graph,
            "timeline": runtime.graph.timeline(incident_id) if incident_id else [],
        }

    @app.post("/api/investigate")
    def investigate(request: InvestigateRequest) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        session_id = request.session_id or runtime.memory.new_id()
        try:
            result = runtime.agent().investigate(
                request.question,
                history=runtime.memory.history(session_id),
            )
            runtime.memory.remember(session_id, request.question, result)
            return {"session_id": session_id, **result.as_dict()}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 503 if "not ready" in str(exc).lower() else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except (DriverError, Neo4jError, OpenAIError) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"An investigation dependency failed: {exc}",
            ) from exc

    @app.delete("/api/sessions/{session_id}")
    def clear_session(session_id: str) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {"cleared": runtime.memory.clear(session_id)}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _default_runtime() -> WebRuntime:
    try:
        config = AppConfig.from_env()
    except ConfigurationError as exc:
        raise RuntimeError(str(exc)) from exc
    graph = OperationsGraphStore(config.neo4j)
    client = OpenAI(api_key=config.openai_api_key)
    return WebRuntime(config, graph, client)


app = create_app()
