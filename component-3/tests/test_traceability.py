"""Acceptance tests for persistent living requirement traceability."""

import asyncio
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.traceability import (
    GraphCreateRequest,
    GraphUpdateRequest,
)
from intelise_c3.core.errors import ApplicationError
from intelise_c3.core.config import get_settings
from intelise_c3.domain.generation import (
    ArtifactOrigin,
    GenerationManifest,
    GeneratedArtifactType,
    GeneratedFileRecord,
    TraceEntityType,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    GraphNodeType,
    GroundTruthLink,
    ImpactSet,
    RequirementCoverageStatus,
    RequirementTraceChain,
    ResearchGroundTruth,
    RtmExport,
    SourceVersionTransitionEvidence,
    TraceabilityMetricsReport,
)
from intelise_c3.traceability.queries import (
    chain,
    compute_metrics_report,
    detect_orphans_and_gaps,
    export_rtm,
    impact_set,
    requirements_for_module,
    validate_no_orphans,
    validate_upstream_anchors,
)
from intelise_c3.generation.evidence import compute_evidence_digest
from intelise_c3.main import create_app
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.semantics import (
    CURRENT_TRACEABILITY_MAPPING_POLICY_VERSION,
    LEGACY_C2_DIRECTION_RULE,
    LEGACY_C2_NORMALIZATION_RULE,
    LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION,
    is_permitted_relation,
)
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService


def _generated_run(workspace_root: Path):
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    result = asyncio.run(
        CodeGenerationService(workspace_root, None).generate(request)
    )
    return result, workspace_root / Path(result.workspace_relative_path)


def _service(workspace_root: Path, database_path: Path) -> TraceabilityService:
    return TraceabilityService(
        verifier=ManifestVerificationService(workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(database_path),
    )


def _create(service: TraceabilityService, result):
    return service.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )


def _with_recomputed_evidence(manifest, *, files=None, traceability=None, source=None):
    files = tuple(files if files is not None else manifest.files)
    aggregate = sha256()
    for record in sorted(files, key=lambda item: item.relative_path):
        aggregate.update(record.relative_path.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(record.sha256.encode("ascii"))
        aggregate.update(b"\n")
    artifact_digest = aggregate.hexdigest()
    evidence = manifest.run_evidence
    evidence_digest = compute_evidence_digest(
        generation_run_id=manifest.generation_run_id,
        input_hashes=evidence.input_hashes,
        prompt_template_version=evidence.prompt_template_version,
        generator_version=evidence.generator_version,
        template_set_version=evidence.template_set_version,
        llm_inference=manifest.llm_inference,
        artifact_digest_sha256=artifact_digest,
        rag_evidence=evidence.rag,
    )
    return manifest.model_copy(
        update={
            "files": files,
            "traceability": traceability or manifest.traceability,
            "source": source or manifest.source,
            "artifact_digest_sha256": artifact_digest,
            "run_evidence": evidence.model_copy(
                update={"evidence_digest_sha256": evidence_digest}
            ),
        }
    )


def _write_manifest(workspace: Path, manifest) -> None:
    (workspace / "artifact-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_valid_graph_construction_preserves_typed_source_evidence(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    snapshot = _create(_service(root, tmp_path / "graphs.sqlite3"), result)

    node_types = {node.node_type for node in snapshot.nodes}
    assert node_types == set(GraphNodeType)
    assert "REQUIREMENT:REQ-TASK-001" in {node.node_id for node in snapshot.nodes}
    assert "UML_ELEMENT:UML-TASK-CLASS-001" in {
        node.node_id for node in snapshot.nodes
    }
    assert "DESIGN_ANCHOR:ANCHOR-TASK-001" in {
        node.node_id for node in snapshot.nodes
    }
    assert snapshot.generation_run_id == result.manifest.generation_run_id
    assert snapshot.artifact_digest_sha256 == result.manifest.artifact_digest_sha256
    assert snapshot.graph_version == 1
    assert any(
        link.resolution_status is TraceResolutionStatus.UNRESOLVED
        and link.review_status is TraceReviewStatus.REVIEW_REQUIRED
        for link in snapshot.links
    )


def test_corrupted_manifest_and_file_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    corrupted_evidence = result.manifest.model_copy(
        update={
            "run_evidence": result.manifest.run_evidence.model_copy(
                update={"evidence_digest_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ApplicationError) as evidence_error:
        service.create(
            GraphCreateRequest(
                manifest=corrupted_evidence,
                workspace_relative_path=result.workspace_relative_path,
            )
        )
    assert evidence_error.value.errors[0].code == "INVALID_EVIDENCE_DIGEST"

    mismatched_payload = result.manifest.model_copy(
        update={"trust_boundary": "altered manifest payload"}
    )
    with pytest.raises(ApplicationError) as manifest_error:
        service.create(
            GraphCreateRequest(
                manifest=mismatched_payload,
                workspace_relative_path=result.workspace_relative_path,
            )
        )
    assert manifest_error.value.errors[0].code == "MANIFEST_PAYLOAD_MISMATCH"

    (workspace / "README.md").write_text("corrupted\n", encoding="utf-8")
    with pytest.raises(ApplicationError) as file_error:
        _create(service, result)
    assert file_error.value.errors[0].code == "ARTIFACT_HASH_MISMATCH"


def test_identical_manifest_build_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    verifier = ManifestVerificationService(root)
    verifier.verify(result.manifest, result.workspace_relative_path)
    builder = TraceabilityGraphBuilder()

    first = builder.build(result.manifest)
    second = builder.build(result.manifest)

    assert first == second
    assert first.graph_content_digest_sha256 == second.graph_content_digest_sha256


def test_creation_run_metadata_is_version_aware(tmp_path: Path) -> None:
    result, _ = _generated_run(tmp_path / "workspaces")
    build = TraceabilityGraphBuilder().build(result.manifest)

    assert all(
        node.created_in_generation_run_id == result.manifest.generation_run_id
        for node in build.nodes
    )
    assert all(
        link.created_in_generation_run_id == result.manifest.generation_run_id
        for link in build.links
    )

    historical_payload = build.model_dump(mode="json")
    for node in historical_payload["nodes"]:
        node.pop("created_in_generation_run_id", None)
    for link in historical_payload["links"]:
        link.pop("created_in_generation_run_id", None)
    historical = type(build).model_validate(historical_payload)
    assert all(node.created_in_generation_run_id is None for node in historical.nodes)
    assert all(link.created_in_generation_run_id is None for link in historical.links)


def test_current_generator_emits_only_valid_relation_directions(tmp_path: Path) -> None:
    result, _ = _generated_run(tmp_path / "workspaces")
    assert (
        result.manifest.traceability.mapping_policy_version
        == CURRENT_TRACEABILITY_MAPPING_POLICY_VERSION
    )
    build = TraceabilityGraphBuilder().build(result.manifest)
    nodes = {node.node_id: node for node in build.nodes}

    assert build.relation_direction_policy_version == "C3_GRAPH_RELATION_DIRECTION_V1"
    assert all(
        is_permitted_relation(
            link.relation_type,
            nodes[link.source_node_id].node_type,
            nodes[link.target_node_id].node_type,
        )
        for link in build.links
    )
    assert any(
        link.relation_type is TraceRelationType.DERIVED_FROM
        and nodes[link.source_node_id].node_type is GraphNodeType.UML_ELEMENT
        and nodes[link.target_node_id].node_type is GraphNodeType.REQUIREMENT
        for link in build.links
    )
    assert not any(
        link.relation_type is TraceRelationType.DERIVED_FROM
        and nodes[link.source_node_id].node_type is GraphNodeType.REQUIREMENT
        and nodes[link.target_node_id].node_type is GraphNodeType.UML_ELEMENT
        for link in build.links
    )


@pytest.mark.parametrize(
    ("relation", "source_type", "target_type"),
    (
        (TraceRelationType.DERIVED_FROM, GraphNodeType.REQUIREMENT, GraphNodeType.UML_ELEMENT),
        (TraceRelationType.IMPLEMENTS, GraphNodeType.REQUIREMENT, GraphNodeType.CODE_MODULE),
        (TraceRelationType.EXPOSES, GraphNodeType.API_OPERATION, GraphNodeType.CODE_MODULE),
        (TraceRelationType.PERSISTS_TO, GraphNodeType.DATABASE_ARTIFACT, GraphNodeType.CODE_MODULE),
        (TraceRelationType.VERIFIED_BY, GraphNodeType.TEST_HOOK, GraphNodeType.CODE_MODULE),
        (TraceRelationType.DEFINES, GraphNodeType.DATABASE_ARTIFACT, GraphNodeType.CODE_MODULE),
    ),
)
def test_relation_policy_rejects_invalid_endpoint_pairs(
    relation: TraceRelationType,
    source_type: GraphNodeType,
    target_type: GraphNodeType,
) -> None:
    assert not is_permitted_relation(relation, source_type, target_type)


def test_graph_builder_rejects_invalid_relation_direction(tmp_path: Path) -> None:
    result, _ = _generated_run(tmp_path / "workspaces")
    links = list(result.manifest.traceability.links)
    index = next(
        index
        for index, link in enumerate(links)
        if link.relation_type is TraceRelationType.EXPOSES
    )
    links[index] = links[index].model_copy(
        update={
            "source_entity_type": TraceEntityType.REQUIREMENT,
            "source_id": result.manifest.source.requirement_ids[0],
        }
    )
    invalid_manifest = result.manifest.model_copy(
        update={
            "traceability": result.manifest.traceability.model_copy(
                update={"links": tuple(links)}
            )
        }
    )

    with pytest.raises(ApplicationError) as captured:
        TraceabilityGraphBuilder().build(invalid_manifest)

    assert captured.value.errors[0].code == "INVALID_TRACE_RELATION_DIRECTION"


def test_legacy_c2_direction_is_normalized_only_with_exact_anchor_evidence(
    tmp_path: Path,
) -> None:
    result, _ = _generated_run(tmp_path / "workspaces")
    links = list(result.manifest.traceability.links)
    index = next(
        index
        for index, link in enumerate(links)
        if link.provenance.mapping_rule_id == "C2_UML_DERIVED_FROM_REQUIREMENT_V2"
    )
    current = links[index]
    links[index] = current.model_copy(
        update={
            "source_entity_type": TraceEntityType.REQUIREMENT,
            "source_id": current.target_id,
            "target_entity_type": TraceEntityType.UML_ELEMENT,
            "target_id": current.source_id,
            "provenance": current.provenance.model_copy(
                update={"mapping_rule_id": LEGACY_C2_DIRECTION_RULE}
            ),
        }
    )
    legacy_manifest = result.manifest.model_copy(
        update={
            "traceability": result.manifest.traceability.model_copy(
                update={
                    "mapping_policy_version": LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION,
                    "links": tuple(links),
                }
            )
        }
    )

    first = TraceabilityGraphBuilder().build(legacy_manifest)
    second = TraceabilityGraphBuilder().build(legacy_manifest)
    normalized = next(
        link
        for link in first.links
        if link.provenance.mapping_rule_id == LEGACY_C2_NORMALIZATION_RULE
    )

    assert normalized.source_node_id == f"UML_ELEMENT:{current.source_id}"
    assert normalized.target_node_id == f"REQUIREMENT:{current.target_id}"
    assert normalized.resolution_status is current.resolution_status
    assert normalized.review_status is current.review_status
    assert current.link_id in normalized.provenance.evidence_refs
    assert first.graph_content_digest_sha256 == second.graph_content_digest_sha256

    bad_link = links[index].model_copy(
        update={
            "provenance": links[index].provenance.model_copy(
                update={"evidence_refs": ("UNKNOWN-ANCHOR",)}
            )
        }
    )
    bad_links = tuple(
        bad_link if position == index else link
        for position, link in enumerate(links)
    )
    ambiguous_manifest = legacy_manifest.model_copy(
        update={
            "traceability": legacy_manifest.traceability.model_copy(
                update={"links": bad_links}
            )
        }
    )
    with pytest.raises(ApplicationError) as captured:
        TraceabilityGraphBuilder().build(ambiguous_manifest)
    assert captured.value.errors[0].code == "LEGACY_TRACE_DIRECTION_MIGRATION_REQUIRED"


def test_existing_verified_task_management_v1_manifest_is_normalized_if_available() -> None:
    workspace_root = Path(__file__).parents[1] / "generated-workspaces"
    if not workspace_root.exists():
        pytest.skip("No local historical Task Management workspace is available.")

    for manifest_path in sorted(workspace_root.rglob("artifact-manifest.json")):
        try:
            manifest = GenerationManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        if (
            manifest.traceability.mapping_policy_version
            != LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION
        ):
            continue
        relative_workspace = manifest_path.parent.relative_to(workspace_root).as_posix()
        try:
            ManifestVerificationService(workspace_root).verify(
                manifest,
                relative_workspace,
            )
        except ApplicationError:
            continue
        build = TraceabilityGraphBuilder().build(manifest)
        assert any(
            link.provenance.mapping_rule_id == LEGACY_C2_NORMALIZATION_RULE
            for link in build.links
        )
        assert not any(
            link.relation_type is TraceRelationType.DERIVED_FROM
            and link.source_node_id.startswith("REQUIREMENT:")
            and link.target_node_id.startswith("UML_ELEMENT:")
            for link in build.links
        )
        return

    pytest.skip("No intact local Task Management v1 manifest was available.")


def test_unresolved_link_status_and_provenance_are_preserved(tmp_path: Path) -> None:
    result, _ = _generated_run(tmp_path / "workspaces")
    source_link = next(
        link
        for link in result.manifest.traceability.links
        if link.relation_type is TraceRelationType.PERSISTS_TO
    )
    build = TraceabilityGraphBuilder().build(result.manifest)
    graph_link = next(link for link in build.links if link.link_id == source_link.link_id)

    assert graph_link.resolution_status is TraceResolutionStatus.UNRESOLVED
    assert graph_link.review_status is TraceReviewStatus.REVIEW_REQUIRED
    assert graph_link.provenance == source_link.provenance


def test_sqlite_snapshots_are_append_only_and_retrievable(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")

    first = _create(service, result)
    second = _create(service, result)

    assert first.graph_version == 1
    assert second.graph_version == 2
    assert first.snapshot_id != second.snapshot_id
    assert first.graph_content_digest_sha256 == second.graph_content_digest_sha256
    assert service.retrieve(first.graph_id, 1) == first
    assert service.latest(first.graph_id) == second


def test_living_update_classifies_artifacts_and_retires_stale_links(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    old_result, _ = _generated_run(root)
    new_result, new_workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    old_snapshot = _create(service, old_result)

    records = {record.relative_path: record for record in new_result.manifest.files}
    readme_path = new_workspace / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8") + "Traceability update.\n",
        encoding="utf-8",
        newline="\n",
    )
    readme_bytes = readme_path.read_bytes()
    records["README.md"] = records["README.md"].model_copy(
        update={
            "sha256": sha256(readme_bytes).hexdigest(),
            "size_bytes": len(readme_bytes),
        }
    )
    removed = records.pop("frontend/src/components/TaskForm.jsx")
    (new_workspace / removed.relative_path).unlink()
    added_path = new_workspace / "docs/traceability-note.txt"
    added_path.parent.mkdir(parents=True)
    added_path.write_text("Research traceability note.\n", encoding="utf-8", newline="\n")
    added_bytes = added_path.read_bytes()
    added_record = GeneratedFileRecord(
        file_id="FILE-TRACEABILITY-NOTE",
        relative_path="docs/traceability-note.txt",
        module_identity="traceability-note",
        artifact_type=GeneratedArtifactType.DOCUMENTATION,
        origin=ArtifactOrigin.TEMPLATE,
        sha256=sha256(added_bytes).hexdigest(),
        size_bytes=len(added_bytes),
    )
    records[added_record.relative_path] = added_record
    retained_links = tuple(
        link
        for link in new_result.manifest.traceability.links
        if removed.file_id not in (link.source_id, link.target_id)
    )
    traceability = new_result.manifest.traceability.model_copy(
        update={"links": retained_links}
    )
    updated_manifest = _with_recomputed_evidence(
        new_result.manifest,
        files=tuple(records.values()),
        traceability=traceability,
    )
    _write_manifest(new_workspace, updated_manifest)

    update = service.update(
        old_snapshot.graph_id,
        GraphUpdateRequest(
            manifest=updated_manifest,
            workspace_relative_path=new_result.workspace_relative_path,
            base_graph_version=1,
        ),
    )

    changes = update.change_report.artifacts
    assert changes.added == (added_record.file_id,)
    assert changes.removed == (removed.file_id,)
    assert changes.changed == (records["README.md"].file_id,)
    assert len(changes.unchanged) == 16
    assert update.change_report.preserved_link_ids
    assert update.change_report.retired_link_ids
    assert any(
        link.lifecycle_status is GraphLifecycleStatus.RETIRED
        and link.retired_in_graph_version == 2
        for link in update.snapshot.links
    )
    assert service.retrieve(old_snapshot.graph_id, 1) == old_snapshot


def test_source_identity_change_requires_explicit_research_approval(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    old_result, _ = _generated_run(root)
    new_result, new_workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    old = _create(service, old_result)
    changed_source = new_result.manifest.source.model_copy(
        update={"srs_version": "SRS-TASK-2.0"}
    )
    changed_manifest = _with_recomputed_evidence(
        new_result.manifest,
        source=changed_source,
    )
    _write_manifest(new_workspace, changed_manifest)
    request = GraphUpdateRequest(
        manifest=changed_manifest,
        workspace_relative_path=new_result.workspace_relative_path,
        base_graph_version=1,
    )

    with pytest.raises(ApplicationError) as captured:
        service.update(old.graph_id, request)
    assert captured.value.errors[0].code == "SOURCE_VERSION_APPROVAL_REQUIRED"

    approved = request.model_copy(
        update={
            "source_transition_evidence": SourceVersionTransitionEvidence(
                approval_reference="SIMULATED-RESEARCH-SOURCE-REVIEW-001",
                approved_by="SIMULATED-RESEARCHER",
                acknowledges_source_version_change=True,
            )
        }
    )
    update = service.update(old.graph_id, approved)
    assert update.change_report.source_version_changed is True
    assert update.change_report.source_transition_evidence is not None
    assert update.change_report.source_transition_evidence.authenticity_verified is False


def test_requirement_coverage_reports_verified_partial_and_unresolved(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    build = TraceabilityGraphBuilder().build(result.manifest)
    assert all(
        item.status is RequirementCoverageStatus.VERIFIED
        for item in build.coverage.requirements
    )
    requirement = build.source.requirement_ids[0]
    requirement_node = f"REQUIREMENT:{requirement}"
    without_verification = tuple(
        link
        for link in build.links
        if link.relation_type is not TraceRelationType.VERIFIED_BY
    )
    partial = TraceabilityGraphBuilder.coverage(
        build.source.requirement_ids,
        build.nodes,
        without_verification,
    )
    assert partial.requirements[0].status is RequirementCoverageStatus.PARTIAL
    without_implementation = tuple(
        link
        for link in without_verification
        if not (
            link.relation_type is TraceRelationType.IMPLEMENTS
            and link.target_node_id == requirement_node
        )
    )
    unresolved = TraceabilityGraphBuilder.coverage(
        build.source.requirement_ids,
        build.nodes,
        without_implementation,
    )
    assert unresolved.requirements[0].status is RequirementCoverageStatus.UNRESOLVED


@pytest.mark.parametrize(
    ("predicted", "expected", "counts", "scores"),
    (
        (
            {("A", "IMPLEMENTS", "B")},
            {("A", "IMPLEMENTS", "B")},
            (1, 0, 0),
            (1.0, 1.0, 1.0),
        ),
        (
            {("A", "IMPLEMENTS", "B"), ("C", "EXPOSES", "D")},
            {("A", "IMPLEMENTS", "B")},
            (1, 1, 0),
            (0.5, 1.0, 2 / 3),
        ),
        (
            {("A", "IMPLEMENTS", "B")},
            {("A", "IMPLEMENTS", "B"), ("C", "EXPOSES", "D")},
            (1, 0, 1),
            (1.0, 0.5, 2 / 3),
        ),
        (
            {("A", "IMPLEMENTS", "B"), ("E", "DEFINES", "F")},
            {("A", "IMPLEMENTS", "B"), ("C", "EXPOSES", "D")},
            (1, 1, 1),
            (0.5, 0.5, 0.5),
        ),
        (set(), set(), (0, 0, 0), (0.0, 0.0, 0.0)),
    ),
    ids=(
        "perfect",
        "one-false-positive",
        "one-false-negative",
        "false-positive-and-false-negative",
        "empty-predicted-and-expected",
    ),
)
def test_precision_recall_and_f1_cases(
    predicted: set[tuple[str, str, str]],
    expected: set[tuple[str, str, str]],
    counts: tuple[int, int, int],
    scores: tuple[float, float, float],
) -> None:
    metrics = TraceabilityService._calculate_metrics(predicted, expected)

    assert metrics[:3] == counts
    assert metrics[3:] == pytest.approx(scores)


def test_evaluation_with_no_predicted_or_expected_links_returns_zero_scores(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)
    scope_node = snapshot.nodes[0].node_id
    assert not any(
        link.source_node_id == scope_node and link.target_node_id == scope_node
        for link in snapshot.links
    )
    truth = ResearchGroundTruth(
        dataset_id="SIMULATED-EMPTY-LINK-ORACLE",
        dataset_version="1.0",
        researcher_reference="SIMULATED-NO-LINKS",
        in_scope_node_ids=(scope_node,),
        expected_links=(),
    )

    report = service.evaluate(snapshot.graph_id, 1, truth)

    assert report.true_positive_count == 0
    assert report.false_positive_count == 0
    assert report.false_negative_count == 0
    assert report.precision == 0.0
    assert report.recall == 0.0
    assert report.f1_score == 0.0


def test_precision_recall_f1_uses_separate_researcher_ground_truth(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)
    predicted = [
        link
        for link in snapshot.links
        if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
        and link.resolution_status is TraceResolutionStatus.RESOLVED
    ]
    scope = tuple(node.node_id for node in snapshot.nodes)
    expected = tuple(
        GroundTruthLink(
            source_node_id=link.source_node_id,
            relation_type=link.relation_type,
            target_node_id=link.target_node_id,
        )
        for link in predicted[:-1]
    ) + (
        GroundTruthLink(
            source_node_id=scope[0],
            relation_type=TraceRelationType.PERSISTS_TO,
            target_node_id=scope[-1],
        ),
    )
    truth = ResearchGroundTruth(
        dataset_id="SIMULATED-RESEARCHER-GROUND-TRUTH-TASK-MVP",
        dataset_version="1.0",
        researcher_reference="SIMULATED-MANUAL-LABELS-001",
        in_scope_node_ids=scope,
        expected_links=expected,
    )

    report = service.evaluate(snapshot.graph_id, 1, truth)

    assert report.ground_truth_authorship == "RESEARCHER_CURATED"
    assert report.true_positive_count == len(predicted) - 1
    assert report.false_positive_count == 1
    assert report.false_negative_count == 1
    assert report.precision == pytest.approx((len(predicted) - 1) / len(predicted))
    assert report.recall == pytest.approx((len(predicted) - 1) / len(predicted))
    assert report.f1_score == pytest.approx((len(predicted) - 1) / len(predicted))
    assert report.algorithm_output_claim == "CALCULATED_NOT_BENCHMARKED"

    repeated = service.evaluate(snapshot.graph_id, 1, truth)
    assert report.evaluation_version == "1.1"
    assert report.model_dump_json() == repeated.model_dump_json()


def test_simulated_researcher_curated_fixture_is_evaluated_not_claimed_as_benchmark(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "simulated"
        / "researcher_curated_traceability_ground_truth.json"
    )
    truth = ResearchGroundTruth.model_validate(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )

    report = service.evaluate(snapshot.graph_id, 1, truth)

    assert report.true_positive_count == 6
    assert report.false_positive_count == 0
    assert report.false_negative_count == 0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1_score == 1.0
    assert report.algorithm_output_claim == "CALCULATED_NOT_BENCHMARKED"


def test_traceability_api_routes_are_exposed(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/traceability/graphs" in paths
    assert "/api/v1/traceability/graphs/{graph_id}/compare" in paths
    assert "/api/v1/traceability/graphs/{graph_id}/updates" in paths
    assert (
        "/api/v1/traceability/graphs/{graph_id}/versions/{version}/evaluate"
        in paths
    )


def test_graph_creation_and_retrieval_api_round_trip(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "api-workspaces"
    result, _ = _generated_run(root)
    get_settings.cache_clear()
    try:
        application = create_app()
        application.state.settings = SimpleNamespace(
            generated_workspace_root=root,
            traceability_store_path=tmp_path / "api-traceability.sqlite3",
        )
        with TestClient(application) as api_client:
            created = api_client.post(
                "/api/v1/traceability/graphs",
                json=GraphCreateRequest(
                    manifest=result.manifest,
                    workspace_relative_path=result.workspace_relative_path,
                ).model_dump(mode="json"),
            )
            assert created.status_code == 201
            body = created.json()
            retrieved = api_client.get(
                f"/api/v1/traceability/graphs/{body['graph_id']}/versions/1"
            )
            assert retrieved.status_code == 200
            assert retrieved.json() == body
    finally:
        get_settings.cache_clear()


def test_chain_query_retrieves_full_typed_chain(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    res_chain = service.chain(snapshot.graph_id, "REQ-TASK-001")
    assert isinstance(res_chain, RequirementTraceChain)
    assert res_chain.requirement_id == "REQ-TASK-001"
    assert res_chain.requirement_node_id == "REQUIREMENT:REQ-TASK-001"
    assert len(res_chain.uml_nodes) > 0
    assert len(res_chain.code_modules) > 0
    assert len(res_chain.api_operations) > 0
    assert len(res_chain.database_artifacts) > 0
    assert len(res_chain.test_hooks) > 0
    assert len(res_chain.links) > 0


def test_impact_set_query_returns_affected_nodes_and_modules(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    impact = service.impact_set(snapshot.graph_id, "REQ-TASK-001")
    assert isinstance(impact, ImpactSet)
    assert impact.requirement_id == "REQ-TASK-001"
    assert len(impact.affected_node_ids) > 0
    assert len(impact.code_node_ids) > 0
    assert len(impact.api_node_ids) > 0
    # The Task MVP SQL artifact is design-only and its mapping is
    # REVIEW_REQUIRED, so the existing scoped-impact policy must not claim it
    # as automatically affected.
    assert impact.database_node_ids == ()
    assert len(impact.test_hook_node_ids) > 0
    assert len(impact.module_paths) > 0


def test_requirements_for_module_reverse_lookup(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    # Pick the primary task service file
    service_file = next(
        f for f in result.manifest.files
        if "Service" in f.relative_path or "service" in f.relative_path
    )
    reqs_by_file_id = service.requirements_for_module(
        snapshot.graph_id, service_file.file_id
    )
    reqs_by_path = service.requirements_for_module(
        snapshot.graph_id, service_file.relative_path
    )

    assert len(reqs_by_file_id) > 0
    assert reqs_by_file_id == reqs_by_path
    assert "REQ-TASK-001" in reqs_by_file_id


def test_rtm_export_generates_json_and_table(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    rtm = service.export_rtm(snapshot.graph_id)
    assert isinstance(rtm, RtmExport)
    assert rtm.graph_id == snapshot.graph_id
    assert rtm.graph_version == 1
    assert len(rtm.rows) == len(result.manifest.source.requirement_ids)
    assert rtm.rows[0].requirement_id == "REQ-TASK-001"
    assert len(rtm.rows[0].uml_elements) > 0
    assert len(rtm.rows[0].code_modules) > 0
    assert "| Requirement | UML Elements |" in rtm.table_markdown
    assert "REQ-TASK-001" in rtm.table_markdown


def test_orphan_detection_and_validation(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    # Normal valid graph has 0 orphan downstream nodes
    diagnostics = detect_orphans_and_gaps(snapshot)
    assert len(diagnostics["orphan_node_ids"]) == 0
    validate_no_orphans(snapshot)

    # Create an artificially injected orphan CODE_MODULE node
    orphan_node = snapshot.nodes[0].model_copy(
        update={
            "node_id": "CODE_MODULE:FILE-ORPHAN-TEST",
            "node_type": GraphNodeType.CODE_MODULE,
            "source_identity": "FILE-ORPHAN-TEST",
            "label": "orphan-test.py",
            "attributes": {"artifact_type": "BUSINESS_LOGIC", "relative_path": "backend/src/orphan.py"},
        }
    )
    orphan_snapshot = snapshot.model_copy(
        update={"nodes": (*snapshot.nodes, orphan_node)}
    )

    orphan_diag = detect_orphans_and_gaps(orphan_snapshot)
    assert "CODE_MODULE:FILE-ORPHAN-TEST" in orphan_diag["orphan_node_ids"]
    orphan_metrics = compute_metrics_report(orphan_snapshot)
    assert {
        diagnostic.code for diagnostic in orphan_metrics.diagnostics
    } == {"ORPHAN_DOWNSTREAM_NODE"}

    with pytest.raises(ApplicationError) as captured:
        validate_no_orphans(orphan_snapshot)
    assert captured.value.errors[0].code == "ORPHAN_GRAPH_NODE"

    missing_requirement_snapshot = snapshot.model_copy(
        update={
            "nodes": tuple(
                node
                for node in snapshot.nodes
                if node.node_id != "REQUIREMENT:REQ-TASK-001"
            )
        }
    )
    gap_metrics = compute_metrics_report(missing_requirement_snapshot)
    assert "REQ-TASK-001" in gap_metrics.coverage_gaps
    assert "REQUIREMENT_COVERAGE_GAP" in {
        diagnostic.code for diagnostic in gap_metrics.diagnostics
    }


def test_negative_cases_and_explicit_error_codes(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    # 1. Unknown requirement id
    with pytest.raises(ApplicationError) as req_err:
        service.chain(snapshot.graph_id, "UNKNOWN-REQ-999")
    assert req_err.value.errors[0].code == "UNKNOWN_REQUIREMENT_ID"

    # 2. Missing REQ->UML anchor
    manifest_without_anchor = result.manifest.model_copy(
        update={
            "source": result.manifest.source.model_copy(
                update={"requirement_uml_anchors": ()}
            )
        }
    )
    with pytest.raises(ApplicationError) as anchor_err:
        validate_upstream_anchors(manifest_without_anchor)
    assert anchor_err.value.errors[0].code == "MISSING_REQ_UML_ANCHOR"

    # 3. Empty requirements list
    manifest_empty_reqs = result.manifest.model_copy(
        update={
            "source": result.manifest.source.model_copy(
                update={"requirement_ids": ()}
            )
        }
    )
    with pytest.raises(ApplicationError) as empty_err:
        TraceabilityGraphBuilder().build(manifest_empty_reqs)
    assert empty_err.value.errors[0].code == "EMPTY_REQUIREMENTS_LIST"

    # 4. Stale artifact digest / hash mismatch
    (workspace / "README.md").write_text("tampered content\n", encoding="utf-8")
    with pytest.raises(ApplicationError) as hash_err:
        _create(service, result)
    assert hash_err.value.errors[0].code == "ARTIFACT_HASH_MISMATCH"


def test_api_routes_for_queries_and_rtm(tmp_path: Path) -> None:
    root = tmp_path / "api-workspaces-queries"
    result, _ = _generated_run(root)
    get_settings.cache_clear()
    try:
        application = create_app()
        application.state.settings = SimpleNamespace(
            generated_workspace_root=root,
            traceability_store_path=tmp_path / "api-traceability-q.sqlite3",
        )
        with TestClient(application) as api_client:
            created = api_client.post(
                "/api/v1/traceability/graphs",
                json=GraphCreateRequest(
                    manifest=result.manifest,
                    workspace_relative_path=result.workspace_relative_path,
                ).model_dump(mode="json"),
            )
            assert created.status_code == 201
            graph_id = created.json()["graph_id"]

            chain_resp = api_client.get(
                f"/api/v1/traceability/graphs/{graph_id}/chains/REQ-TASK-001"
            )
            assert chain_resp.status_code == 200
            assert chain_resp.json()["requirement_id"] == "REQ-TASK-001"

            impact_resp = api_client.get(
                f"/api/v1/traceability/graphs/{graph_id}/impact/REQ-TASK-001"
            )
            assert impact_resp.status_code == 200
            assert impact_resp.json()["requirement_id"] == "REQ-TASK-001"

            rtm_resp = api_client.get(
                f"/api/v1/traceability/graphs/{graph_id}/rtm"
            )
            assert rtm_resp.status_code == 200
            assert len(rtm_resp.json()["rows"]) == 3
    finally:
        get_settings.cache_clear()


def test_regression_one_requirement_change_only_affects_its_chain(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    old_result, _ = _generated_run(root)
    new_result, new_workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    old_snapshot = _create(service, old_result)

    # In v1, record all three requirement chains
    v1_c1 = service.chain(old_snapshot.graph_id, "REQ-TASK-001", version=1)
    v1_c2 = service.chain(old_snapshot.graph_id, "REQ-TASK-002", version=1)
    v1_c3 = service.chain(old_snapshot.graph_id, "REQ-TASK-003", version=1)

    # Create an updated manifest where only REQ-TASK-001 gains a new dedicated module
    records = {record.relative_path: record for record in new_result.manifest.files}
    added_path = new_workspace / "docs/req1-extra-doc.txt"
    added_path.parent.mkdir(parents=True, exist_ok=True)
    added_path.write_text("REQ-TASK-001 specific update.\n", encoding="utf-8", newline="\n")
    added_bytes = added_path.read_bytes()
    added_record = GeneratedFileRecord(
        file_id="FILE-REQ1-EXTRA",
        relative_path="docs/req1-extra-doc.txt",
        module_identity="req1-extra",
        artifact_type=GeneratedArtifactType.DOCUMENTATION,
        origin=ArtifactOrigin.TEMPLATE,
        sha256=sha256(added_bytes).hexdigest(),
        size_bytes=len(added_bytes),
        requirement_ids=("REQ-TASK-001",),
    )
    records[added_record.relative_path] = added_record

    # Add an IMPLEMENTS link specifically for REQ-TASK-001 from this new module
    from intelise_c3.domain.generation import TraceabilityLink, TraceLinkProvenance
    extra_link = TraceabilityLink(
        link_id="LINK-REQ1-EXTRA-DOC",
        source_entity_type=TraceEntityType.FILE,
        source_id="FILE-REQ1-EXTRA",
        relation_type=TraceRelationType.IMPLEMENTS,
        target_entity_type=TraceEntityType.REQUIREMENT,
        target_id="REQ-TASK-001",
        resolution_status=TraceResolutionStatus.RESOLVED,
        review_status=TraceReviewStatus.NOT_REQUIRED,
        provenance=TraceLinkProvenance(
            evidence_kind="DETERMINISTIC_MAPPING_RULE",
            mapping_rule_id="C3_REQ1_EXTRA_MAPPING",
            evidence_refs=("FILE-REQ1-EXTRA",),
            details="Extra doc specifically implementing REQ-TASK-001",
        ),
    )

    updated_manifest = _with_recomputed_evidence(
        new_result.manifest,
        files=tuple(records.values()),
        traceability=new_result.manifest.traceability.model_copy(
            update={"links": (*new_result.manifest.traceability.links, extra_link)}
        ),
    )
    _write_manifest(new_workspace, updated_manifest)

    update = service.update(
        old_snapshot.graph_id,
        GraphUpdateRequest(
            manifest=updated_manifest,
            workspace_relative_path=new_result.workspace_relative_path,
            base_graph_version=1,
        ),
    )

    assert update.snapshot.graph_version == 2

    # In v2:
    v2_c1 = service.chain(old_snapshot.graph_id, "REQ-TASK-001", version=2)
    v2_c2 = service.chain(old_snapshot.graph_id, "REQ-TASK-002", version=2)
    v2_c3 = service.chain(old_snapshot.graph_id, "REQ-TASK-003", version=2)

    # 1. REQ-TASK-001 chain MUST change
    assert v2_c1 != v1_c1
    assert "CODE_MODULE:FILE-REQ1-EXTRA" in {n.node_id for n in v2_c1.code_modules}
    added_node = next(
        node
        for node in update.snapshot.nodes
        if node.node_id == "CODE_MODULE:FILE-REQ1-EXTRA"
    )
    assert (
        added_node.created_in_generation_run_id
        == updated_manifest.generation_run_id
    )
    preserved_requirement = next(
        node
        for node in update.snapshot.nodes
        if node.node_id == "REQUIREMENT:REQ-TASK-002"
        and node.lifecycle_status is GraphLifecycleStatus.ACTIVE
    )
    assert (
        preserved_requirement.created_in_generation_run_id
        == old_result.manifest.generation_run_id
    )

    # 2. REQ-TASK-002 chain MUST be byte-identical
    assert v2_c2.model_dump_json() == v1_c2.model_dump_json()

    # 3. REQ-TASK-003 chain MUST be byte-identical
    assert v2_c3.model_dump_json() == v1_c3.model_dump_json()


def test_metrics_report_with_gpa_oracle(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    result, _ = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    snapshot = _create(service, result)

    # 1. Base metrics without oracle
    metrics_base = service.metrics(snapshot.graph_id)
    assert isinstance(metrics_base, TraceabilityMetricsReport)
    assert metrics_base.total_requirements == 3
    assert metrics_base.covered_requirements == 3
    assert metrics_base.coverage_rate == 1.0
    assert metrics_base.orphan_rate == 0.0

    # 2. Evaluate against the GPA oracle fixture
    gpa_truth_path = (
        Path(__file__).parent
        / "fixtures"
        / "simulated"
        / "gpa_researcher_ground_truth.json"
    )
    gpa_truth = ResearchGroundTruth.model_validate(
        json.loads(gpa_truth_path.read_text(encoding="utf-8"))
    )

    # For testing the GPA oracle directly: build a GPA graph from the GPA input package
    from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
    from intelise_c3.services.input_validation import InputValidationService
    from intelise_c3.services.design_understanding import DesignUnderstandingService
    from intelise_c3.services.stack_selection import StackSelectionService
    from intelise_c3.contracts.stack_selection import StackSelectionRequest
    from intelise_c3.contracts.generation import CodeGenerationRequest, GenerationMode, ProvisionalStackApproval, ProvisionalApprovalStatus
    from intelise_c3.scripts.generate_task_mvp import build_simulated_stack_criteria

    gpa_pkg_path = Path(__file__).parent / "fixtures" / "simulated" / "gpa_input_package.json"
    gpa_payload = json.loads(gpa_pkg_path.read_text(encoding="utf-8"))
    gpa_pkg = ProvisionalInputPackage.model_validate(gpa_payload)
    gpa_gen_ctx = InputValidationService().validate(gpa_pkg)
    gpa_design_ctx = DesignUnderstandingService().build(gpa_gen_ctx)
    criteria = build_simulated_stack_criteria()
    gpa_stack_report = StackSelectionService().select(
        StackSelectionRequest(design_context=gpa_design_ctx, criteria=criteria)
    )
    gpa_req = CodeGenerationRequest(
        generation_context=gpa_gen_ctx,
        design_context=gpa_design_ctx,
        stack_selection_report=gpa_stack_report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference="SIMULATED-GPA-APPROVAL",
            approved_by="LOCAL-RESEARCHER-EXPERIMENT",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.TEMPLATE_ONLY,
        workspace_name="gpa-calc-manual",
    )
    import asyncio
    gpa_result = asyncio.run(CodeGenerationService(root, None).generate(gpa_req))
    gpa_snapshot = _create(service, gpa_result)

    gpa_metrics = service.metrics(gpa_snapshot.graph_id, oracle=gpa_truth)
    assert gpa_metrics.oracle_dataset_id == "SIMULATED-RESEARCHER-GROUND-TRUTH-GPA-PROJECT"
    assert gpa_metrics.oracle_link_count == 3
    assert gpa_metrics.true_positives == 3
    assert gpa_metrics.false_positives == 0
    assert gpa_metrics.false_negatives == 0
    assert gpa_metrics.precision == 1.0
    assert gpa_metrics.recall == 1.0
    assert gpa_metrics.f1_score == 1.0
    assert "hand-labelled oracle" in gpa_metrics.oracle_honesty_note
    assert "3 expected links" in gpa_metrics.oracle_honesty_note


def test_metrics_preservation_rate_after_regeneration(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    old_result, _ = _generated_run(root)
    new_result, new_workspace = _generated_run(root)
    service = _service(root, tmp_path / "graphs.sqlite3")
    old_snapshot = _create(service, old_result)

    records = {record.relative_path: record for record in new_result.manifest.files}
    added_path = new_workspace / "docs/note.txt"
    added_path.parent.mkdir(parents=True, exist_ok=True)
    added_path.write_text("Note\n", encoding="utf-8")
    added_bytes = added_path.read_bytes()
    added_record = GeneratedFileRecord(
        file_id="FILE-NOTE",
        relative_path="docs/note.txt",
        module_identity="note",
        artifact_type=GeneratedArtifactType.DOCUMENTATION,
        origin=ArtifactOrigin.TEMPLATE,
        sha256=sha256(added_bytes).hexdigest(),
        size_bytes=len(added_bytes),
    )
    records[added_record.relative_path] = added_record
    updated_manifest = _with_recomputed_evidence(new_result.manifest, files=tuple(records.values()))
    _write_manifest(new_workspace, updated_manifest)

    update = service.update(
        old_snapshot.graph_id,
        GraphUpdateRequest(
            manifest=updated_manifest,
            workspace_relative_path=new_result.workspace_relative_path,
            base_graph_version=1,
        ),
    )
    metrics = service.metrics(old_snapshot.graph_id, version=2, change_report=update.change_report)
    assert metrics.preservation_rate == 1.0
