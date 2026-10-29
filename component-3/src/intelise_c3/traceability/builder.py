"""Deterministic graph construction from verified Task 6 evidence."""

from hashlib import sha256

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import (
    GenerationManifest,
    TraceEntityType,
    TraceLinkProvenance,
    TraceabilityLink,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    GraphNodeType,
    GraphSourceIdentity,
    RequirementCoverage,
    RequirementCoverageStatus,
    TraceabilityCoverageReport,
    TraceabilityDiagnostics,
    TraceGraphBuild,
    TraceGraphLink,
    TraceGraphNode,
)
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.traceability.semantics import (
    LEGACY_C2_DIRECTION_RULE,
    LEGACY_C2_NORMALIZATION_RULE,
    LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION,
    RELATION_DIRECTION_POLICY_VERSION,
    is_permitted_relation,
)

_ENTITY_TO_NODE = {
    TraceEntityType.REQUIREMENT: GraphNodeType.REQUIREMENT,
    TraceEntityType.UML_ELEMENT: GraphNodeType.UML_ELEMENT,
    TraceEntityType.UML_ANCHOR: GraphNodeType.DESIGN_ANCHOR,
    TraceEntityType.FILE: GraphNodeType.CODE_MODULE,
    TraceEntityType.API_OPERATION: GraphNodeType.API_OPERATION,
    TraceEntityType.DATABASE_TABLE: GraphNodeType.DATABASE_ARTIFACT,
    TraceEntityType.DATABASE_COLUMN: GraphNodeType.DATABASE_ARTIFACT,
    TraceEntityType.TEST_SEAM: GraphNodeType.TEST_HOOK,
    TraceEntityType.UI_ARTIFACT: GraphNodeType.UI_ARTIFACT,
}


def graph_node_id(node_type: GraphNodeType, source_identity: str) -> str:
    return f"{node_type.value}:{source_identity}"


class TraceabilityGraphBuilder:
    """Translate only explicit manifest identities and evidence into a graph."""

    def build(self, manifest: GenerationManifest) -> TraceGraphBuild:
        if not manifest.source.requirement_ids:
            self._fail(
                "EMPTY_REQUIREMENTS_LIST",
                "manifest.source.requirement_ids",
                "The source manifest must contain at least one requirement.",
            )
        nodes: dict[str, TraceGraphNode] = {}
        links: dict[str, TraceGraphLink] = {}
        missing_evidence: list[str] = []

        def add_node(node: TraceGraphNode) -> None:
            existing = nodes.get(node.node_id)
            if existing is not None and existing != node:
                self._fail(
                    "CONFLICTING_GRAPH_NODE",
                    node.node_id,
                    "One source identity produced conflicting graph nodes.",
                )
            nodes[node.node_id] = node

        for requirement_id in manifest.source.requirement_ids:
            add_node(self._node(GraphNodeType.REQUIREMENT, requirement_id))
        for uml_id in manifest.source.uml_ids:
            add_node(self._node(GraphNodeType.UML_ELEMENT, uml_id))
        for anchor in manifest.source.requirement_uml_anchors:
            add_node(
                self._node(
                    GraphNodeType.DESIGN_ANCHOR,
                    anchor.anchor_id,
                    requirement_id=anchor.requirement_id,
                    uml_id=anchor.uml_id,
                )
            )
        for ui in manifest.source.ui_artifacts:
            add_node(
                self._node(
                    GraphNodeType.UI_ARTIFACT,
                    ui.ui_id,
                    artifact_type=ui.artifact_type,
                    source_ref=ui.source_ref,
                )
            )
        for record in manifest.files:
            add_node(
                self._node(
                    GraphNodeType.CODE_MODULE,
                    record.file_id,
                    label=record.module_identity,
                    relative_path=record.relative_path,
                    module_identity=record.module_identity,
                    artifact_type=record.artifact_type.value,
                    origin=record.origin.value,
                    sha256=record.sha256,
                    size_bytes=record.size_bytes,
                )
            )
        for api in manifest.api_references:
            for operation in api.operations:
                add_node(
                    self._node(
                        GraphNodeType.API_OPERATION,
                        operation.operation_id,
                        method=operation.method,
                        route_path=operation.route_path,
                        definition_path=api.definition_path,
                        success_status=operation.success_status,
                    )
                )
        for database in manifest.database_references:
            for table in database.tables:
                add_node(
                    self._node(
                        GraphNodeType.DATABASE_ARTIFACT,
                        table.table_id,
                        database_kind="TABLE",
                        name=table.name,
                        persistence_mode=database.persistence_mode,
                        runtime_repository_mode=database.runtime_repository_mode,
                        script_path=database.script_path,
                    )
                )
                for column in table.columns:
                    add_node(
                        self._node(
                            GraphNodeType.DATABASE_ARTIFACT,
                            column.column_id,
                            database_kind="COLUMN",
                            name=column.name,
                            table_id=table.table_id,
                            data_type=column.data_type,
                            nullable=column.nullable,
                            primary_key=column.primary_key,
                        )
                    )
        for seam in manifest.test_seams:
            add_node(
                self._node(
                    GraphNodeType.TEST_HOOK,
                    seam.reference_id,
                    module_path=seam.module_path,
                    seam_type=seam.seam_type,
                    description=seam.description,
                )
            )

        for anchor in manifest.source.requirement_uml_anchors:
            anchor_node = graph_node_id(GraphNodeType.DESIGN_ANCHOR, anchor.anchor_id)
            provenance = TraceLinkProvenance(
                evidence_kind="SOURCE_C2_ANCHOR",
                mapping_rule_id="C2_DESIGN_ANCHOR_GRAPH_V1",
                evidence_refs=(anchor.anchor_id,),
                details="Exact accepted C2 requirement-to-UML anchor identity.",
            )
            for target_type, target_id in (
                (GraphNodeType.REQUIREMENT, anchor.requirement_id),
                (GraphNodeType.UML_ELEMENT, anchor.uml_id),
            ):
                logical_id = self._link_id(
                    anchor_node,
                    TraceRelationType.DERIVED_FROM,
                    graph_node_id(target_type, target_id),
                    "C2_DESIGN_ANCHOR_GRAPH_V1",
                )
                links[logical_id] = TraceGraphLink(
                    link_id=logical_id,
                    logical_link_id=logical_id,
                    source_node_id=anchor_node,
                    relation_type=TraceRelationType.DERIVED_FROM,
                    target_node_id=graph_node_id(target_type, target_id),
                    resolution_status=TraceResolutionStatus.RESOLVED,
                    review_status=TraceReviewStatus.NOT_REQUIRED,
                    provenance=provenance,
                )

        for source_link in manifest.traceability.links:
            source_type = _ENTITY_TO_NODE.get(source_link.source_entity_type)
            target_type = _ENTITY_TO_NODE.get(source_link.target_entity_type)
            if source_type is None or target_type is None:
                missing_evidence.append(
                    f"Skipped unsupported manifest link endpoint: {source_link.link_id}"
                )
                continue
            (
                source_type,
                source_id,
                target_type,
                target_id,
                link_id,
                provenance,
            ) = self._normalize_legacy_direction(
                manifest,
                source_link,
                source_type,
                target_type,
            )
            if (
                source_link.resolution_status is TraceResolutionStatus.RESOLVED
                and provenance.evidence_kind == "UNRESOLVED_SOURCE_REFERENCE"
            ):
                self._fail(
                    "UNSUPPORTED_RESOLVED_LINK",
                    source_link.link_id,
                    "A resolved link cannot rely on unresolved source evidence.",
                )
            source_node_id = graph_node_id(source_type, source_id)
            target_node_id = graph_node_id(target_type, target_id)
            if source_node_id not in nodes or target_node_id not in nodes:
                missing_evidence.append(
                    f"Link {source_link.link_id} references an absent graph node."
                )
                continue
            links[link_id] = TraceGraphLink(
                link_id=link_id,
                logical_link_id=link_id,
                source_node_id=source_node_id,
                relation_type=source_link.relation_type,
                target_node_id=target_node_id,
                resolution_status=source_link.resolution_status,
                review_status=source_link.review_status,
                provenance=provenance,
            )

        for link in links.values():
            source_node = nodes[link.source_node_id]
            target_node = nodes[link.target_node_id]
            if not is_permitted_relation(
                link.relation_type,
                source_node.node_type,
                target_node.node_type,
            ):
                self._fail(
                    "INVALID_TRACE_RELATION_DIRECTION",
                    link.link_id,
                    (
                        f"{link.relation_type.value} does not permit "
                        f"{source_node.node_type.value} -> {target_node.node_type.value} "
                        f"under {RELATION_DIRECTION_POLICY_VERSION}."
                    ),
                )

        ordered_nodes = tuple(
            node.model_copy(
                update={"created_in_generation_run_id": manifest.generation_run_id}
            )
            for node in sorted(nodes.values(), key=lambda item: item.node_id)
        )
        ordered_links = tuple(
            link.model_copy(
                update={"created_in_generation_run_id": manifest.generation_run_id}
            )
            for link in sorted(links.values(), key=lambda item: item.link_id)
        )
        coverage = self.coverage(
            manifest.source.requirement_ids,
            ordered_nodes,
            ordered_links,
            tuple(sorted(missing_evidence)),
        )
        graph_id = "GRAPH-" + sha256(
            manifest.source.project_id.encode("utf-8")
        ).hexdigest()[:16].upper()
        source = GraphSourceIdentity(
            project_id=manifest.source.project_id,
            srs_version=manifest.source.srs_version,
            uml_version=manifest.source.uml_version,
            generation_context_version=manifest.source.generation_context_version,
            design_context_version=manifest.source.design_context_version,
            source_contract_versions=manifest.source.source_contract_versions,
            requirement_ids=manifest.source.requirement_ids,
            uml_ids=manifest.source.uml_ids,
        )
        manifest_hash = canonical_sha256(manifest)
        content_digest = canonical_sha256(
            {
                "graph_schema_version": "1.0",
                "relation_direction_policy_version": RELATION_DIRECTION_POLICY_VERSION,
                "graph_id": graph_id,
                "generation_run_id": manifest.generation_run_id,
                "source": source.model_dump(mode="json"),
                "artifact_digest_sha256": manifest.artifact_digest_sha256,
                "evidence_digest_sha256": manifest.run_evidence.evidence_digest_sha256,
                "manifest_sha256": manifest_hash,
                "nodes": [item.model_dump(mode="json") for item in ordered_nodes],
                "links": [item.model_dump(mode="json") for item in ordered_links],
                "coverage": coverage.model_dump(mode="json"),
            }
        )
        return TraceGraphBuild(
            relation_direction_policy_version=RELATION_DIRECTION_POLICY_VERSION,
            graph_id=graph_id,
            generation_run_id=manifest.generation_run_id,
            source=source,
            artifact_digest_sha256=manifest.artifact_digest_sha256,
            evidence_digest_sha256=manifest.run_evidence.evidence_digest_sha256,
            manifest_sha256=manifest_hash,
            nodes=ordered_nodes,
            links=ordered_links,
            coverage=coverage,
            graph_content_digest_sha256=content_digest,
        )

    @staticmethod
    def coverage(
        requirement_ids: tuple[str, ...],
        nodes: tuple[TraceGraphNode, ...],
        links: tuple[TraceGraphLink, ...],
        missing_evidence: tuple[str, ...] = (),
    ) -> TraceabilityCoverageReport:
        active_links = tuple(
            link for link in links if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
        )
        node_ids = {node.node_id for node in nodes if node.lifecycle_status is GraphLifecycleStatus.ACTIVE}
        degree = {node_id: 0 for node_id in node_ids}
        for link in active_links:
            if link.source_node_id in degree:
                degree[link.source_node_id] += 1
            if link.target_node_id in degree:
                degree[link.target_node_id] += 1

        reports: list[RequirementCoverage] = []
        for requirement_id in requirement_ids:
            requirement_node = graph_node_id(GraphNodeType.REQUIREMENT, requirement_id)
            implementation_links = tuple(
                link
                for link in active_links
                if link.relation_type is TraceRelationType.IMPLEMENTS
                and link.target_node_id == requirement_node
                and link.resolution_status is TraceResolutionStatus.RESOLVED
            )
            implementing_nodes = tuple(
                sorted({link.source_node_id for link in implementation_links})
            )
            verification_links = tuple(
                link
                for link in active_links
                if link.relation_type is TraceRelationType.VERIFIED_BY
                and link.source_node_id in implementing_nodes
                and link.resolution_status is TraceResolutionStatus.RESOLVED
            )
            verifying_nodes = tuple(
                sorted({link.target_node_id for link in verification_links})
            )
            unresolved = tuple(
                sorted(
                    link.link_id
                    for link in active_links
                    if requirement_node in (link.source_node_id, link.target_node_id)
                    and link.resolution_status is TraceResolutionStatus.UNRESOLVED
                )
            )
            if implementing_nodes and verifying_nodes:
                coverage_status = RequirementCoverageStatus.VERIFIED
            elif implementing_nodes:
                coverage_status = RequirementCoverageStatus.PARTIAL
            else:
                coverage_status = RequirementCoverageStatus.UNRESOLVED
            reports.append(
                RequirementCoverage(
                    requirement_id=requirement_id,
                    status=coverage_status,
                    implementing_node_ids=implementing_nodes,
                    verifying_node_ids=verifying_nodes,
                    unresolved_link_ids=unresolved,
                )
            )
        return TraceabilityCoverageReport(
            requirements=tuple(reports),
            verified_count=sum(item.status is RequirementCoverageStatus.VERIFIED for item in reports),
            partial_count=sum(item.status is RequirementCoverageStatus.PARTIAL for item in reports),
            unresolved_count=sum(item.status is RequirementCoverageStatus.UNRESOLVED for item in reports),
            diagnostics=TraceabilityDiagnostics(
                dangling_node_ids=tuple(sorted(node_id for node_id, count in degree.items() if count == 0)),
                unresolved_link_ids=tuple(
                    sorted(
                        link.link_id
                        for link in active_links
                        if link.resolution_status is TraceResolutionStatus.UNRESOLVED
                        or link.review_status is TraceReviewStatus.REVIEW_REQUIRED
                    )
                ),
                missing_evidence=missing_evidence,
            ),
        )

    @staticmethod
    def _node(
        node_type: GraphNodeType,
        source_identity: str,
        *,
        label: str | None = None,
        **attributes: str | int | bool | None,
    ) -> TraceGraphNode:
        return TraceGraphNode(
            node_id=graph_node_id(node_type, source_identity),
            node_type=node_type,
            source_identity=source_identity,
            label=label or source_identity,
            attributes=attributes,
        )

    @classmethod
    def _normalize_legacy_direction(
        cls,
        manifest: GenerationManifest,
        source_link: TraceabilityLink,
        source_type: GraphNodeType,
        target_type: GraphNodeType,
    ) -> tuple[
        GraphNodeType,
        str,
        GraphNodeType,
        str,
        str,
        TraceLinkProvenance,
    ]:
        """Normalize one unambiguous historical C2 link without changing its source."""

        is_legacy_reverse = (
            manifest.traceability.mapping_policy_version
            == LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION
            and source_link.provenance.mapping_rule_id == LEGACY_C2_DIRECTION_RULE
            and source_link.source_entity_type is TraceEntityType.REQUIREMENT
            and source_link.target_entity_type is TraceEntityType.UML_ELEMENT
            and source_link.relation_type is TraceRelationType.DERIVED_FROM
        )
        if not is_legacy_reverse:
            return (
                source_type,
                source_link.source_id,
                target_type,
                source_link.target_id,
                source_link.link_id,
                source_link.provenance,
            )

        matching_anchors = tuple(
            anchor
            for anchor in manifest.source.requirement_uml_anchors
            if anchor.requirement_id == source_link.source_id
            and anchor.uml_id == source_link.target_id
            and anchor.anchor_id in source_link.provenance.evidence_refs
        )
        if len(matching_anchors) != 1:
            cls._fail(
                "LEGACY_TRACE_DIRECTION_MIGRATION_REQUIRED",
                source_link.link_id,
                (
                    "The historical requirement-to-UML link cannot be normalized "
                    "unambiguously from an exact C2 anchor; regenerate or migrate it."
                ),
            )

        normalized_source_type = GraphNodeType.UML_ELEMENT
        normalized_target_type = GraphNodeType.REQUIREMENT
        normalized_source_id = source_link.target_id
        normalized_target_id = source_link.source_id
        normalized_link_id = cls._link_id(
            graph_node_id(normalized_source_type, normalized_source_id),
            source_link.relation_type,
            graph_node_id(normalized_target_type, normalized_target_id),
            LEGACY_C2_NORMALIZATION_RULE,
        )
        provenance = TraceLinkProvenance(
            evidence_kind=source_link.provenance.evidence_kind,
            mapping_rule_id=LEGACY_C2_NORMALIZATION_RULE,
            evidence_refs=tuple(
                dict.fromkeys(
                    (*source_link.provenance.evidence_refs, source_link.link_id)
                )
            ),
            details=(
                "Deterministically normalized the historical "
                f"{LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION} edge to the "
                "downstream-to-upstream convention. Original rule: "
                f"{source_link.provenance.mapping_rule_id}. Original details: "
                f"{source_link.provenance.details}"
            ),
        )
        return (
            normalized_source_type,
            normalized_source_id,
            normalized_target_type,
            normalized_target_id,
            normalized_link_id,
            provenance,
        )

    @staticmethod
    def _link_id(
        source_node_id: str,
        relation: TraceRelationType,
        target_node_id: str,
        rule: str,
    ) -> str:
        payload = "|".join((source_node_id, relation.value, target_node_id, rule))
        return "GRAPH-LINK-" + sha256(payload.encode("utf-8")).hexdigest()[:16].upper()

    @staticmethod
    def _fail(code: str, field: str, message: str) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status.HTTP_409_CONFLICT,
        )
