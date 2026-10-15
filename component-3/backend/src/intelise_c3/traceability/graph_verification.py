"""Full canonical verification of a stored graph against its verified manifest.

``GraphEvidenceVerifier`` compares a persisted ``TraceGraphSnapshot`` with the
graph deterministically rebuilt from the already-verified source manifest by the
same ``TraceabilityGraphBuilder``. Any difference in a node or link that is
ACTIVE in the snapshot is rejected, even when its stable identifier is
unchanged: identity, endpoints, relation, resolution status, review status,
lifecycle, provenance and evidence references, module identity, and file hashes.

Version-aware legacy handling is not re-implemented here. The only legacy
normalization in the traceability code (historical C2 reverse-direction edges,
selected by the manifest's ``mapping_policy_version``) happens inside the
builder, so the rebuild reproduces it. A snapshot that lacks the current
relation-direction policy version has no supported verification path and is
rejected rather than guessed at.

Historical RETIRED records cannot be re-derived from the current manifest. They
are checked for internal consistency and are covered by the recomputed content
digest, but this module cannot prove their historical authenticity.

Verification is read-only: it never mutates a snapshot or the SQLite store.
"""

from collections import Counter

from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    TraceGraphBuild,
    TraceGraphLink,
    TraceGraphNode,
    TraceGraphSnapshot,
)
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.traceability.builder import TraceabilityGraphBuilder

MAX_REPORTED_PROBLEMS = 25


def _changed_fields(left: TraceGraphNode | TraceGraphLink, right: TraceGraphNode | TraceGraphLink) -> list[str]:
    left_data = left.model_dump(mode="json")
    right_data = right.model_dump(mode="json")
    return sorted(
        key for key in left_data if canonical_sha256(left_data[key]) != canonical_sha256(right_data.get(key))
    )


class GraphEvidenceVerifier:
    """Return deterministic problem labels; an empty list means fully verified."""

    def __init__(self, builder: TraceabilityGraphBuilder) -> None:
        self._builder = builder

    def problems(self, snapshot: TraceGraphSnapshot, rebuilt: TraceGraphBuild) -> list[str]:
        found: list[str] = []
        found.extend(self._header_problems(snapshot, rebuilt))
        found.extend(self._node_problems(snapshot, rebuilt))
        found.extend(self._link_problems(snapshot, rebuilt))
        found.extend(self._retired_history_problems(snapshot))
        found.extend(self._derived_problems(snapshot, rebuilt))
        return sorted(dict.fromkeys(found))[:MAX_REPORTED_PROBLEMS]

    @staticmethod
    def _header_problems(snapshot: TraceGraphSnapshot, rebuilt: TraceGraphBuild) -> list[str]:
        found: list[str] = []
        if snapshot.relation_direction_policy_version != rebuilt.relation_direction_policy_version:
            found.append("header:relation-direction-policy-version")
        for field in (
            "graph_schema_version",
            "graph_id",
            "generation_run_id",
            "artifact_digest_sha256",
            "evidence_digest_sha256",
            "manifest_sha256",
        ):
            if getattr(snapshot, field) != getattr(rebuilt, field):
                found.append(f"header:{field}")
        if canonical_sha256(snapshot.source) != canonical_sha256(rebuilt.source):
            found.append("header:source-identity")
        return found

    @staticmethod
    def _node_problems(snapshot: TraceGraphSnapshot, rebuilt: TraceGraphBuild) -> list[str]:
        found: list[str] = []
        active = [n for n in snapshot.nodes if n.lifecycle_status is GraphLifecycleStatus.ACTIVE]
        for node_id, count in Counter(n.node_id for n in active).items():
            if count > 1:
                found.append(f"node-duplicate-active:{node_id}")
        stored = {n.node_id: n for n in active}
        expected = {n.node_id: n for n in rebuilt.nodes}
        for node_id in sorted(set(expected) - set(stored)):
            found.append(f"node-missing:{node_id}")
        for node_id in sorted(set(stored) - set(expected)):
            found.append(f"node-extra:{node_id}")
        for node_id in sorted(set(stored) & set(expected)):
            if canonical_sha256(stored[node_id]) != canonical_sha256(expected[node_id]):
                fields = ",".join(_changed_fields(stored[node_id], expected[node_id])) or "canonical"
                found.append(f"node-mismatch:{node_id}:{fields}")
        return found

    @staticmethod
    def _link_problems(snapshot: TraceGraphSnapshot, rebuilt: TraceGraphBuild) -> list[str]:
        found: list[str] = []
        active = [l for l in snapshot.links if l.lifecycle_status is GraphLifecycleStatus.ACTIVE]
        for logical_id, count in Counter(l.logical_link_id for l in active).items():
            if count > 1:
                found.append(f"link-duplicate-active:{logical_id}")
        stored = {l.logical_link_id: l for l in active}
        expected = {l.logical_link_id: l for l in rebuilt.links}
        for logical_id in sorted(set(expected) - set(stored)):
            found.append(f"link-missing:{logical_id}")
        for logical_id in sorted(set(stored) - set(expected)):
            found.append(f"link-extra:{logical_id}")
        for logical_id in sorted(set(stored) & set(expected)):
            if canonical_sha256(stored[logical_id]) != canonical_sha256(expected[logical_id]):
                fields = ",".join(_changed_fields(stored[logical_id], expected[logical_id])) or "canonical"
                found.append(f"link-mismatch:{logical_id}:{fields}")
        return found

    @staticmethod
    def _retired_history_problems(snapshot: TraceGraphSnapshot) -> list[str]:
        found: list[str] = []
        for node in snapshot.nodes:
            if node.lifecycle_status is GraphLifecycleStatus.RETIRED and not (
                node.retired_in_graph_version is not None
                and 2 <= node.retired_in_graph_version <= snapshot.graph_version
            ):
                found.append(f"retired-node-inconsistent:{node.node_id}")
        link_ids = Counter(link.link_id for link in snapshot.links)
        for link_id, count in link_ids.items():
            if count > 1:
                found.append(f"link-duplicate-id:{link_id}")
        for link in snapshot.links:
            if link.lifecycle_status is GraphLifecycleStatus.RETIRED and not (
                link.retired_in_graph_version is not None
                and 2 <= link.retired_in_graph_version <= snapshot.graph_version
                and link.retirement_reason
            ):
                found.append(f"retired-link-inconsistent:{link.link_id}")
        return found

    def _derived_problems(self, snapshot: TraceGraphSnapshot, rebuilt: TraceGraphBuild) -> list[str]:
        found: list[str] = []
        coverage = self._builder.coverage(
            rebuilt.source.requirement_ids,
            snapshot.nodes,
            snapshot.links,
            rebuilt.coverage.diagnostics.missing_evidence,
        )
        if canonical_sha256(coverage) != canonical_sha256(snapshot.coverage):
            found.append("derived:coverage")
        payload = snapshot.model_dump(
            mode="json",
            include=set(TraceGraphBuild.model_fields) - {"graph_content_digest_sha256"},
        )
        if canonical_sha256(payload) != snapshot.graph_content_digest_sha256:
            found.append("derived:graph-content-digest")
        return found
