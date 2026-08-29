"""FastAPI fraud-intelligence workbench with graph-backed investigation memory."""

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
from graph_store import FraudGraphStore
from memory import GraphInvestigationMemory
from runtime import build_agent


STATIC_DIR = PROJECT_DIR / "static"


class InvestigateRequest(BaseModel):
    question: Annotated[str, Field(min_length=3, max_length=1800)]
    alert_id: str | None = Field(default=None, max_length=50)
    session_id: str | None = Field(default=None, min_length=8, max_length=100)


class WebRuntime:
    def __init__(self, config: AppConfig, graph: FraudGraphStore, client: Any, memory: Any | None = None):
        self.config, self.graph, self.client = config, graph, client
        self.memory = memory or GraphInvestigationMemory(graph)
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

    app = FastAPI(title="Northstar Financial · Graph-Native Fraud Intelligence", version="4.0.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {"ready": runtime.graph.is_ready(), "agent_model": runtime.config.agent_model,
                "embedding_model": runtime.config.embedding_model, "read_only_tools": True,
                "persistent_graph_memory": True, **runtime.graph.stats()}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        return {
            "alerts": runtime.graph.alerts(), "cases": runtime.graph.cases(),
            "examples": [
                "Investigate the shared identifiers and fund-flow cycle. What is observed versus inferred?",
                "How concentrated is the cluster's cash-out to digital-goods merchants?",
                "Which historical case is most similar, and what evidence contradicts that analogy?",
                "What additional evidence should a human investigator collect before escalation?",
            ],
        }

    @app.get("/api/network/{alert_id}")
    def network(alert_id: str) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        context = runtime.graph.alert_context(alert_id.upper())
        if context is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"alert": context, "graph": runtime.graph.alert_network(alert_id.upper()),
                "timeline": runtime.graph.transaction_timeline(alert_id.upper())}

    @app.post("/api/investigate")
    def investigate(request: InvestigateRequest) -> dict[str, Any]:
        runtime: WebRuntime = app.state.runtime
        session_id = request.session_id or runtime.memory.new_id()
        alert_id = request.alert_id.strip().upper() if request.alert_id else None
        scoped_question = f"Selected alert: {alert_id}. {request.question}" if alert_id else request.question
        try:
            result = runtime.agent().investigate(scoped_question, history=runtime.memory.history(session_id))
            runtime.memory.remember(session_id, scoped_question, result)
            return {"session_id": session_id, "alert_id": alert_id, **result.as_dict()}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503 if "not ready" in str(exc).lower() else 502, detail=str(exc)) from exc
        except (DriverError, Neo4jError, OpenAIError) as exc:
            raise HTTPException(status_code=502, detail=f"An investigation dependency failed: {exc}") from exc

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
    graph = FraudGraphStore(config.neo4j)
    return WebRuntime(config, graph, OpenAI(api_key=config.openai_api_key))


app = create_app()
