"""Neo4j schema, ingestion, topology, and temporal investigation queries."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from neo4j import GraphDatabase, RoutingControl

from config import (
    EMBEDDING_DIMENSIONS,
    FULLTEXT_INDEX_NAME,
    VECTOR_INDEX_NAME,
    Neo4jConfig,
)


SCHEMA_QUERIES = (
    "CYPHER 25 CREATE CONSTRAINT ops_team_id_unique IF NOT EXISTS "
    "FOR (team:OpsTeam) REQUIRE team.teamId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_service_id_unique IF NOT EXISTS "
    "FOR (service:OpsService) REQUIRE service.serviceId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_commit_sha_unique IF NOT EXISTS "
    "FOR (commit:OpsCommit) REQUIRE commit.sha IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_deployment_id_unique IF NOT EXISTS "
    "FOR (deployment:OpsDeployment) REQUIRE deployment.deploymentId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_incident_id_unique IF NOT EXISTS "
    "FOR (incident:OpsIncident) REQUIRE incident.incidentId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_alert_id_unique IF NOT EXISTS "
    "FOR (alert:OpsAlert) REQUIRE alert.alertId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_runbook_id_unique IF NOT EXISTS "
    "FOR (runbook:OpsRunbook) REQUIRE runbook.runbookId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_postmortem_id_unique IF NOT EXISTS "
    "FOR (postmortem:OpsPostmortem) REQUIRE postmortem.postmortemId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT ops_chunk_id_unique IF NOT EXISTS "
    "FOR (chunk:OpsChunk) REQUIRE chunk.chunkId IS UNIQUE",
    "CYPHER 25 CREATE INDEX ops_deployment_time_idx IF NOT EXISTS "
    "FOR (deployment:OpsDeployment) ON (deployment.deployedAt)",
    "CYPHER 25 CREATE INDEX ops_incident_time_idx IF NOT EXISTS "
    "FOR (incident:OpsIncident) ON (incident.startedAt)",
    "CYPHER 25 CREATE INDEX ops_alert_time_idx IF NOT EXISTS "
    "FOR (alert:OpsAlert) ON (alert.firedAt)",
    "CYPHER 25 CREATE TEXT INDEX ops_service_name_idx IF NOT EXISTS "
    "FOR (service:OpsService) ON (service.name)",
    f"CYPHER 25 CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
    "FOR (chunk:OpsChunk) ON (chunk.embedding) "
    "OPTIONS {indexConfig: {"
    f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}, "
    "`vector.similarity_function`: 'cosine'}}",
    f"CYPHER 25 CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS "
    "FOR (chunk:OpsChunk) ON EACH [chunk.text, chunk.title, chunk.section]",
)


UPSERT_TEAMS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (team:OpsTeam {teamId: row.teamId})
SET team.name = row.name,
    team.channel = row.channel
RETURN count(team) AS processed
""".strip()


UPSERT_SERVICES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (service:OpsService {serviceId: row.serviceId})
SET service.name = row.name,
    service.tier = row.tier,
    service.layer = row.layer,
    service.description = row.description
WITH service, row
MATCH (team:OpsTeam {teamId: row.teamId})
MERGE (service)-[:OWNED_BY]->(team)
RETURN count(service) AS processed
""".strip()


UPSERT_DEPENDENCIES_QUERY = """
CYPHER 25
UNWIND $rows AS row
MATCH (source:OpsService {serviceId: row.serviceId})
CALL (source) {
  MATCH (source)-[stale:DEPENDS_ON]->(:OpsService)
  DELETE stale
}
WITH source, row
UNWIND row.dependsOn AS dependency
MATCH (target:OpsService {serviceId: dependency.serviceId})
MERGE (source)-[relationship:DEPENDS_ON]->(target)
SET relationship.criticality = dependency.criticality
RETURN count(relationship) AS processed
""".strip()


UPSERT_COMMITS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (commit:OpsCommit {sha: row.sha})
SET commit.summary = row.summary,
    commit.author = row.author
RETURN count(commit) AS processed
""".strip()


UPSERT_DEPLOYMENTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (deployment:OpsDeployment {deploymentId: row.deploymentId})
SET deployment.version = row.version,
    deployment.environment = row.environment,
    deployment.status = row.status,
    deployment.deployedAt = datetime({
      datetime: datetime(row.deployedAt), timezone: 'UTC'
    })
WITH deployment, row
MATCH (service:OpsService {serviceId: row.serviceId})
MATCH (commit:OpsCommit {sha: row.sha})
MERGE (deployment)-[:DEPLOYED_TO]->(service)
MERGE (deployment)-[:BUILT_FROM]->(commit)
RETURN count(deployment) AS processed
""".strip()


UPSERT_INCIDENTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (incident:OpsIncident {incidentId: row.incidentId})
SET incident.title = row.title,
    incident.severity = row.severity,
    incident.status = row.status,
    incident.summary = row.summary,
    incident.startedAt = datetime({
      datetime: datetime(row.startedAt), timezone: 'UTC'
    }),
    incident.endedAt = CASE
      WHEN row.endedAt IS NULL THEN null
      ELSE datetime({datetime: datetime(row.endedAt), timezone: 'UTC'})
    END
CALL (incident) {
  MATCH (incident)-[stale:IMPACTED]->(:OpsService)
  DELETE stale
}
CALL (incident) {
  MATCH (incident)-[stale:PRECEDED_BY]->(:OpsDeployment)
  DELETE stale
}
WITH incident, row
FOREACH (serviceId IN row.impactedServices |
  MERGE (service:OpsService {serviceId: serviceId})
  MERGE (incident)-[:IMPACTED]->(service)
)
FOREACH (deploymentId IN row.precededBy |
  MERGE (deployment:OpsDeployment {deploymentId: deploymentId})
  MERGE (incident)-[:PRECEDED_BY]->(deployment)
)
RETURN count(incident) AS processed
""".strip()


UPSERT_ALERTS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (alert:OpsAlert {alertId: row.alertId})
SET alert.name = row.name,
    alert.metric = row.metric,
    alert.value = row.value,
    alert.unit = row.unit,
    alert.firedAt = datetime({
      datetime: datetime(row.firedAt), timezone: 'UTC'
    }),
    alert.clearedAt = CASE
      WHEN row.clearedAt IS NULL THEN null
      ELSE datetime({datetime: datetime(row.clearedAt), timezone: 'UTC'})
    END
WITH alert, row
MATCH (service:OpsService {serviceId: row.serviceId})
MATCH (incident:OpsIncident {incidentId: row.incidentId})
MERGE (alert)-[:TRIGGERED_FOR]->(service)
MERGE (alert)-[:SIGNALS]->(incident)
RETURN count(alert) AS processed
""".strip()


UPSERT_RUNBOOKS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (runbook:OpsRunbook {runbookId: row.runbookId})
SET runbook.title = row.title,
    runbook.updatedAt = datetime()
CALL (runbook) {
  MATCH (runbook)-[stale:APPLIES_TO]->(:OpsService)
  DELETE stale
}
WITH runbook, row
FOREACH (serviceId IN row.serviceIds |
  MERGE (service:OpsService {serviceId: serviceId})
  MERGE (runbook)-[:APPLIES_TO]->(service)
)
RETURN count(runbook) AS processed
""".strip()


UPSERT_POSTMORTEMS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (postmortem:OpsPostmortem {postmortemId: row.postmortemId})
SET postmortem.title = row.title,
    postmortem.updatedAt = datetime()
WITH postmortem, row
MATCH (incident:OpsIncident {incidentId: row.incidentId})
MERGE (postmortem)-[:DOCUMENTS]->(incident)
RETURN count(postmortem) AS processed
""".strip()


UPSERT_CHUNKS_QUERY = """
CYPHER 25
UNWIND $rows AS row
MERGE (chunk:OpsChunk {chunkId: row.chunkId})
SET chunk.sourceId = row.sourceId,
    chunk.sourceType = row.sourceType,
    chunk.title = row.title,
    chunk.section = row.section,
    chunk.sequence = row.sequence,
    chunk.text = row.text,
    chunk.contentHash = row.contentHash
FOREACH (_ IN CASE WHEN row.embedding IS NULL THEN [] ELSE [1] END |
  SET chunk.embedding = row.embedding,
      chunk.embeddingModel = $embeddingModel
)
WITH chunk, row
CALL (chunk, row) {
  WITH chunk, row WHERE row.sourceType = 'runbook'
  MATCH (document:OpsRunbook {runbookId: row.sourceId})
  MERGE (document)-[:HAS_OPS_CHUNK]->(chunk)
  RETURN count(*) AS linked
  UNION ALL
  WITH chunk, row WHERE row.sourceType = 'postmortem'
  MATCH (document:OpsPostmortem {postmortemId: row.sourceId})
  MERGE (document)-[:HAS_OPS_CHUNK]->(chunk)
  RETURN count(*) AS linked
}
RETURN count(chunk) AS processed
""".strip()


class OperationsGraphStore:
    """Own one driver and isolate every Project 3 Neo4j operation."""

    def __init__(self, config: Neo4jConfig):
        self.database = config.database
        self.driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )

    def __enter__(self) -> "OperationsGraphStore":
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
            "CYPHER 25 SHOW INDEXES YIELD name, state "
            "WHERE name IN $names RETURN name, state LIMIT 10",
            names=[VECTOR_INDEX_NAME, FULLTEXT_INDEX_NAME],
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {record["name"]: record["state"] for record in records}

    def wait_for_search_indexes(self, timeout_seconds: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            states = self.index_states()
            if states.get(VECTOR_INDEX_NAME) == "ONLINE" and states.get(
                FULLTEXT_INDEX_NAME
            ) == "ONLINE":
                return
            time.sleep(0.5)
        raise TimeoutError("Operations search indexes did not become ONLINE")

    def is_ready(self) -> bool:
        states = self.index_states()
        return (
            states.get(VECTOR_INDEX_NAME) == "ONLINE"
            and states.get(FULLTEXT_INDEX_NAME) == "ONLINE"
            and self.stats()["chunkCount"] > 0
        )

    def existing_chunk_state(self) -> dict[str, dict[str, Any]]:
        if self.stats()["chunkCount"] == 0:
            return {}
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (chunk:OpsChunk) "
            "RETURN chunk.chunkId AS chunkId, chunk.contentHash AS contentHash, "
            "chunk.embedding IS NOT NULL AS hasEmbedding LIMIT 10000",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {
            record["chunkId"]: {
                "contentHash": record["contentHash"],
                "hasEmbedding": bool(record["hasEmbedding"]),
            }
            for record in records
        }

    def ingest(
        self,
        payload: Mapping[str, Any],
        runbooks: Sequence[Mapping[str, Any]],
        postmortems: Sequence[Mapping[str, Any]],
        chunks: Sequence[Mapping[str, Any]],
        embedding_model: str,
    ) -> None:
        batches = (
            (UPSERT_TEAMS_QUERY, payload["teams"]),
            (UPSERT_SERVICES_QUERY, payload["services"]),
            (UPSERT_DEPENDENCIES_QUERY, payload["services"]),
            (UPSERT_COMMITS_QUERY, payload["commits"]),
            (UPSERT_DEPLOYMENTS_QUERY, payload["deployments"]),
            (UPSERT_INCIDENTS_QUERY, payload["incidents"]),
            (UPSERT_ALERTS_QUERY, payload["alerts"]),
            (UPSERT_RUNBOOKS_QUERY, runbooks),
            (UPSERT_POSTMORTEMS_QUERY, postmortems),
        )
        for query, rows in batches:
            self.driver.execute_query(
                query,
                rows=[dict(row) for row in rows],
                database_=self.database,
            )
        self.driver.execute_query(
            UPSERT_CHUNKS_QUERY,
            rows=[dict(row) for row in chunks],
            embeddingModel=embedding_model,
            database_=self.database,
        )

    def stats(self) -> dict[str, int]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 "
            "CALL () { MATCH (service:OpsService) RETURN count(service) AS serviceCount } "
            "CALL () { MATCH (incident:OpsIncident) RETURN count(incident) AS incidentCount } "
            "CALL () { MATCH (deployment:OpsDeployment) RETURN count(deployment) AS deploymentCount } "
            "CALL () { MATCH (alert:OpsAlert) RETURN count(alert) AS alertCount } "
            "CALL () { MATCH (chunk:OpsChunk) RETURN count(chunk) AS chunkCount } "
            "RETURN serviceCount, incidentCount, deploymentCount, alertCount, "
            "chunkCount LIMIT 1",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        empty = {
            "serviceCount": 0,
            "incidentCount": 0,
            "deploymentCount": 0,
            "alertCount": 0,
            "chunkCount": 0,
        }
        if not records:
            return empty
        return {key: int(records[0][key]) for key in empty}

    def incidents(self, status: str | None = None) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (incident:OpsIncident) "
            "WHERE $status IS NULL OR incident.status = $status "
            "RETURN incident.incidentId AS incidentId, incident.title AS title, "
            "incident.severity AS severity, incident.status AS status, "
            "toString(incident.startedAt) AS startedAt, incident.summary AS summary, "
            "COLLECT { MATCH (incident)-[:IMPACTED]->(service:OpsService) "
            "RETURN service.serviceId ORDER BY service.serviceId } AS serviceIds "
            "ORDER BY incident.startedAt DESC LIMIT 25",
            status=status,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def services(self) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (service:OpsService)-[:OWNED_BY]->(team:OpsTeam) "
            "RETURN service.serviceId AS serviceId, service.name AS name, "
            "service.tier AS tier, service.layer AS layer, team.name AS team "
            "ORDER BY service.layer, service.name LIMIT 100",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def topology(self, incident_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
        nodes, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (service:OpsService)-[:OWNED_BY]->(team:OpsTeam) "
            "RETURN service.serviceId AS id, service.name AS label, 'service' AS type, "
            "service.tier AS tier, service.layer AS layer, team.name AS team, "
            "EXISTS { MATCH (:OpsIncident {incidentId: $incidentId})-[:IMPACTED]->(service) } "
            "AS impacted ORDER BY service.layer, service.name LIMIT 100",
            incidentId=incident_id,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        edges, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (source:OpsService)-[relationship:DEPENDS_ON]->"
            "(target:OpsService) RETURN source.serviceId AS source, "
            "target.serviceId AS target, 'DEPENDS_ON' AS relationship, "
            "relationship.criticality AS criticality ORDER BY source, target LIMIT 200",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {
            "nodes": [record.data() for record in nodes],
            "edges": [record.data() for record in edges],
        }

    def timeline(self, incident_id: str) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (incident:OpsIncident {incidentId: $incidentId})
CALL (incident) {
  RETURN 'incident' AS type, incident.incidentId AS eventId,
         incident.startedAt AS occurredAt, incident.title AS label,
         null AS serviceId, incident.severity AS detail
  UNION ALL
  MATCH (alert:OpsAlert)-[:SIGNALS]->(incident)
  MATCH (alert)-[:TRIGGERED_FOR]->(service:OpsService)
  RETURN 'alert' AS type, alert.alertId AS eventId,
         alert.firedAt AS occurredAt, alert.name AS label,
         service.serviceId AS serviceId,
         toString(alert.value) + ' ' + alert.unit AS detail
  UNION ALL
  MATCH (incident)-[:PRECEDED_BY]->(deployment:OpsDeployment)
  MATCH (deployment)-[:DEPLOYED_TO]->(service:OpsService)
  RETURN 'deployment' AS type, deployment.deploymentId AS eventId,
         deployment.deployedAt AS occurredAt,
         'Deploy ' + deployment.version AS label,
         service.serviceId AS serviceId, deployment.status AS detail
}
RETURN type, eventId, toString(occurredAt) AS occurredAt, label, serviceId, detail
ORDER BY occurredAt LIMIT 100
""".strip(),
            incidentId=incident_id,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def incident_context(self, incident_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (incident:OpsIncident {incidentId: $incidentId})
RETURN incident.incidentId AS incidentId, incident.title AS title,
       incident.severity AS severity, incident.status AS status,
       incident.summary AS summary, toString(incident.startedAt) AS startedAt,
       CASE WHEN incident.endedAt IS NULL THEN null ELSE toString(incident.endedAt) END AS endedAt,
       COLLECT {
         MATCH (incident)-[:IMPACTED]->(service:OpsService)
         RETURN {serviceId: service.serviceId, name: service.name, tier: service.tier}
         ORDER BY service.tier, service.name
       } AS impactedServices,
       COLLECT {
         MATCH (alert:OpsAlert)-[:SIGNALS]->(incident)
         MATCH (alert)-[:TRIGGERED_FOR]->(service:OpsService)
         RETURN {alertId: alert.alertId, name: alert.name, metric: alert.metric,
                 value: alert.value, unit: alert.unit,
                 firedAt: toString(alert.firedAt), serviceId: service.serviceId}
         ORDER BY alert.firedAt
       } AS alerts
LIMIT 1
""".strip(),
            incidentId=incident_id,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return records[0].data() if records else None

    def recent_changes(
        self, incident_id: str, lookback_minutes: int
    ) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH (incident:OpsIncident {incidentId: $incidentId})-[:IMPACTED]->(impacted:OpsService)
WITH incident, collect(DISTINCT impacted) AS impactedServices
MATCH (deployment:OpsDeployment)-[:DEPLOYED_TO]->(service:OpsService)
MATCH (deployment)-[:BUILT_FROM]->(commit:OpsCommit)
WHERE deployment.deployedAt <= incident.startedAt
  AND deployment.deployedAt >= incident.startedAt - duration({minutes: $lookbackMinutes})
  AND any(impacted IN impactedServices WHERE
    service = impacted
    OR EXISTS { (impacted)-[:DEPENDS_ON]->(service) }
    OR EXISTS { (service)-[:DEPENDS_ON]->(impacted) }
  )
RETURN DISTINCT deployment.deploymentId AS deploymentId,
       deployment.version AS version, deployment.status AS status,
       toString(deployment.deployedAt) AS deployedAt,
       service.serviceId AS serviceId, service.name AS serviceName,
       commit.sha AS sha, commit.summary AS commitSummary,
       duration.between(deployment.deployedAt, incident.startedAt).minutes AS minutesBefore
ORDER BY deployedAt DESC LIMIT 25
""".strip(),
            incidentId=incident_id,
            lookbackMinutes=max(15, min(int(lookback_minutes), 1440)),
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def blast_radius(self, service_id: str, max_hops: int) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
MATCH path = (origin:OpsService {serviceId: $serviceId})
             (()<-[:DEPENDS_ON]-()){1,3}(dependent:OpsService)
WHERE length(path) <= $maxHops
RETURN dependent.serviceId AS serviceId, dependent.name AS name,
       dependent.tier AS tier, min(length(path)) AS hops,
       [node IN nodes(path) | node.serviceId] AS path
ORDER BY hops, tier, name LIMIT 25
""".strip(),
            serviceId=service_id,
            maxHops=max(1, min(int(max_hops), 3)),
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]

    def runbook_sections(self, service_ids: Sequence[str]) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
CYPHER 25
UNWIND $serviceIds AS serviceId
MATCH (runbook:OpsRunbook)-[:APPLIES_TO]->(service:OpsService {serviceId: serviceId})
MATCH (runbook)-[:HAS_OPS_CHUNK]->(chunk:OpsChunk)
RETURN DISTINCT runbook.runbookId AS runbookId, runbook.title AS title,
       chunk.chunkId AS chunkId, chunk.section AS section,
       chunk.sequence AS sequence, chunk.text AS text,
       COLLECT {
         MATCH (runbook)-[:APPLIES_TO]->(appliesTo:OpsService)
         RETURN appliesTo.serviceId ORDER BY appliesTo.serviceId
       } AS serviceIds
ORDER BY title, sequence LIMIT 25
""".strip(),
            serviceIds=list(dict.fromkeys(service_ids))[:8],
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]
