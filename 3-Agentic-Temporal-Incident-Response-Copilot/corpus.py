"""Validation and deterministic chunk preparation for the operations corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


class CorpusError(ValueError):
    """Raised when the synthetic operations dataset is internally inconsistent."""


def _unique(items: Iterable[dict[str, Any]], key: str, label: str) -> set[str]:
    values = [str(item.get(key, "")).strip() for item in items]
    if any(not value for value in values):
        raise CorpusError(f"Every {label} requires {key}")
    if len(values) != len(set(values)):
        raise CorpusError(f"Duplicate {label} {key}")
    return set(values)


def _timestamp(value: str, field: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CorpusError(f"Invalid ISO timestamp for {field}: {value}") from exc


def load_platform(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "platform",
        "teams",
        "services",
        "commits",
        "deployments",
        "incidents",
        "alerts",
        "runbooks",
        "postmortems",
    }
    missing = required - payload.keys()
    if missing:
        raise CorpusError("Missing corpus sections: " + ", ".join(sorted(missing)))

    team_ids = _unique(payload["teams"], "teamId", "team")
    service_ids = _unique(payload["services"], "serviceId", "service")
    commit_ids = _unique(payload["commits"], "sha", "commit")
    deployment_ids = _unique(payload["deployments"], "deploymentId", "deployment")
    incident_ids = _unique(payload["incidents"], "incidentId", "incident")
    alert_ids = _unique(payload["alerts"], "alertId", "alert")
    _unique(payload["runbooks"], "runbookId", "runbook")
    _unique(payload["postmortems"], "postmortemId", "postmortem")

    for service in payload["services"]:
        if service["teamId"] not in team_ids:
            raise CorpusError(f"Unknown team for {service['serviceId']}")
        for dependency in service.get("dependsOn", []):
            if dependency["serviceId"] not in service_ids:
                raise CorpusError(f"Unknown service dependency: {dependency['serviceId']}")
            if dependency["serviceId"] == service["serviceId"]:
                raise CorpusError("A service cannot depend on itself")

    for deployment in payload["deployments"]:
        if deployment["serviceId"] not in service_ids:
            raise CorpusError(f"Unknown deployment service: {deployment['serviceId']}")
        if deployment["sha"] not in commit_ids:
            raise CorpusError(f"Unknown deployment commit: {deployment['sha']}")
        _timestamp(deployment["deployedAt"], "deployedAt")

    for incident in payload["incidents"]:
        _timestamp(incident["startedAt"], "startedAt")
        if incident.get("endedAt"):
            _timestamp(incident["endedAt"], "endedAt")
        if not set(incident["impactedServices"]).issubset(service_ids):
            raise CorpusError(f"Unknown impacted service in {incident['incidentId']}")
        if not set(incident.get("precededBy", [])).issubset(deployment_ids):
            raise CorpusError(f"Unknown preceding deployment in {incident['incidentId']}")

    for alert in payload["alerts"]:
        if alert["serviceId"] not in service_ids:
            raise CorpusError(f"Unknown alert service: {alert['serviceId']}")
        if alert["incidentId"] not in incident_ids:
            raise CorpusError(f"Unknown alert incident: {alert['incidentId']}")
        _timestamp(alert["firedAt"], "firedAt")
        if alert.get("clearedAt"):
            _timestamp(alert["clearedAt"], "clearedAt")

    for runbook in payload["runbooks"]:
        if not set(runbook["serviceIds"]).issubset(service_ids):
            raise CorpusError(f"Unknown runbook service in {runbook['runbookId']}")
        _validate_sections(runbook, "runbookId")
    for postmortem in payload["postmortems"]:
        if postmortem["incidentId"] not in incident_ids:
            raise CorpusError(
                f"Unknown postmortem incident: {postmortem['incidentId']}"
            )
        _validate_sections(postmortem, "postmortemId")

    if alert_ids != {
        alert_id
        for incident in payload["incidents"]
        for alert_id in incident.get("alertIds", [])
    }:
        raise CorpusError("Incident alertIds must reference every alert exactly once")
    return payload


def _validate_sections(document: dict[str, Any], key: str) -> None:
    sections = document.get("sections") or []
    if not sections:
        raise CorpusError(f"{document[key]} requires at least one section")
    if any(not item.get("heading") or not item.get("text") for item in sections):
        raise CorpusError(f"{document[key]} contains an incomplete section")


def content_hash(*values: str) -> str:
    joined = "\n".join(values).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def build_document_rows(
    payload: dict[str, Any],
    existing: dict[str, dict[str, Any]],
    embedder: Any,
    *,
    batch_size: int = 32,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
    int,
]:
    documents: list[tuple[str, dict[str, Any]]] = [
        *(("runbook", item) for item in payload["runbooks"]),
        *(("postmortem", item) for item in payload["postmortems"]),
    ]
    chunks: list[dict[str, Any]] = []
    for source_type, document in documents:
        source_id = document[f"{source_type}Id"]
        for sequence, section in enumerate(document["sections"]):
            chunk_id = f"{source_type}:{source_id}:{sequence:02d}"
            text = section["text"].strip()
            digest = content_hash(document["title"], section["heading"], text)
            chunks.append(
                {
                    "chunkId": chunk_id,
                    "sourceId": source_id,
                    "sourceType": source_type,
                    "title": document["title"],
                    "section": section["heading"],
                    "sequence": sequence,
                    "text": text,
                    "embeddingText": (
                        f"{document['title']}\n{section['heading']}\n{text}"
                    ),
                    "contentHash": digest,
                }
            )

    to_embed = [
        chunk
        for chunk in chunks
        if existing.get(chunk["chunkId"], {}).get("contentHash")
        != chunk["contentHash"]
        or not existing.get(chunk["chunkId"], {}).get("hasEmbedding", False)
    ]
    vectors = (
        embedder.embed_documents(
            [chunk["embeddingText"] for chunk in to_embed], batch_size=batch_size
        )
        if to_embed
        else []
    )
    vector_by_id = {
        chunk["chunkId"]: vector
        for chunk, vector in zip(to_embed, vectors, strict=True)
    }
    chunk_rows = [
        {
            key: value
            for key, value in chunk.items()
            if key != "embeddingText"
        }
        | {"embedding": vector_by_id.get(chunk["chunkId"])}
        for chunk in chunks
    ]
    runbooks = [
        {key: value for key, value in item.items() if key != "sections"}
        | {
            "chunkIds": [
                chunk["chunkId"]
                for chunk in chunk_rows
                if chunk["sourceType"] == "runbook"
                and chunk["sourceId"] == item["runbookId"]
            ]
        }
        for item in payload["runbooks"]
    ]
    postmortems = [
        {key: value for key, value in item.items() if key != "sections"}
        | {
            "chunkIds": [
                chunk["chunkId"]
                for chunk in chunk_rows
                if chunk["sourceType"] == "postmortem"
                and chunk["sourceId"] == item["postmortemId"]
            ]
        }
        for item in payload["postmortems"]
    ]
    return runbooks, postmortems, chunk_rows, len(chunk_rows), len(to_embed)
