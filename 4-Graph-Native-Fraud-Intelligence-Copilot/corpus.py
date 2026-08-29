"""Validation and deterministic chunk preparation for the fraud corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


class CorpusError(ValueError):
    """Raised when the synthetic fraud dataset is internally inconsistent."""


def _unique(items: Iterable[dict[str, Any]], key: str, label: str) -> set[str]:
    values = [str(item.get(key, "")).strip() for item in items]
    if any(not value for value in values):
        raise CorpusError(f"Every {label} requires {key}")
    if len(values) != len(set(values)):
        raise CorpusError(f"Duplicate {label} {key}")
    return set(values)


def _timestamp(value: str, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CorpusError(f"Invalid ISO timestamp for {field}: {value}") from exc
    if parsed.tzinfo is None:
        raise CorpusError(f"Timestamp must include a timezone for {field}: {value}")


def _references(values: Iterable[str], known: set[str], message: str) -> None:
    missing = set(values) - known
    if missing:
        raise CorpusError(f"{message}: {', '.join(sorted(missing))}")


def load_fraud_network(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "institution", "persons", "accounts", "devices", "addresses", "phones",
        "merchants", "transactions", "alerts", "cases", "documents",
    }
    missing = required - payload.keys()
    if missing:
        raise CorpusError("Missing corpus sections: " + ", ".join(sorted(missing)))

    person_ids = _unique(payload["persons"], "personId", "person")
    account_ids = _unique(payload["accounts"], "accountId", "account")
    device_ids = _unique(payload["devices"], "deviceId", "device")
    address_ids = _unique(payload["addresses"], "addressId", "address")
    phone_ids = _unique(payload["phones"], "phoneId", "phone")
    merchant_ids = _unique(payload["merchants"], "merchantId", "merchant")
    transaction_ids = _unique(payload["transactions"], "transactionId", "transaction")
    alert_ids = _unique(payload["alerts"], "alertId", "alert")
    case_ids = _unique(payload["cases"], "caseId", "case")
    _unique(payload["documents"], "documentId", "document")

    for person in payload["persons"]:
        _references(person.get("accountIds", []), account_ids, f"Unknown account for {person['personId']}")
        _references(person.get("deviceIds", []), device_ids, f"Unknown device for {person['personId']}")
        _references(person.get("addressIds", []), address_ids, f"Unknown address for {person['personId']}")
        _references(person.get("phoneIds", []), phone_ids, f"Unknown phone for {person['personId']}")
    controlled = [account for person in payload["persons"] for account in person.get("accountIds", [])]
    if set(controlled) != account_ids or len(controlled) != len(set(controlled)):
        raise CorpusError("Every account must have exactly one controlling person")

    for transaction in payload["transactions"]:
        if transaction["senderAccountId"] not in account_ids:
            raise CorpusError(f"Unknown sender for {transaction['transactionId']}")
        receiver = transaction.get("receiverAccountId")
        merchant = transaction.get("merchantId")
        if bool(receiver) == bool(merchant):
            raise CorpusError(f"{transaction['transactionId']} requires exactly one receiver account or merchant")
        if receiver and receiver not in account_ids:
            raise CorpusError(f"Unknown receiver for {transaction['transactionId']}")
        if merchant and merchant not in merchant_ids:
            raise CorpusError(f"Unknown merchant for {transaction['transactionId']}")
        if transaction.get("deviceId") and transaction["deviceId"] not in device_ids:
            raise CorpusError(f"Unknown transaction device for {transaction['transactionId']}")
        if float(transaction["amount"]) <= 0:
            raise CorpusError(f"Transaction amount must be positive: {transaction['transactionId']}")
        _timestamp(transaction["occurredAt"], "occurredAt")

    for alert in payload["alerts"]:
        _references(alert.get("accountIds", []), account_ids, f"Unknown account for {alert['alertId']}")
        _references(alert.get("transactionIds", []), transaction_ids, f"Unknown transaction for {alert['alertId']}")
        if alert.get("caseId") and alert["caseId"] not in case_ids:
            raise CorpusError(f"Unknown case for {alert['alertId']}")
        _timestamp(alert["createdAt"], "createdAt")

    referenced_alerts: list[str] = []
    for case in payload["cases"]:
        _references(case.get("alertIds", []), alert_ids, f"Unknown alert for {case['caseId']}")
        referenced_alerts.extend(case.get("alertIds", []))
        _timestamp(case["openedAt"], "openedAt")
    assigned = {alert["alertId"] for alert in payload["alerts"] if alert.get("caseId")}
    if assigned != set(referenced_alerts) or len(referenced_alerts) != len(set(referenced_alerts)):
        raise CorpusError("Case alertIds and alert caseId assignments must agree")

    for document in payload["documents"]:
        sections = document.get("sections") or []
        if not sections or any(not section.get("heading") or not section.get("text") for section in sections):
            raise CorpusError(f"{document['documentId']} requires complete sections")
        _references(document.get("relatedAccountIds", []), account_ids, f"Unknown document account for {document['documentId']}")
        _references(document.get("relatedDeviceIds", []), device_ids, f"Unknown document device for {document['documentId']}")
        _references(document.get("relatedMerchantIds", []), merchant_ids, f"Unknown document merchant for {document['documentId']}")
    return payload


def content_hash(*values: str) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def build_document_rows(
    payload: dict[str, Any],
    existing: dict[str, dict[str, Any]],
    embedder: Any,
    *,
    batch_size: int = 32,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    chunks: list[dict[str, Any]] = []
    for document in payload["documents"]:
        for sequence, section in enumerate(document["sections"]):
            chunk_id = f"fraud:{document['documentId']}:{sequence:02d}"
            text = section["text"].strip()
            chunks.append({
                "chunkId": chunk_id,
                "documentId": document["documentId"],
                "documentType": document["documentType"],
                "title": document["title"],
                "section": section["heading"],
                "sequence": sequence,
                "text": text,
                "embeddingText": f"{document['title']}\n{section['heading']}\n{text}",
                "contentHash": content_hash(document["title"], section["heading"], text),
            })
    to_embed = [
        chunk for chunk in chunks
        if existing.get(chunk["chunkId"], {}).get("contentHash") != chunk["contentHash"]
        or not existing.get(chunk["chunkId"], {}).get("hasEmbedding", False)
    ]
    vectors = embedder.embed_documents(
        [chunk["embeddingText"] for chunk in to_embed], batch_size=batch_size
    ) if to_embed else []
    vector_by_id = {
        chunk["chunkId"]: vector for chunk, vector in zip(to_embed, vectors, strict=True)
    }
    chunk_rows = [
        {key: value for key, value in chunk.items() if key != "embeddingText"}
        | {"embedding": vector_by_id.get(chunk["chunkId"])}
        for chunk in chunks
    ]
    documents = [
        {key: value for key, value in item.items() if key != "sections"}
        | {"chunkIds": [chunk["chunkId"] for chunk in chunk_rows if chunk["documentId"] == item["documentId"]]}
        for item in payload["documents"]
    ]
    return documents, chunk_rows, len(chunk_rows), len(to_embed)
