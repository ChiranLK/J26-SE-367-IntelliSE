"""Living, versioned Requirement -> UML -> Rule -> Code -> API -> DB -> Test-seam traceability.

The hybrid graph uses the typed vocabulary in ``KB-TRACE-SCHEMA`` (RULE and
KNOWLEDGE_ITEM nodes, upstream -> downstream relations). Versions are appended
to their own table inside the existing traceability SQLite store (never
updated or deleted). Regeneration preserves unchanged links, marks replaced
links SUPERSEDED and vanished links EXPIRED, and keeps every earlier version.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.generation.evidence import canonical_sha256

TRACE_SCHEMA_VERSION = "C3_LIVING_TRACE_V1"
NODE_TYPES = frozenset({
    "REQUIREMENT", "UML_ELEMENT", "RULE", "KNOWLEDGE_ITEM", "MODULE", "CODE_FILE", "CODE_SYMBOL",
    "API_OPERATION", "DATABASE_ENTITY", "TEST_SEAM", "C4_TEST", "DEFECT_REPORT", "PATCH_EVENT",
    "READINESS_SIGNAL", "DEPLOYMENT_EVENT", "ARTIFACT",
})
RELATIONS: dict[str, tuple[str, str]] = {
    "DESIGNED_BY": ("REQUIREMENT", "UML_ELEMENT"),
    "IMPLEMENTED_BY": ("REQUIREMENT", "MODULE"),
    "GENERATED_AS": ("UML_ELEMENT", "CODE_SYMBOL"),
    "PRODUCED": ("RULE", "CODE_FILE"),
    "CONSTRAINED": ("KNOWLEDGE_ITEM", "CODE_FILE"),
    "CONTAINS": ("MODULE", "CODE_FILE"),
    "DEFINES": ("CODE_FILE", "CODE_SYMBOL"),
    "EXPOSED_BY": ("REQUIREMENT", "API_OPERATION"),
    "STORED_BY": ("REQUIREMENT", "DATABASE_ENTITY"),
    "VERIFIED_THROUGH": ("REQUIREMENT", "TEST_SEAM"),
    "TARGETS": ("TEST_SEAM", "MODULE"),
    "PART_OF": ("MODULE", "ARTIFACT"),
    "EXERCISES": ("C4_TEST", "TEST_SEAM"),
    "IMPACTS": ("DEFECT_REPORT", "MODULE"),
    "REGENERATED": ("PATCH_EVENT", "MODULE"),
    "AUTHORIZES": ("READINESS_SIGNAL", "ARTIFACT"),
    "DEPLOYED": ("DEPLOYMENT_EVENT", "ARTIFACT"),
}
EVENT_NODE_TYPES = frozenset({"DEFECT_REPORT", "PATCH_EVENT", "C4_TEST", "READINESS_SIGNAL", "DEPLOYMENT_EVENT"})
# Hosting links make scaffold artifacts traceable but are not semantic impact evidence.
DIRECT = "DIRECT"
HOSTING = "HOSTING_CLOSURE"
REQUIRED_FILE_ATTRIBUTES = (
    "requirement_ids", "srs_version", "uml_version", "rule_ids", "template_ref", "sha256", "generation_run_id",
)


def node_id(node_type: str, key: str) -> str:
    return f"{node_type}:{key}"


@dataclass
class LivingTraceGraph:
    graph_id: str
    project_id: str
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    links: list[dict[str, Any]] = field(default_factory=list)
    version: int = 0
    generation_run_id: str | None = None
    artifact_digest_sha256: str | None = None
    parent_version: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    # -- construction -------------------------------------------------------
    def add_node(self, node_type: str, key: str, label: str | None = None, **attributes: Any) -> str:
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node type {node_type}")
        identifier = node_id(node_type, key)
        existing = self.nodes.get(identifier)
        if existing is None:
            self.nodes[identifier] = {"node_id": identifier, "node_type": node_type, "key": key,
                                      "label": label or key, "attributes": dict(attributes)}
        else:
            existing["attributes"].update(attributes)
        return identifier

    def add_link(self, source: str, relation: str, target: str, *, evidence: str = DIRECT,
                 detail: str = "", version_tag: str = "") -> None:
        expected = RELATIONS.get(relation)
        if expected is None:
            raise ValueError(f"unknown relation {relation}")
        if (self.nodes[source]["node_type"], self.nodes[target]["node_type"]) != expected:
            raise ValueError(f"{relation} requires {expected}, got {source} -> {target}")
        identity = f"{source}|{relation}|{target}|{version_tag}"
        link_id = "TL-" + sha256(identity.encode("utf-8")).hexdigest()[:16]
        if any(link["link_id"] == link_id for link in self.links):
            return
        self.links.append({
            "link_id": link_id, "logical_id": f"{source}|{relation}|{target}", "source": source,
            "relation": relation, "target": target, "evidence": evidence, "detail": detail,
            "status": "ACTIVE", "created_in_version": None, "superseded_in_version": None,
        })

    # -- queries --------------------------------------------------------------
    def active_links(self) -> list[dict[str, Any]]:
        return [link for link in self.links if link["status"] == "ACTIVE"]

    def incoming(self, target: str, relation: str) -> list[dict[str, Any]]:
        return [l for l in self.active_links() if l["target"] == target and l["relation"] == relation]

    def outgoing(self, source: str, relation: str) -> list[dict[str, Any]]:
        return [l for l in self.active_links() if l["source"] == source and l["relation"] == relation]

    def orphans(self) -> list[dict[str, str]]:
        problems: list[dict[str, str]] = []
        for node in self.nodes.values():
            if node["node_type"] != "CODE_FILE" or not node["attributes"].get("accepted", True):
                continue
            nid = node["node_id"]
            missing_attributes = [a for a in REQUIRED_FILE_ATTRIBUTES if not node["attributes"].get(a)]
            if missing_attributes:
                problems.append({"node_id": nid, "reason": f"missing provenance attributes {missing_attributes}"})
            if not self.incoming(nid, "PRODUCED"):
                problems.append({"node_id": nid, "reason": "no RULE PRODUCED link"})
            containers = self.incoming(nid, "CONTAINS")
            if not containers:
                problems.append({"node_id": nid, "reason": "not contained in any MODULE"})
            elif not any(self.incoming(c["source"], "IMPLEMENTED_BY") for c in containers):
                problems.append({"node_id": nid, "reason": "module has no originating REQUIREMENT"})
        return problems

    def modules_for_requirements(self, requirement_ids: set[str], *, direct_only: bool = True) -> set[str]:
        modules = set()
        for link in self.active_links():
            if link["relation"] != "IMPLEMENTED_BY":
                continue
            if direct_only and link["evidence"] != DIRECT:
                continue
            if self.nodes[link["source"]]["key"] in requirement_ids:
                modules.add(self.nodes[link["target"]]["key"])
        return modules

    def modules_for_seam(self, seam_id: str) -> set[str]:
        return {self.nodes[l["target"]]["key"] for l in self.outgoing(node_id("TEST_SEAM", seam_id), "TARGETS")}

    def coverage(self) -> dict[str, Any]:
        rows = []
        for node in sorted(self.nodes.values(), key=lambda n: n["node_id"]):
            if node["node_type"] != "REQUIREMENT":
                continue
            nid = node["node_id"]
            designed = len(self.outgoing(nid, "DESIGNED_BY"))
            implemented = [l for l in self.outgoing(nid, "IMPLEMENTED_BY") if l["evidence"] == DIRECT]
            seams = len(self.outgoing(nid, "VERIFIED_THROUGH"))
            api = len(self.outgoing(nid, "EXPOSED_BY"))
            stored = len(self.outgoing(nid, "STORED_BY"))
            if implemented and designed and seams:
                state = "TRACED_TO_CODE_AND_SEAM"
            elif implemented:
                state = "TRACED_TO_CODE_ONLY"
            else:
                state = "NOT_IMPLEMENTED"
            rows.append({"requirement_id": node["key"], "status": state, "uml_elements": designed,
                         "modules": len(implemented), "test_seams": seams, "api_operations": api, "database_entities": stored})
        traced = sum(r["status"] == "TRACED_TO_CODE_AND_SEAM" for r in rows)
        return {
            "policy": "TRACE_COVERAGE_V1 (structural trace coverage; not test or correctness coverage)",
            "requirements": rows,
            "traced_count": traced,
            "total": len(rows),
            "orphan_artifacts": self.orphans(),
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": TRACE_SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "project_id": self.project_id,
            "version": self.version,
            "parent_version": self.parent_version,
            "generation_run_id": self.generation_run_id,
            "artifact_digest_sha256": self.artifact_digest_sha256,
            "nodes": sorted(self.nodes.values(), key=lambda n: n["node_id"]),
            "links": sorted(self.links, key=lambda l: (l["status"] != "ACTIVE", l["link_id"])),
            "events": self.events,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "LivingTraceGraph":
        graph = cls(data["graph_id"], data["project_id"])
        graph.nodes = {node["node_id"]: node for node in data["nodes"]}
        graph.links = list(data["links"])
        graph.version = data["version"]
        graph.parent_version = data.get("parent_version")
        graph.generation_run_id = data.get("generation_run_id")
        graph.artifact_digest_sha256 = data.get("artifact_digest_sha256")
        graph.events = list(data.get("events", []))
        return graph


def graph_id_for(project_id: str) -> str:
    return "LTG-" + sha256(project_id.encode("utf-8")).hexdigest()[:16]


def evolve(previous: LivingTraceGraph | None, current: LivingTraceGraph) -> dict[str, Any]:
    """Merge ``current`` onto ``previous``: preserve, supersede or expire links. Returns a change summary."""
    version = (previous.version if previous else 0) + 1
    current.version = version
    current.parent_version = previous.version if previous else None
    if previous is None:
        for link in current.links:
            link["created_in_version"] = version
        return {"preserved": 0, "added": len(current.links), "superseded": 0, "expired": 0}
    # Event links (defects, patches, readiness, deployment) are historical facts: carry them forward unchanged.
    carried = [dict(link) for link in previous.links
               if previous.nodes.get(link["source"], {}).get("node_type") in EVENT_NODE_TYPES
               and link["link_id"] not in {l["link_id"] for l in current.links}]
    previous_links = [link for link in previous.links if link not in carried and not (
        previous.nodes.get(link["source"], {}).get("node_type") in EVENT_NODE_TYPES)]
    old_active = {link["link_id"]: link for link in previous_links if link["status"] == "ACTIVE"}
    new_ids = {link["link_id"] for link in current.links}
    new_logical = {link["logical_id"] for link in current.links}
    preserved = added = superseded = expired = 0
    for link in current.links:
        if link["link_id"] in old_active:
            link["created_in_version"] = old_active[link["link_id"]]["created_in_version"]
            preserved += 1
        else:
            link["created_in_version"] = version
            added += 1
    history = [dict(link) for link in previous_links if link["status"] != "ACTIVE"] + carried
    for link_id, link in old_active.items():
        if link_id in new_ids:
            continue
        retired = dict(link)
        retired["superseded_in_version"] = version
        if link["logical_id"] in new_logical:
            retired["status"] = "SUPERSEDED"
            superseded += 1
        else:
            retired["status"] = "EXPIRED"
            expired += 1
        history.append(retired)
    for node_key, node in previous.nodes.items():
        if node_key not in current.nodes and node["node_type"] in EVENT_NODE_TYPES | {"ARTIFACT"}:
            current.nodes[node_key] = node
    current.links.extend(history)
    current.events = previous.events + current.events
    return {"preserved": preserved, "added": added, "superseded": superseded, "expired": expired}


class LivingTraceStore:
    """Append-only versions in the existing C3 traceability SQLite file."""

    def __init__(self, database_path: Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hybrid_trace_versions ("
                " graph_id TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT NOT NULL,"
                " generation_run_id TEXT, artifact_digest TEXT, payload TEXT NOT NULL,"
                " payload_sha256 TEXT NOT NULL, persisted_at TEXT NOT NULL, PRIMARY KEY (graph_id, version))"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # sqlite3's own context manager only commits; close explicitly so no file handle outlives the call.
        connection = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
        finally:
            connection.close()

    def append(self, graph: LivingTraceGraph, expected_version: int) -> None:
        payload = graph.to_json()
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM hybrid_trace_versions WHERE graph_id = ?", (graph.graph_id,)
                ).fetchone()
                if row[0] + 1 != expected_version or graph.version != expected_version:
                    raise ApplicationError(
                        [ErrorDetail(code="TRACE_VERSION_CONFLICT", field="graph_version",
                                     message=f"Living trace graph moved to version {row[0]}; expected base {expected_version - 1}.")],
                        status_code=status.HTTP_409_CONFLICT,
                    )
                connection.execute(
                    "INSERT INTO hybrid_trace_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (graph.graph_id, graph.version, graph.project_id, graph.generation_run_id,
                     graph.artifact_digest_sha256, text, canonical_sha256(payload), datetime.now(UTC).isoformat()),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def latest(self, graph_id: str) -> LivingTraceGraph | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM hybrid_trace_versions WHERE graph_id = ? ORDER BY version DESC LIMIT 1", (graph_id,)
            ).fetchone()
        return LivingTraceGraph.from_json(json.loads(row[0])) if row else None

    def get(self, graph_id: str, version: int) -> LivingTraceGraph | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM hybrid_trace_versions WHERE graph_id = ? AND version = ?", (graph_id, version)
            ).fetchone()
        return LivingTraceGraph.from_json(json.loads(row[0])) if row else None

    def versions(self, graph_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT version, generation_run_id, artifact_digest, payload_sha256, persisted_at FROM hybrid_trace_versions"
                " WHERE graph_id = ? ORDER BY version", (graph_id,)
            ).fetchall()
        return [
            {"version": r[0], "generation_run_id": r[1], "artifact_digest_sha256": r[2], "payload_sha256": r[3], "persisted_at_utc": r[4]}
            for r in rows
        ]
