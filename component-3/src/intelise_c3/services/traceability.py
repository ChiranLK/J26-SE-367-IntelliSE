"""Persistent living requirement traceability orchestration."""

from fastapi import status

from intelise_c3.contracts.traceability import (
    GraphComparisonRequest,
    GraphCreateRequest,
    GraphUpdateRequest,
)
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest, TraceResolutionStatus
from intelise_c3.domain.traceability import (
    ArtifactChangeClassification,
    GraphChangeReport,
    GraphLifecycleStatus,
    GraphNodeType,
    GraphUpdateResult,
    ImpactSet,
    RequirementTraceChain,
    ResearchGroundTruth,
    RtmExport,
    TraceGraphBuild,
    TraceGraphLink,
    TraceGraphNode,
    TraceGraphSnapshot,
    TraceabilityEvaluationReport,
    TraceabilityMetricsReport,
)
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.traceability.builder import TraceabilityGraphBuilder, graph_node_id
from intelise_c3.traceability.queries import (
    chain as query_chain,
    compute_metrics_report,
    export_rtm as query_export_rtm,
    impact_set as query_impact_set,
    requirements_for_module as query_requirements_for_module,
)
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService


class TraceabilityService:
    """Verify, construct, compare, version, and evaluate traceability graphs."""

    def __init__(
        self,
        verifier: ManifestVerificationService,
        builder: TraceabilityGraphBuilder,
        store: SQLiteTraceabilityStore,
    ) -> None:
        self._verifier = verifier
        self._builder = builder
        self._store = store

    def create(self, request: GraphCreateRequest) -> TraceGraphSnapshot:
        self._verifier.verify(request.manifest, request.workspace_relative_path)
        build = self._builder.build(request.manifest)
        return self._store.append(build, request.manifest)

    def retrieve(self, graph_id: str, version: int) -> TraceGraphSnapshot:
        return self._store.get(graph_id, version)

    def latest(self, graph_id: str) -> TraceGraphSnapshot:
        return self._store.latest(graph_id)

    def chain(
        self,
        graph_id: str,
        requirement_id: str,
        version: int | None = None,
    ) -> RequirementTraceChain:
        snapshot = self.latest(graph_id) if version is None else self.retrieve(graph_id, version)
        return query_chain(snapshot, requirement_id)

    def impact_set(
        self,
        graph_id: str,
        requirement_id: str,
        version: int | None = None,
    ) -> ImpactSet:
        snapshot = self.latest(graph_id) if version is None else self.retrieve(graph_id, version)
        manifest = self._store.get_manifest(graph_id, snapshot.graph_version)
        return query_impact_set(snapshot, requirement_id, manifest)

    def requirements_for_module(
        self,
        graph_id: str,
        module_identifier: str,
        version: int | None = None,
    ) -> tuple[str, ...]:
        snapshot = self.latest(graph_id) if version is None else self.retrieve(graph_id, version)
        manifest = self._store.get_manifest(graph_id, snapshot.graph_version)
        return query_requirements_for_module(snapshot, module_identifier, manifest)

    def export_rtm(
        self,
        graph_id: str,
        version: int | None = None,
    ) -> RtmExport:
        snapshot = self.latest(graph_id) if version is None else self.retrieve(graph_id, version)
        return query_export_rtm(snapshot)

    def metrics(
        self,
        graph_id: str,
        version: int | None = None,
        oracle: ResearchGroundTruth | None = None,
        change_report: GraphChangeReport | None = None,
    ) -> TraceabilityMetricsReport:
        snapshot = self.latest(graph_id) if version is None else self.retrieve(graph_id, version)
        return compute_metrics_report(snapshot, oracle=oracle, change_report=change_report)

    def compare(self, graph_id: str, request: GraphComparisonRequest) -> GraphChangeReport:
        old_snapshot = self._store.get(graph_id, request.base_graph_version)
        old_manifest = self._store.get_manifest(graph_id, request.base_graph_version)
        self._verifier.verify(request.manifest, request.workspace_relative_path)
        candidate = self._builder.build(request.manifest)
        report, _ = self._prepare_update(
            old_snapshot,
            old_manifest,
            candidate,
            request.manifest,
            request.source_transition_evidence,
            target_version=request.base_graph_version + 1,
        )
        return report

    def update(self, graph_id: str, request: GraphUpdateRequest) -> GraphUpdateResult:
        latest = self._store.latest(graph_id)
        if latest.graph_version != request.base_graph_version:
            self._fail(
                "STALE_GRAPH_BASE_VERSION",
                "base_graph_version",
                "Living graph updates must start from the latest persisted version.",
            )
        old_manifest = self._store.get_manifest(graph_id, request.base_graph_version)
        self._verifier.verify(request.manifest, request.workspace_relative_path)
        candidate = self._builder.build(request.manifest)
        target_version = self._store.next_version(graph_id)
        report, updated_build = self._prepare_update(
            latest,
            old_manifest,
            candidate,
            request.manifest,
            request.source_transition_evidence,
            target_version=target_version,
        )
        snapshot = self._store.append(
            updated_build,
            request.manifest,
            expected_version=target_version,
        )
        return GraphUpdateResult(snapshot=snapshot, change_report=report)

    def evaluate(
        self,
        graph_id: str,
        version: int,
        ground_truth: ResearchGroundTruth,
    ) -> TraceabilityEvaluationReport:
        snapshot = self._store.get(graph_id, version)
        scope = set(ground_truth.in_scope_node_ids)
        active_node_ids = {
            node.node_id
            for node in snapshot.nodes
            if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
        }
        if not scope or not scope.issubset(active_node_ids):
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="INVALID_GROUND_TRUTH_SCOPE",
                        field="ground_truth.in_scope_node_ids",
                        message=(
                            "Ground-truth scope must contain only active graph "
                            "node IDs and must not be empty."
                        ),
                    )
                ],
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        expected = {
            (item.source_node_id, item.relation_type.value, item.target_node_id)
            for item in ground_truth.expected_links
        }
        if any(source not in scope or target not in scope for source, _, target in expected):
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="INVALID_GROUND_TRUTH_LINK",
                        field="ground_truth.expected_links",
                        message="Every expected link endpoint must be in the declared scope.",
                    )
                ],
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        predicted = {
            (link.source_node_id, link.relation_type.value, link.target_node_id)
            for link in snapshot.links
            if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
            and link.resolution_status is TraceResolutionStatus.RESOLVED
            and link.source_node_id in scope
            and link.target_node_id in scope
        }
        (
            true_positive,
            false_positive,
            false_negative,
            precision,
            recall,
            f1_score,
        ) = self._calculate_metrics(predicted, expected)
        return TraceabilityEvaluationReport(
            graph_id=graph_id,
            graph_version=version,
            ground_truth_dataset_id=ground_truth.dataset_id,
            ground_truth_dataset_version=ground_truth.dataset_version,
            ground_truth_authorship=ground_truth.authorship,
            true_positive_count=true_positive,
            false_positive_count=false_positive,
            false_negative_count=false_negative,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
        )

    @staticmethod
    def _calculate_metrics(
        predicted: set[tuple[str, str, str]],
        expected: set[tuple[str, str, str]],
    ) -> tuple[int, int, int, float, float, float]:
        """Calculate unrounded set-based evaluation metrics deterministically."""

        true_positive = len(predicted & expected)
        false_positive = len(predicted - expected)
        false_negative = len(expected - predicted)
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1_score = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        return (
            true_positive,
            false_positive,
            false_negative,
            precision,
            recall,
            f1_score,
        )

    def _prepare_update(
        self,
        old: TraceGraphSnapshot,
        old_manifest: GenerationManifest,
        candidate: TraceGraphBuild,
        new_manifest: GenerationManifest,
        transition_evidence,
        *,
        target_version: int,
    ) -> tuple[GraphChangeReport, TraceGraphBuild]:
        if candidate.graph_id != old.graph_id:
            self._fail(
                "GRAPH_PROJECT_MISMATCH",
                "manifest.source.project_id",
                "A different project must start a separate traceability graph.",
            )
        source_changed = old.source != candidate.source
        if source_changed and transition_evidence is None:
            self._fail(
                "SOURCE_VERSION_APPROVAL_REQUIRED",
                "source_transition_evidence",
                "Changed source identities require explicit researcher approval.",
            )

        old_files = {item.file_id: item for item in old_manifest.files}
        new_files = {item.file_id: item for item in new_manifest.files}
        old_ids = set(old_files)
        new_ids = set(new_files)
        added = new_ids - old_ids
        removed = old_ids - new_ids
        common = old_ids & new_ids
        changed = {
            file_id
            for file_id in common
            if old_files[file_id].sha256 != new_files[file_id].sha256
            or old_files[file_id].relative_path != new_files[file_id].relative_path
        }
        unchanged = common - changed

        old_active_nodes = {
            item.node_id: item
            for item in old.nodes
            if item.lifecycle_status is GraphLifecycleStatus.ACTIVE
        }
        candidate_nodes = {item.node_id: item for item in candidate.nodes}
        # A rebuild stamps candidates with the new run. Existing stable graph
        # identities retain their original creation evidence, including None
        # for snapshots that predate the field.
        candidate_nodes = {
            node_id: (
                node.model_copy(
                    update={
                        "created_in_generation_run_id": old_active_nodes[
                            node_id
                        ].created_in_generation_run_id
                    }
                )
                if node_id in old_active_nodes
                else node
            )
            for node_id, node in candidate_nodes.items()
        }
        added_nodes = set(candidate_nodes) - set(old_active_nodes)
        removed_nodes = set(old_active_nodes) - set(candidate_nodes)
        common_nodes = set(old_active_nodes) & set(candidate_nodes)
        changed_nodes = {
            node_id
            for node_id in common_nodes
            if old_active_nodes[node_id] != candidate_nodes[node_id]
        }
        unchanged_nodes = common_nodes - changed_nodes

        old_active_links = {
            item.logical_link_id: item
            for item in old.links
            if item.lifecycle_status is GraphLifecycleStatus.ACTIVE
        }
        candidate_links = {item.logical_link_id: item for item in candidate.links}
        candidate_links = {
            logical_id: (
                link.model_copy(
                    update={
                        "created_in_generation_run_id": old_active_links[
                            logical_id
                        ].created_in_generation_run_id
                    }
                )
                if logical_id in old_active_links
                else link
            )
            for logical_id, link in candidate_links.items()
        }
        added_links = set(candidate_links) - set(old_active_links)
        retired_links = set(old_active_links) - set(candidate_links)
        shared_links = set(old_active_links) & set(candidate_links)
        replaced_links = {
            link_id
            for link_id in shared_links
            if old_active_links[link_id] != candidate_links[link_id]
        }
        added_links |= replaced_links
        retired_links |= replaced_links
        changed_module_nodes = {
            graph_node_id(GraphNodeType.CODE_MODULE, file_id) for file_id in changed
        }
        revalidated_links = {
            link_id
            for link_id in shared_links - replaced_links
            if candidate_links[link_id].source_node_id in changed_module_nodes
            or candidate_links[link_id].target_node_id in changed_module_nodes
        }
        preserved_links = shared_links - replaced_links - revalidated_links

        retired_node_records = [
            node.model_copy(
                update={
                    "lifecycle_status": GraphLifecycleStatus.RETIRED,
                    "retired_in_graph_version": target_version,
                }
            )
            for node_id, node in old_active_nodes.items()
            if node_id in removed_nodes
        ]
        previously_retired_nodes = [
            node for node in old.nodes if node.lifecycle_status is GraphLifecycleStatus.RETIRED
        ]
        retired_link_records = [
            link.model_copy(
                update={
                    "link_id": f"{link.logical_link_id}:RETIRED:{target_version}",
                    "lifecycle_status": GraphLifecycleStatus.RETIRED,
                    "retired_in_graph_version": target_version,
                    "retirement_reason": "Absent or superseded in the newly verified manifest.",
                }
            )
            for logical_id, link in old_active_links.items()
            if logical_id in retired_links
        ]
        previously_retired_links = [
            link for link in old.links if link.lifecycle_status is GraphLifecycleStatus.RETIRED
        ]
        active_node_records = [
            old_active_nodes[node_id]
            if node_id in unchanged_nodes
            else candidate_nodes[node_id]
            for node_id in sorted(candidate_nodes)
        ]
        active_link_records = [
            old_active_links[logical_id]
            if logical_id in preserved_links
            else candidate_links[logical_id]
            for logical_id in sorted(candidate_links)
        ]
        nodes = tuple(
            sorted(
                [
                    *active_node_records,
                    *previously_retired_nodes,
                    *retired_node_records,
                ],
                key=lambda item: (item.node_id, item.lifecycle_status.value),
            )
        )
        links = tuple(
            sorted(
                [
                    *active_link_records,
                    *previously_retired_links,
                    *retired_link_records,
                ],
                key=lambda item: item.link_id,
            )
        )
        coverage = self._builder.coverage(
            candidate.source.requirement_ids,
            nodes,
            links,
            candidate.coverage.diagnostics.missing_evidence,
        )
        updated_payload = candidate.model_dump(mode="json")
        updated_payload["nodes"] = [item.model_dump(mode="json") for item in nodes]
        updated_payload["links"] = [item.model_dump(mode="json") for item in links]
        updated_payload["coverage"] = coverage.model_dump(mode="json")
        updated_payload.pop("graph_content_digest_sha256", None)
        updated_build = candidate.model_copy(
            update={
                "nodes": nodes,
                "links": links,
                "coverage": coverage,
                "graph_content_digest_sha256": canonical_sha256(updated_payload),
            }
        )
        report = GraphChangeReport(
            graph_id=old.graph_id,
            base_graph_version=old.graph_version,
            candidate_generation_run_id=candidate.generation_run_id,
            artifacts=ArtifactChangeClassification(
                added=tuple(sorted(added)),
                removed=tuple(sorted(removed)),
                changed=tuple(sorted(changed)),
                unchanged=tuple(sorted(unchanged)),
            ),
            added_node_ids=tuple(sorted(added_nodes)),
            removed_node_ids=tuple(sorted(removed_nodes)),
            changed_node_ids=tuple(sorted(changed_nodes)),
            unchanged_node_ids=tuple(sorted(unchanged_nodes)),
            added_link_ids=tuple(sorted(added_links)),
            retired_link_ids=tuple(sorted(retired_links)),
            preserved_link_ids=tuple(sorted(preserved_links)),
            revalidated_link_ids=tuple(sorted(revalidated_links)),
            source_version_changed=source_changed,
            source_transition_evidence=transition_evidence,
        )
        return report, updated_build

    @staticmethod
    def _fail(code: str, field: str, message: str) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status.HTTP_409_CONFLICT,
        )
