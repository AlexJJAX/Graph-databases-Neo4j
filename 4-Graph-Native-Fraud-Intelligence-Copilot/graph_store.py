"""Neo4j schema, ingestion, bounded fraud patterns, and investigation memory."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from neo4j import GraphDatabase, RoutingControl

from config import EMBEDDING_DIMENSIONS, FULLTEXT_INDEX_NAME, VECTOR_INDEX_NAME, Neo4jConfig


SCHEMA_QUERIES = (
    "CYPHER 25 CREATE CONSTRAINT fraud_person_id_unique IF NOT EXISTS FOR (n:FraudPerson) REQUIRE n.personId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_account_id_unique IF NOT EXISTS FOR (n:FraudAccount) REQUIRE n.accountId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_device_id_unique IF NOT EXISTS FOR (n:FraudDevice) REQUIRE n.deviceId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_address_id_unique IF NOT EXISTS FOR (n:FraudAddress) REQUIRE n.addressId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_phone_id_unique IF NOT EXISTS FOR (n:FraudPhone) REQUIRE n.phoneId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_merchant_id_unique IF NOT EXISTS FOR (n:FraudMerchant) REQUIRE n.merchantId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_transaction_id_unique IF NOT EXISTS FOR (n:FraudTransaction) REQUIRE n.transactionId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_alert_id_unique IF NOT EXISTS FOR (n:FraudAlert) REQUIRE n.alertId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_case_id_unique IF NOT EXISTS FOR (n:FraudCase) REQUIRE n.caseId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_document_id_unique IF NOT EXISTS FOR (n:FraudDocument) REQUIRE n.documentId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_chunk_id_unique IF NOT EXISTS FOR (n:FraudChunk) REQUIRE n.chunkId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_investigation_id_unique IF NOT EXISTS FOR (n:FraudInvestigation) REQUIRE n.sessionId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT fraud_turn_id_unique IF NOT EXISTS FOR (n:FraudTurn) REQUIRE n.turnId IS UNIQUE",
    "CYPHER 25 CREATE INDEX fraud_transaction_time_idx IF NOT EXISTS FOR (n:FraudTransaction) ON (n.occurredAt)",
    "CYPHER 25 CREATE INDEX fraud_alert_time_idx IF NOT EXISTS FOR (n:FraudAlert) ON (n.createdAt)",
    f"CYPHER 25 CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS FOR (n:FraudChunk) ON (n.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBEDDING_DIMENSIONS}, `vector.similarity_function`: 'cosine'}}}}",
    f"CYPHER 25 CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS FOR (n:FraudChunk) ON EACH [n.text, n.title, n.section]",
)


UPSERT_PERSONS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudPerson {personId: row.personId})
SET n.name = row.name, n.riskTier = row.riskTier
RETURN count(n) AS processed
""".strip()

UPSERT_ACCOUNTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudAccount {accountId: row.accountId})
SET n.product = row.product, n.openedAt = date(row.openedAt), n.status = row.status,
    n.balance = row.balance
RETURN count(n) AS processed
""".strip()

UPSERT_DEVICES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudDevice {deviceId: row.deviceId})
SET n.fingerprint = row.fingerprint, n.kind = row.kind, n.trust = row.trust
RETURN count(n) AS processed
""".strip()

UPSERT_ADDRESSES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudAddress {addressId: row.addressId})
SET n.masked = row.masked, n.postcodeSector = row.postcodeSector
RETURN count(n) AS processed
""".strip()

UPSERT_PHONES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudPhone {phoneId: row.phoneId})
SET n.masked = row.masked, n.country = row.country
RETURN count(n) AS processed
""".strip()

UPSERT_MERCHANTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudMerchant {merchantId: row.merchantId})
SET n.name = row.name, n.category = row.category, n.country = row.country,
    n.riskLevel = row.riskLevel
RETURN count(n) AS processed
""".strip()

LINK_IDENTITIES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MATCH (person:FraudPerson {personId: row.personId})
CALL (person) { MATCH (person)-[r:CONTROLS|USES_DEVICE|LIVES_AT|USES_PHONE]->() DELETE r }
WITH person, row
CALL (person, row) {
  UNWIND row.accountIds AS id MATCH (n:FraudAccount {accountId: id}) MERGE (person)-[:CONTROLS]->(n) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.deviceIds AS id MATCH (n:FraudDevice {deviceId: id}) MERGE (person)-[:USES_DEVICE]->(n) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.addressIds AS id MATCH (n:FraudAddress {addressId: id}) MERGE (person)-[:LIVES_AT]->(n) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.phoneIds AS id MATCH (n:FraudPhone {phoneId: id}) MERGE (person)-[:USES_PHONE]->(n) RETURN count(*) AS linked
}
RETURN sum(linked) AS processed
""".strip()

UPSERT_TRANSACTIONS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudTransaction {transactionId: row.transactionId})
SET n.amount = row.amount, n.currency = row.currency,
    n.occurredAt = datetime({datetime: datetime(row.occurredAt), timezone: 'UTC'}),
    n.channel = row.channel, n.status = row.status
RETURN count(n) AS processed
""".strip()

LINK_TRANSACTIONS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MATCH (transaction:FraudTransaction {transactionId: row.transactionId})
MATCH (sender:FraudAccount {accountId: row.senderAccountId})
MERGE (sender)-[:INITIATED]->(transaction)
WITH transaction, row
CALL (transaction, row) {
  WITH transaction, row WHERE row.receiverAccountId IS NOT NULL
  MATCH (receiver:FraudAccount {accountId: row.receiverAccountId})
  MERGE (transaction)-[:CREDITED]->(receiver)
  RETURN count(*) AS linked
  UNION ALL
  WITH transaction, row WHERE row.merchantId IS NOT NULL
  MATCH (merchant:FraudMerchant {merchantId: row.merchantId})
  MERGE (transaction)-[:AT_MERCHANT]->(merchant)
  RETURN count(*) AS linked
  UNION ALL
  WITH transaction, row WHERE row.deviceId IS NOT NULL
  MATCH (device:FraudDevice {deviceId: row.deviceId})
  MERGE (transaction)-[:FROM_DEVICE]->(device)
  RETURN count(*) AS linked
}
RETURN sum(linked) AS processed
""".strip()

UPSERT_ALERTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudAlert {alertId: row.alertId})
SET n.title = row.title, n.severity = row.severity, n.status = row.status,
    n.createdAt = datetime({datetime: datetime(row.createdAt), timezone: 'UTC'}),
    n.reason = row.reason
RETURN count(n) AS processed
""".strip()

LINK_ALERTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MATCH (alert:FraudAlert {alertId: row.alertId})
CALL (alert) { MATCH (alert)-[r:FLAGS_ACCOUNT|FLAGS_TRANSACTION]->() DELETE r }
WITH alert, row
CALL (alert, row) {
  UNWIND row.accountIds AS id MATCH (n:FraudAccount {accountId: id}) MERGE (alert)-[:FLAGS_ACCOUNT]->(n) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.transactionIds AS id MATCH (n:FraudTransaction {transactionId: id}) MERGE (alert)-[:FLAGS_TRANSACTION]->(n) RETURN count(*) AS linked
}
RETURN sum(linked) AS processed
""".strip()

UPSERT_CASES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudCase {caseId: row.caseId})
SET n.title = row.title, n.status = row.status, n.priority = row.priority,
    n.openedAt = datetime({datetime: datetime(row.openedAt), timezone: 'UTC'}),
    n.assignee = row.assignee
WITH n, row
CALL (n) { MATCH (n)-[r:CONTAINS_ALERT]->() DELETE r }
WITH n, row UNWIND row.alertIds AS id
MATCH (alert:FraudAlert {alertId: id})
MERGE (n)-[:CONTAINS_ALERT]->(alert)
RETURN count(alert) AS processed
""".strip()

UPSERT_DOCUMENTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (n:FraudDocument {documentId: row.documentId})
SET n.documentType = row.documentType, n.title = row.title, n.updatedAt = datetime()
WITH n, row
CALL (n) { MATCH (n)-[r:REFERENCES_ACCOUNT|REFERENCES_DEVICE|REFERENCES_MERCHANT]->() DELETE r }
WITH n, row
CALL (n, row) {
  UNWIND row.relatedAccountIds AS id MATCH (x:FraudAccount {accountId: id}) MERGE (n)-[:REFERENCES_ACCOUNT]->(x) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.relatedDeviceIds AS id MATCH (x:FraudDevice {deviceId: id}) MERGE (n)-[:REFERENCES_DEVICE]->(x) RETURN count(*) AS linked
  UNION ALL
  UNWIND row.relatedMerchantIds AS id MATCH (x:FraudMerchant {merchantId: id}) MERGE (n)-[:REFERENCES_MERCHANT]->(x) RETURN count(*) AS linked
}
RETURN sum(linked) AS processed
""".strip()

UPSERT_CHUNKS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (chunk:FraudChunk {chunkId: row.chunkId})
SET chunk.documentId = row.documentId, chunk.documentType = row.documentType,
    chunk.title = row.title, chunk.section = row.section, chunk.sequence = row.sequence,
    chunk.text = row.text, chunk.contentHash = row.contentHash
FOREACH (_ IN CASE WHEN row.embedding IS NULL THEN [] ELSE [1] END |
  SET chunk.embedding = row.embedding, chunk.embeddingModel = $embeddingModel)
WITH chunk, row
MATCH (document:FraudDocument {documentId: row.documentId})
MERGE (document)-[:HAS_FRAUD_CHUNK]->(chunk)
RETURN count(chunk) AS processed
""".strip()


class FraudGraphStore:
    """Own one driver and isolate every Project 4 operation under Fraud* labels."""

    def __init__(self, config: Neo4jConfig):
        self.database = config.database
        self.driver = GraphDatabase.driver(config.uri, auth=(config.username, config.password))

    def __enter__(self) -> "FraudGraphStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def create_schema(self) -> None:
        for query in SCHEMA_QUERIES:
            self.driver.execute_query(query, database_=self.database)

    def index_states(self) -> dict[str, str]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 SHOW INDEXES YIELD name, state WHERE name IN $names RETURN name, state LIMIT 10",
            names=[VECTOR_INDEX_NAME, FULLTEXT_INDEX_NAME], database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {record["name"]: record["state"] for record in records}

    def wait_for_search_indexes(self, timeout_seconds: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            states = self.index_states()
            if states.get(VECTOR_INDEX_NAME) == "ONLINE" and states.get(FULLTEXT_INDEX_NAME) == "ONLINE":
                return
            time.sleep(0.5)
        raise TimeoutError("Fraud search indexes did not become ONLINE")

    def is_ready(self) -> bool:
        states = self.index_states()
        return states.get(VECTOR_INDEX_NAME) == "ONLINE" and states.get(FULLTEXT_INDEX_NAME) == "ONLINE" and self.stats()["chunkCount"] > 0

    def existing_chunk_state(self) -> dict[str, dict[str, Any]]:
        if self.stats()["chunkCount"] == 0:
            return {}
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (n:FraudChunk) RETURN n.chunkId AS chunkId, n.contentHash AS contentHash, n.embedding IS NOT NULL AS hasEmbedding LIMIT 10000",
            database_=self.database, routing_=RoutingControl.READ,
        )
        return {record["chunkId"]: {"contentHash": record["contentHash"], "hasEmbedding": bool(record["hasEmbedding"])} for record in records}

    def ingest(
        self, payload: Mapping[str, Any], documents: Sequence[Mapping[str, Any]],
        chunks: Sequence[Mapping[str, Any]], embedding_model: str,
    ) -> None:
        batches = (
            (UPSERT_PERSONS_QUERY, payload["persons"]),
            (UPSERT_ACCOUNTS_QUERY, payload["accounts"]),
            (UPSERT_DEVICES_QUERY, payload["devices"]),
            (UPSERT_ADDRESSES_QUERY, payload["addresses"]),
            (UPSERT_PHONES_QUERY, payload["phones"]),
            (UPSERT_MERCHANTS_QUERY, payload["merchants"]),
            (LINK_IDENTITIES_QUERY, payload["persons"]),
            (UPSERT_TRANSACTIONS_QUERY, payload["transactions"]),
            (LINK_TRANSACTIONS_QUERY, payload["transactions"]),
            (UPSERT_ALERTS_QUERY, payload["alerts"]),
            (LINK_ALERTS_QUERY, payload["alerts"]),
            (UPSERT_CASES_QUERY, payload["cases"]),
            (UPSERT_DOCUMENTS_QUERY, documents),
        )
        for query, rows in batches:
            self.driver.execute_query(query, rows=[dict(row) for row in rows], database_=self.database)
        self.driver.execute_query(
            UPSERT_CHUNKS_QUERY, rows=[dict(row) for row in chunks],
            embeddingModel=embedding_model, database_=self.database,
        )

    def stats(self) -> dict[str, int]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 "
            "CALL () { MATCH (n:FraudPerson) RETURN count(n) AS personCount } "
            "CALL () { MATCH (n:FraudAccount) RETURN count(n) AS accountCount } "
            "CALL () { MATCH (n:FraudTransaction) RETURN count(n) AS transactionCount } "
            "CALL () { MATCH (n:FraudAlert) RETURN count(n) AS alertCount } "
            "CALL () { MATCH (n:FraudCase) RETURN count(n) AS caseCount } "
            "CALL () { MATCH (n:FraudChunk) RETURN count(n) AS chunkCount } "
            "RETURN personCount, accountCount, transactionCount, alertCount, caseCount, chunkCount LIMIT 1",
            database_=self.database, routing_=RoutingControl.READ,
        )
        empty = {"personCount": 0, "accountCount": 0, "transactionCount": 0, "alertCount": 0, "caseCount": 0, "chunkCount": 0}
        return {key: int(records[0][key]) for key in empty} if records else empty

    def alerts(self, status: str | None = None) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (alert:FraudAlert) WHERE $status IS NULL OR alert.status = $status "
            "OPTIONAL MATCH (case:FraudCase)-[:CONTAINS_ALERT]->(alert) "
            "RETURN alert.alertId AS alertId, alert.title AS title, alert.severity AS severity, "
            "alert.status AS status, toString(alert.createdAt) AS createdAt, alert.reason AS reason, "
            "case.caseId AS caseId, COLLECT { MATCH (alert)-[:FLAGS_ACCOUNT]->(a:FraudAccount) RETURN a.accountId ORDER BY a.accountId } AS accountIds "
            "ORDER BY alert.createdAt DESC LIMIT 50",
            status=status, database_=self.database, routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def cases(self) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (c:FraudCase) RETURN c.caseId AS caseId, c.title AS title, c.status AS status, "
            "c.priority AS priority, toString(c.openedAt) AS openedAt, c.assignee AS assignee, "
            "COLLECT { MATCH (c)-[:CONTAINS_ALERT]->(a:FraudAlert) RETURN a.alertId ORDER BY a.alertId } AS alertIds "
            "ORDER BY c.openedAt DESC LIMIT 25",
            database_=self.database, routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def alert_context(self, alert_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (alert:FraudAlert {alertId: $alertId})
OPTIONAL MATCH (case:FraudCase)-[:CONTAINS_ALERT]->(alert)
RETURN alert.alertId AS alertId, alert.title AS title, alert.severity AS severity,
       alert.status AS status, alert.reason AS reason, toString(alert.createdAt) AS createdAt,
       case.caseId AS caseId,
       COLLECT { MATCH (alert)-[:FLAGS_ACCOUNT]->(a:FraudAccount)<-[:CONTROLS]-(p:FraudPerson)
         RETURN {accountId: a.accountId, product: a.product, accountStatus: a.status,
                 openedAt: toString(a.openedAt), balance: a.balance,
                 personId: p.personId, personName: p.name, riskTier: p.riskTier}
         ORDER BY a.accountId } AS accounts,
       COLLECT { MATCH (alert)-[:FLAGS_TRANSACTION]->(t:FraudTransaction)<-[:INITIATED]-(sender:FraudAccount)
         OPTIONAL MATCH (t)-[:CREDITED]->(receiver:FraudAccount)
         OPTIONAL MATCH (t)-[:AT_MERCHANT]->(merchant:FraudMerchant)
         OPTIONAL MATCH (t)-[:FROM_DEVICE]->(device:FraudDevice)
         RETURN {transactionId: t.transactionId, amount: t.amount, currency: t.currency,
                 occurredAt: toString(t.occurredAt), channel: t.channel,
                 senderAccountId: sender.accountId, receiverAccountId: receiver.accountId,
                 merchantId: merchant.merchantId, merchantName: merchant.name, deviceId: device.deviceId}
         ORDER BY t.occurredAt } AS transactions
LIMIT 1
""".strip(),
            alertId=alert_id, database_=self.database, routing_=RoutingControl.READ,
        )
        return records[0].data() if records else None

    def shared_identifiers(self, account_ids: Sequence[str]) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
UNWIND $accountIds AS accountId
MATCH (account:FraudAccount {accountId: accountId})<-[:CONTROLS]-(person:FraudPerson)
MATCH (person)-[:USES_DEVICE|USES_PHONE|LIVES_AT]->(identifier)
WITH identifier, labels(identifier)[0] AS label,
     collect(DISTINCT account.accountId) AS accountIds,
     collect(DISTINCT {personId: person.personId, name: person.name}) AS persons
WHERE size(accountIds) > 1
RETURN coalesce(identifier.deviceId, identifier.phoneId, identifier.addressId) AS identifierId,
       CASE label WHEN 'FraudDevice' THEN 'device' WHEN 'FraudPhone' THEN 'phone' ELSE 'address' END AS identifierType,
       coalesce(identifier.masked, identifier.fingerprint) AS display, accountIds, persons
ORDER BY identifierType, identifierId LIMIT 25
""".strip(),
            accountIds=list(dict.fromkeys(account_ids))[:12], database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def fund_flows(self, account_ids: Sequence[str], window_hours: int) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (selected:FraudAccount)-[:INITIATED|CREDITED]-(anchor:FraudTransaction)
WHERE selected.accountId IN $accountIds
WITH max(anchor.occurredAt) AS latest
MATCH (sender:FraudAccount)-[:INITIATED]->(t:FraudTransaction)
WHERE t.occurredAt >= latest - duration({hours: $windowHours})
  AND (sender.accountId IN $accountIds
       OR EXISTS {
         MATCH (t)-[:CREDITED]->(candidate:FraudAccount)
         WHERE candidate.accountId IN $accountIds
       })
OPTIONAL MATCH (t)-[:CREDITED]->(receiver:FraudAccount)
OPTIONAL MATCH (t)-[:AT_MERCHANT]->(merchant:FraudMerchant)
OPTIONAL MATCH (t)-[:FROM_DEVICE]->(device:FraudDevice)
RETURN t.transactionId AS transactionId, sender.accountId AS senderAccountId,
       receiver.accountId AS receiverAccountId, merchant.merchantId AS merchantId,
       merchant.name AS merchantName, device.deviceId AS deviceId,
       t.amount AS amount, t.currency AS currency, toString(t.occurredAt) AS occurredAt,
       t.channel AS channel
ORDER BY t.occurredAt LIMIT 100
""".strip(),
            accountIds=list(dict.fromkeys(account_ids))[:12],
            windowHours=max(1, min(int(window_hours), 720)),
            database_=self.database, routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def transaction_cycles(self, account_ids: Sequence[str], max_minutes: int) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (a:FraudAccount)-[:INITIATED]->(t1:FraudTransaction)-[:CREDITED]->(b:FraudAccount),
      (b)-[:INITIATED]->(t2:FraudTransaction)-[:CREDITED]->(c:FraudAccount),
      (c)-[:INITIATED]->(t3:FraudTransaction)-[:CREDITED]->(a)
WHERE a.accountId IN $accountIds AND b.accountId IN $accountIds AND c.accountId IN $accountIds
  AND a.accountId < b.accountId AND a.accountId < c.accountId
  AND t1.occurredAt < t2.occurredAt AND t2.occurredAt < t3.occurredAt
  AND duration.between(t1.occurredAt, t3.occurredAt).minutes <= $maxMinutes
RETURN [a.accountId, b.accountId, c.accountId, a.accountId] AS accountPath,
       [t1.transactionId, t2.transactionId, t3.transactionId] AS transactionIds,
       [t1.amount, t2.amount, t3.amount] AS amounts,
       toString(t1.occurredAt) AS startedAt, toString(t3.occurredAt) AS endedAt,
       duration.between(t1.occurredAt, t3.occurredAt).minutes AS elapsedMinutes
ORDER BY startedAt LIMIT 12
""".strip(),
            accountIds=list(dict.fromkeys(account_ids))[:12],
            maxMinutes=max(5, min(int(max_minutes), 1440)),
            database_=self.database, routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def merchant_concentration(self, account_ids: Sequence[str], window_hours: int) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (account:FraudAccount)-[:INITIATED]->(anchor:FraudTransaction)
WHERE account.accountId IN $accountIds
WITH max(anchor.occurredAt) AS latest
MATCH (account:FraudAccount)-[:INITIATED]->(t:FraudTransaction)
WHERE account.accountId IN $accountIds AND t.occurredAt >= latest - duration({hours: $windowHours})
WITH latest, sum(t.amount) AS totalOutgoing
MATCH (account:FraudAccount)-[:INITIATED]->(t:FraudTransaction)-[:AT_MERCHANT]->(merchant:FraudMerchant)
WHERE account.accountId IN $accountIds AND t.occurredAt >= latest - duration({hours: $windowHours})
RETURN merchant.merchantId AS merchantId, merchant.name AS merchantName,
       merchant.category AS category, merchant.riskLevel AS riskLevel,
       sum(t.amount) AS merchantAmount, totalOutgoing,
       round(100.0 * sum(t.amount) / totalOutgoing, 1) AS percentage,
       collect(t.transactionId) AS transactionIds
ORDER BY merchantAmount DESC LIMIT 12
""".strip(),
            accountIds=list(dict.fromkeys(account_ids))[:12],
            windowHours=max(1, min(int(window_hours), 720)),
            database_=self.database, routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def alert_network(self, alert_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = self.alert_context(alert_id)
        if rows is None:
            return {"nodes": [], "edges": []}
        ids = [item["accountId"] for item in rows["accounts"]]
        identifiers = self.shared_identifiers(ids)
        flows = self.fund_flows(ids, 72)
        nodes: dict[str, dict[str, Any]] = {
            alert_id: {"id": alert_id, "label": alert_id, "type": "alert", "severity": rows["severity"]}
        }
        edges: list[dict[str, Any]] = []
        for account in rows["accounts"]:
            nodes[account["accountId"]] = {"id": account["accountId"], "label": account["accountId"], "type": "account", "status": account["accountStatus"]}
            nodes[account["personId"]] = {"id": account["personId"], "label": account["personName"], "type": "person"}
            edges.extend([
                {"source": alert_id, "target": account["accountId"], "relationship": "FLAGS"},
                {"source": account["personId"], "target": account["accountId"], "relationship": "CONTROLS"},
            ])
        for item in identifiers:
            nodes[item["identifierId"]] = {"id": item["identifierId"], "label": item["identifierId"], "type": item["identifierType"], "display": item["display"]}
            for person in item["persons"]:
                edges.append({"source": person["personId"], "target": item["identifierId"], "relationship": "SHARES"})
        for flow in flows:
            nodes.setdefault(flow["senderAccountId"], {"id": flow["senderAccountId"], "label": flow["senderAccountId"], "type": "account"})
            target = flow.get("receiverAccountId") or flow.get("merchantId")
            if target:
                nodes.setdefault(target, {"id": target, "label": flow.get("merchantName") or target, "type": "merchant" if flow.get("merchantId") else "account"})
                edges.append({"source": flow["senderAccountId"], "target": target, "relationship": "TRANSFERRED" if flow.get("receiverAccountId") else "PAID", "amount": flow["amount"], "transactionId": flow["transactionId"]})
        return {"nodes": list(nodes.values()), "edges": edges}

    def transaction_timeline(self, alert_id: str) -> list[dict[str, Any]]:
        context = self.alert_context(alert_id)
        if context is None:
            return []
        ids = [item["accountId"] for item in context["accounts"]]
        return [
            {"eventId": row["transactionId"], "type": "transaction", "occurredAt": row["occurredAt"],
             "label": f"{row['senderAccountId']} → {row.get('receiverAccountId') or row.get('merchantName')}",
             "detail": f"{row['currency']} {row['amount']:,.2f}"}
            for row in self.fund_flows(ids, 72)
        ]

    def history(self, session_id: str, limit: int = 6) -> tuple[dict[str, str], ...]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (:FraudInvestigation {sessionId: $sessionId})-[:HAS_TURN]->(t:FraudTurn) "
            "RETURN t.question AS question, t.summary AS summary, t.riskAssessment AS risk_assessment, t.confidence AS confidence "
            "ORDER BY t.createdAt DESC LIMIT $limit",
            sessionId=session_id, limit=max(1, min(int(limit), 12)),
            database_=self.database, routing_=RoutingControl.READ,
        )
        return tuple(reversed([record.data() for record in records]))

    def remember(self, session_id: str, turn_id: str, question: str, summary: str, risk_assessment: str, confidence: str) -> None:
        self.driver.execute_query(
            "CYPHER 25 MERGE (i:FraudInvestigation {sessionId: $sessionId}) ON CREATE SET i.createdAt = datetime() "
            "SET i.updatedAt = datetime() MERGE (t:FraudTurn {turnId: $turnId}) "
            "SET t.question = $question, t.summary = $summary, t.riskAssessment = $riskAssessment, "
            "t.confidence = $confidence, t.createdAt = datetime() MERGE (i)-[:HAS_TURN]->(t)",
            sessionId=session_id, turnId=turn_id, question=question, summary=summary,
            riskAssessment=risk_assessment, confidence=confidence, database_=self.database,
        )

    def clear_history(self, session_id: str) -> bool:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 OPTIONAL MATCH (i:FraudInvestigation {sessionId: $sessionId}) "
            "OPTIONAL MATCH (i)-[:HAS_TURN]->(t:FraudTurn) WITH i, collect(t) AS turns, count(t) AS removed "
            "FOREACH (turn IN turns | DETACH DELETE turn) FOREACH (_ IN CASE WHEN i IS NULL THEN [] ELSE [1] END | DETACH DELETE i) "
            "RETURN removed > 0 OR i IS NOT NULL AS cleared",
            sessionId=session_id, database_=self.database,
        )
        return bool(records and records[0]["cleared"])
