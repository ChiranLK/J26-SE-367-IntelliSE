"""Deterministic queries and RTM export over verified traceability graphs."""

from collections import defaultdict

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest, TraceRelationType, TraceResolutionStatus
from intelise_c3.domain.traceability import (
    GraphChangeReport,
    GraphLifecycleStatus,
    GraphNodeType,
    ImpactSet,
    RequirementTraceChain,
    ResearchGroundTruth,
    RtmExport,
    RtmRow,
    TraceGraphBuild,
    TraceGraphLink,
    TraceGraphNode,
    TraceabilityDiagnostic,
    TraceabilityMetricsReport,
)
from intelise_c3.traceability.builder import graph_node_id
from intelise_c3.traceability.impact import requirement_impact_set


def chain(snapshot: TraceGraphBuild, requirement_id: str) -> RequirementTraceChain:
    """Trace a requirement through UML, Code, API, Database, and Test seam nodes."""
    req_id = requirement_id.removeprefix("REQUIREMENT:")
    target_node_id = graph_node_id(GraphNodeType.REQUIREMENT, req_id)

    nodes_by_id = {
        node.node_id: node
        for node in snapshot.nodes
        if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
    }
    if target_node_id not in nodes_by_id:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="UNKNOWN_REQUIREMENT_ID",
                    field="requirement_id",
                    message=f"Requirement '{req_id}' is not an active graph node.",
                )
            ],
            status_code=status.HTTP_404_NOT_FOUND,
        )

    req_node = nodes_by_id[target_node_id]
    active_links = [
        link
        for link in snapshot.links
        if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
    ]

    by_target: dict[str, list[TraceGraphLink]] = defaultdict(list)
    by_source: dict[str, list[TraceGraphLink]] = defaultdict(list)
    for link in active_links:
        by_target[link.target_node_id].append(link)
        by_source[link.source_node_id].append(link)

    # 1. Design / UML elements
    uml_nodes: dict[str, TraceGraphNode] = {}
    chain_links: dict[str, TraceGraphLink] = {}

    for link in by_target[target_node_id]:
        source = nodes_by_id.get(link.source_node_id)
        if source and source.node_type in (
            GraphNodeType.UML_ELEMENT,
            GraphNodeType.DESIGN_ANCHOR,
        ):
            uml_nodes[source.node_id] = source
            chain_links[link.link_id] = link
            if source.node_type is GraphNodeType.DESIGN_ANCHOR:
                for next_link in by_source[source.node_id]:
                    target = nodes_by_id.get(next_link.target_node_id)
                    if target and target.node_type is GraphNodeType.UML_ELEMENT:
                        uml_nodes[target.node_id] = target
                        chain_links[next_link.link_id] = next_link

    # Also handle reverse UML_ELEMENT links if present
    for link in by_source[target_node_id]:
        target = nodes_by_id.get(link.target_node_id)
        if target and target.node_type in (
            GraphNodeType.UML_ELEMENT,
            GraphNodeType.DESIGN_ANCHOR,
        ):
            uml_nodes[target.node_id] = target
            chain_links[link.link_id] = link

    # 2. Code modules
    code_nodes: dict[str, TraceGraphNode] = {}
    for link in by_target[target_node_id]:
        source = nodes_by_id.get(link.source_node_id)
        if (
            source
            and source.node_type is GraphNodeType.CODE_MODULE
            and link.relation_type is TraceRelationType.IMPLEMENTS
        ):
            code_nodes[source.node_id] = source
            chain_links[link.link_id] = link

    for uml_id in list(uml_nodes.keys()):
        for link in by_target[uml_id]:
            source = nodes_by_id.get(link.source_node_id)
            if (
                source
                and source.node_type is GraphNodeType.CODE_MODULE
                and link.relation_type is TraceRelationType.DERIVED_FROM
            ):
                code_nodes[source.node_id] = source
                chain_links[link.link_id] = link

    # 3. Downstream API, Database, and Test seam nodes from code modules
    api_nodes: dict[str, TraceGraphNode] = {}
    db_nodes: dict[str, TraceGraphNode] = {}
    test_nodes: dict[str, TraceGraphNode] = {}

    for code_id in code_nodes:
        for link in by_source[code_id]:
            target = nodes_by_id.get(link.target_node_id)
            if not target:
                continue
            if target.node_type is GraphNodeType.API_OPERATION:
                api_nodes[target.node_id] = target
                chain_links[link.link_id] = link
            elif target.node_type is GraphNodeType.DATABASE_ARTIFACT:
                db_nodes[target.node_id] = target
                chain_links[link.link_id] = link
            elif target.node_type is GraphNodeType.TEST_HOOK or (
                target.node_type is GraphNodeType.CODE_MODULE
                and link.relation_type is TraceRelationType.VERIFIED_BY
            ):
                test_nodes[target.node_id] = target
                chain_links[link.link_id] = link

    return RequirementTraceChain(
        requirement_id=req_id,
        requirement_node_id=target_node_id,
        label=req_node.label,
        uml_nodes=tuple(sorted(uml_nodes.values(), key=lambda n: n.node_id)),
        code_modules=tuple(sorted(code_nodes.values(), key=lambda n: n.node_id)),
        api_operations=tuple(sorted(api_nodes.values(), key=lambda n: n.node_id)),
        database_artifacts=tuple(sorted(db_nodes.values(), key=lambda n: n.node_id)),
        test_hooks=tuple(sorted(test_nodes.values(), key=lambda n: n.node_id)),
        links=tuple(sorted(chain_links.values(), key=lambda l: l.link_id)),
    )


def impact_set(
    snapshot: TraceGraphBuild,
    requirement_id: str,
    manifest: GenerationManifest | None = None,
) -> ImpactSet:
    """Delegate to the existing scoped-impact graph policy."""
    if manifest is None:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="VERIFIED_MANIFEST_REQUIRED",
                    field="manifest",
                    message="Impact-set queries require the graph's verified manifest.",
                )
            ],
            status_code=status.HTTP_409_CONFLICT,
        )
    return requirement_impact_set(snapshot, manifest, requirement_id)


def requirements_for_module(
    snapshot: TraceGraphBuild,
    module_identifier: str,
    manifest: GenerationManifest | None = None,
) -> tuple[str, ...]:
    """Reverse lookup: return all requirement IDs implemented or linked by a module."""
    nodes_by_id = {
        node.node_id: node
        for node in snapshot.nodes
        if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
    }

    # Find the target CODE_MODULE node
    target_node: TraceGraphNode | None = None
    if module_identifier in nodes_by_id:
        target_node = nodes_by_id[module_identifier]
    elif graph_node_id(GraphNodeType.CODE_MODULE, module_identifier) in nodes_by_id:
        target_node = nodes_by_id[graph_node_id(GraphNodeType.CODE_MODULE, module_identifier)]
    else:
        for node in nodes_by_id.values():
            if node.node_type is not GraphNodeType.CODE_MODULE:
                continue
            if (
                node.source_identity == module_identifier
                or node.attributes.get("relative_path") == module_identifier
                or node.attributes.get("module_identity") == module_identifier
                or node.label == module_identifier
            ):
                target_node = node
                break

    if target_node is None:
        return ()

    active_links = [
        link
        for link in snapshot.links
        if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
    ]

    matched_requirements: set[str] = set()

    for link in active_links:
        # Direct IMPLEMENTS link: CODE_MODULE -> REQUIREMENT
        if (
            link.source_node_id == target_node.node_id
            and link.target_node_id.startswith("REQUIREMENT:")
            and link.relation_type is TraceRelationType.IMPLEMENTS
        ):
            matched_requirements.add(link.target_node_id.removeprefix("REQUIREMENT:"))

        # Reverse link if applicable
        if (
            link.target_node_id == target_node.node_id
            and link.source_node_id.startswith("REQUIREMENT:")
            and link.relation_type is TraceRelationType.IMPLEMENTS
        ):
            matched_requirements.add(link.source_node_id.removeprefix("REQUIREMENT:"))

    # Transitive links: CODE_MODULE -> DESIGN_ANCHOR / UML_ELEMENT -> REQUIREMENT
    anchors_or_umls: set[str] = set()
    for link in active_links:
        if (
            link.source_node_id == target_node.node_id
            and link.relation_type is TraceRelationType.DERIVED_FROM
        ):
            anchors_or_umls.add(link.target_node_id)

    for link in active_links:
        if (
            link.source_node_id in anchors_or_umls
            and link.target_node_id.startswith("REQUIREMENT:")
        ):
            matched_requirements.add(link.target_node_id.removeprefix("REQUIREMENT:"))

    # Cross-check manifest if supplied
    if manifest is not None:
        file_id = target_node.source_identity
        for record in manifest.files:
            if record.file_id == file_id:
                for req in record.requirement_ids:
                    matched_requirements.add(req)

    return tuple(sorted(matched_requirements))


def detect_orphans_and_gaps(
    snapshot: TraceGraphBuild,
) -> dict[str, tuple[str, ...]]:
    """Detect downstream nodes with no path to a requirement and requirement coverage gaps."""
    active_nodes = {
        node.node_id: node
        for node in snapshot.nodes
        if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
    }
    active_links = [
        link
        for link in snapshot.links
        if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
    ]

    # Build bidirectional adjacency among active nodes
    adj: dict[str, set[str]] = defaultdict(set)
    for link in active_links:
        if link.source_node_id in active_nodes and link.target_node_id in active_nodes:
            adj[link.source_node_id].add(link.target_node_id)
            adj[link.target_node_id].add(link.source_node_id)

    # Breadth-first search from all REQUIREMENT nodes
    req_nodes = {
        node_id
        for node_id, node in active_nodes.items()
        if node.node_type is GraphNodeType.REQUIREMENT
    }
    visited = set(req_nodes)
    queue = list(req_nodes)
    while queue:
        curr = queue.pop(0)
        for neighbor in adj[curr]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    scaffold_types = {"CONFIGURATION", "DOCUMENTATION"}
    scaffold_paths = {"frontend/index.html", "frontend/src/main.jsx", "index.html", "src/main.jsx"}

    orphan_node_ids = tuple(
        sorted(
            node_id
            for node_id, node in active_nodes.items()
            if node_id not in visited
            and (
                node.node_type in (
                    GraphNodeType.API_OPERATION,
                    GraphNodeType.DATABASE_ARTIFACT,
                    GraphNodeType.TEST_HOOK,
                )
                or (
                    node.node_type is GraphNodeType.CODE_MODULE
                    and node.attributes.get("artifact_type") not in scaffold_types
                    and node.attributes.get("relative_path") not in scaffold_paths
                )
            )
        )
    )

    # Coverage gaps: Requirements that have no CODE_MODULE reachable
    coverage_gaps: list[str] = []
    for req_id in snapshot.source.requirement_ids:
        r_node = graph_node_id(GraphNodeType.REQUIREMENT, req_id)
        if r_node not in active_nodes:
            coverage_gaps.append(req_id)
            continue

        # Check reachability to any CODE_MODULE
        sub_visited = {r_node}
        sub_queue = [r_node]
        has_code = False
        while sub_queue:
            curr = sub_queue.pop(0)
            node = active_nodes.get(curr)
            if node and node.node_type is GraphNodeType.CODE_MODULE:
                has_code = True
                break
            for neighbor in adj[curr]:
                if neighbor not in sub_visited:
                    sub_visited.add(neighbor)
                    sub_queue.append(neighbor)
        if not has_code:
            coverage_gaps.append(req_id)

    return {
        "orphan_node_ids": orphan_node_ids,
        "coverage_gaps": tuple(sorted(coverage_gaps)),
    }


def validate_no_orphans(snapshot: TraceGraphBuild) -> None:
    """Raise ApplicationError if any downstream orphan node is detected."""
    results = detect_orphans_and_gaps(snapshot)
    orphans = results["orphan_node_ids"]
    if orphans:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="ORPHAN_GRAPH_NODE",
                    field="nodes",
                    message=(
                        f"Traceability graph contains {len(orphans)} orphan downstream "
                        f"node(s) with no path back to a requirement: {', '.join(orphans[:5])}"
                    ),
                )
            ],
            status_code=status.HTTP_409_CONFLICT,
        )


def validate_upstream_anchors(manifest: GenerationManifest) -> None:
    """Verify that every requirement has at least one valid REQ->UML anchor."""
    anchored_reqs = {a.requirement_id for a in manifest.source.requirement_uml_anchors}
    missing = [req for req in manifest.source.requirement_ids if req not in anchored_reqs]
    if missing:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="MISSING_REQ_UML_ANCHOR",
                    field="requirement_uml_anchors",
                    message=f"Requirements missing REQ->UML anchor: {', '.join(missing)}",
                )
            ],
            status_code=status.HTTP_409_CONFLICT,
        )


def export_rtm(snapshot: TraceGraphBuild) -> RtmExport:
    """Generate Requirements Traceability Matrix as structured JSON and Markdown table."""
    rows: list[RtmRow] = []

    for req_id in snapshot.source.requirement_ids:
        req_chain = chain(snapshot, req_id)
        uml_labels = tuple(sorted(n.label for n in req_chain.uml_nodes))
        code_labels = tuple(
            sorted(
                str(n.attributes.get("relative_path") or n.label)
                for n in req_chain.code_modules
            )
        )
        api_labels = tuple(
            sorted(
                f"{n.attributes.get('method', '')} {n.attributes.get('route_path', '')}".strip()
                or n.label
                for n in req_chain.api_operations
            )
        )
        db_labels = tuple(
            sorted(
                str(n.attributes.get("name") or n.label)
                for n in req_chain.database_artifacts
            )
        )
        test_labels = tuple(
            sorted(
                str(n.attributes.get("module_path") or n.label)
                for n in req_chain.test_hooks
            )
        )

        rows.append(
            RtmRow(
                requirement_id=req_id,
                requirement_label=req_chain.label,
                uml_elements=uml_labels,
                code_modules=code_labels,
                api_operations=api_labels,
                database_entities=db_labels,
                test_hooks=test_labels,
            )
        )

    # Build Markdown table
    md_lines = [
        "| Requirement | UML Elements | Code Modules | API Operations | Database Entities | Test Hooks |",
        "|:---|:---|:---|:---|:---|:---|",
    ]
    for row in rows:
        uml_str = "<br>".join(row.uml_elements) or "—"
        code_str = "<br>".join(row.code_modules) or "—"
        api_str = "<br>".join(row.api_operations) or "—"
        db_str = "<br>".join(row.database_entities) or "—"
        test_str = "<br>".join(row.test_hooks) or "—"
        md_lines.append(
            f"| **{row.requirement_id}**<br>_{row.requirement_label}_ | {uml_str} | {code_str} | {api_str} | {db_str} | {test_str} |"
        )

    table_markdown = "\n".join(md_lines)
    graph_version = getattr(snapshot, "graph_version", 1)

    return RtmExport(
        graph_id=snapshot.graph_id,
        graph_version=graph_version,
        rows=tuple(rows),
        table_markdown=table_markdown,
    )


def compute_metrics_report(
    snapshot: TraceGraphBuild,
    oracle: ResearchGroundTruth | None = None,
    change_report: GraphChangeReport | None = None,
) -> TraceabilityMetricsReport:
    """Compute living traceability metrics: coverage, orphan rate, precision/recall/F1, and preservation."""
    active_nodes = [
        node
        for node in snapshot.nodes
        if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
    ]
    orphans = detect_orphans_and_gaps(snapshot)
    orphan_ids = orphans["orphan_node_ids"]
    coverage_gaps = orphans["coverage_gaps"]
    total_reqs = len(snapshot.source.requirement_ids)
    covered_reqs = total_reqs - len(coverage_gaps)
    coverage_rate = (covered_reqs / total_reqs) if total_reqs > 0 else 0.0
    orphan_rate = (len(orphan_ids) / len(active_nodes)) if active_nodes else 0.0

    tp = fp = fn = 0
    prec = rec = f1 = 0.0
    oracle_id = None
    oracle_count = 0
    honesty_note = ""

    if oracle is not None:
        oracle_id = oracle.dataset_id
        oracle_count = len(oracle.expected_links)
        scope = set(oracle.in_scope_node_ids)
        expected = {
            (item.source_node_id, item.relation_type.value, item.target_node_id)
            for item in oracle.expected_links
        }
        predicted = {
            (link.source_node_id, link.relation_type.value, link.target_node_id)
            for link in snapshot.links
            if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
            and link.resolution_status is TraceResolutionStatus.RESOLVED
            and link.source_node_id in scope
            and link.target_node_id in scope
        }
        tp = len(predicted & expected)
        fp = len(predicted - expected)
        fn = len(expected - predicted)
        prec = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        honesty_note = (
            f"Evaluated against hand-labelled oracle '{oracle.dataset_id}' containing "
            f"{oracle_count} expected links across {len(scope)} in-scope nodes. "
            "Metrics are calculated directly without benchmark claims or inflation."
        )

    preservation_rate = None
    if change_report is not None:
        total_unchanged_eval = len(change_report.preserved_link_ids) + len(change_report.retired_link_ids)
        preservation_rate = (
            (len(change_report.preserved_link_ids) / total_unchanged_eval)
            if total_unchanged_eval > 0
            else 1.0
        )

    diagnostics: list[TraceabilityDiagnostic] = []
    if orphan_ids:
        diagnostics.append(
            TraceabilityDiagnostic(
                code="ORPHAN_DOWNSTREAM_NODE",
                affected_ids=orphan_ids,
                message=(
                    f"{len(orphan_ids)} active downstream node(s) have no trace path "
                    "to an active requirement. Existing graph flows remain available, "
                    "but these nodes require research review."
                ),
            )
        )
    if coverage_gaps:
        diagnostics.append(
            TraceabilityDiagnostic(
                code="REQUIREMENT_COVERAGE_GAP",
                affected_ids=coverage_gaps,
                message=(
                    f"{len(coverage_gaps)} source requirement(s) have no downstream "
                    "code coverage path and require research review."
                ),
            )
        )

    return TraceabilityMetricsReport(
        graph_id=snapshot.graph_id,
        graph_version=getattr(snapshot, "graph_version", 1),
        total_requirements=total_reqs,
        covered_requirements=covered_reqs,
        coverage_rate=coverage_rate,
        coverage_gaps=coverage_gaps,
        total_active_nodes=len(active_nodes),
        orphan_node_count=len(orphan_ids),
        orphan_rate=orphan_rate,
        orphan_node_ids=orphan_ids,
        diagnostics=tuple(diagnostics),
        oracle_dataset_id=oracle_id,
        oracle_link_count=oracle_count,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=prec,
        recall=rec,
        f1_score=f1,
        preservation_rate=preservation_rate,
        oracle_honesty_note=honesty_note,
    )
