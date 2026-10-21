"""Trigger-C integration tests using the clearly labelled simulated GPA fixture."""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from pathlib import Path

import pytest

from intelise_c3.contracts.generation import (
    CodeGenerationRequest,
    GenerationMode,
    ProvisionalApprovalStatus,
    ProvisionalStackApproval,
)
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.contracts.stack_selection import StackSelectionRequest
from intelise_c3.contracts.traceability import GraphCreateRequest
from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.domain.scoped_regeneration import (
    RegenerationReasonCode,
    RegenerationStatus,
)
from intelise_c3.rag.best_practices import FilterBestPracticeStore, load_rule_cards
from intelise_c3.rag.defect_context import ChromaDefectContextStore, DefectContextGraph
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.scripts.generate_task_mvp import build_simulated_stack_criteria
from intelise_c3.scripts.scoped_regeneration_experiment import (
    SimulatedModelClient,
    model_output,
)
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.stack_selection import StackSelectionService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.queries import requirements_for_module
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

from tests.test_defect_context import FakeEmbedding, _report
from tests.test_dynamic_stage3 import _rebind_manifest


GPA_FIXTURE = Path(__file__).parent / "fixtures" / "simulated" / "gpa_input_package.json"
COURSE_SERVICE = "backend/src/services/courseService.js"
MISSING_CHECK = (
    "      if (!(await repository.findById(id))) fail(404, "
    "'COURSE_NOT_FOUND', 'Course not found.');\n"
)


class EmptyDefectContextStore:
    def upsert(self, chunks):
        return None

    def query(self, text, module_ids):
        return []


def _rag_b() -> RagRuntime:
    cards = load_rule_cards(COMPONENT_ROOT / "rules")
    return RagRuntime.for_test(FilterBestPracticeStore(cards), backend="filter")


@pytest.fixture()
def gpa_trigger_c(tmp_path: Path):
    package = ProvisionalInputPackage.model_validate_json(
        GPA_FIXTURE.read_text(encoding="utf-8")
    )
    generation_context = InputValidationService().validate(package)
    design_context = DesignUnderstandingService().build(generation_context)
    stack_report = StackSelectionService().select(
        StackSelectionRequest(
            design_context=design_context,
            criteria=build_simulated_stack_criteria(),
        )
    )
    generation_request = CodeGenerationRequest(
        generation_context=generation_context,
        design_context=design_context,
        stack_selection_report=stack_report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference="SIMULATED-GPA-TRIGGER-C-APPROVAL",
            approved_by="LOCAL-RESEARCHER-TEST",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.TEMPLATE_ONLY,
        workspace_name="gpa-trigger-c-baseline",
    )
    root = tmp_path / "workspaces"
    result = asyncio.run(CodeGenerationService(root, None).generate(generation_request))
    workspace = root / result.workspace_relative_path
    corrected_source = (workspace / COURSE_SERVICE).read_text(encoding="utf-8")
    assert MISSING_CHECK in corrected_source
    defective_source = corrected_source.replace(
        MISSING_CHECK,
        "      // SIMULATED_C4_FIXTURE: update existence check deliberately removed.\n",
        1,
    )
    (workspace / COURSE_SERVICE).write_text(
        defective_source, encoding="utf-8", newline="\n"
    )
    data = (workspace / COURSE_SERVICE).read_bytes()
    records = tuple(
        item.model_copy(
            update={"sha256": sha256(data).hexdigest(), "size_bytes": len(data)}
        )
        if item.relative_path == COURSE_SERVICE
        else item
        for item in result.manifest.files
    )
    result = _rebind_manifest(result, workspace, files=records)

    traceability = TraceabilityService(
        verifier=ManifestVerificationService(root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(tmp_path / "graphs.sqlite3"),
    )
    snapshot = traceability.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )
    service_node = next(
        node
        for node in snapshot.nodes
        if node.attributes.get("relative_path") == COURSE_SERVICE
    )
    requirement_ids = requirements_for_module(
        snapshot, service_node.node_id, result.manifest
    )
    requirement_id = "REQ-GPA-002" if "REQ-GPA-002" in requirement_ids else requirement_ids[0]
    store = ChromaDefectContextStore(
        tmp_path / "raga-trigger-c", "fake", FakeEmbedding()
    )
    graph = DefectContextGraph(
        snapshot=snapshot,
        manifest=result.manifest,
        workspace_root=root,
        workspace_relative_path=result.workspace_relative_path,
        store=store,
    )
    report = _report(graph, COURSE_SERVICE, requirement_id)
    request = ScopedRegenerationRequest(
        defect_report=report,
        manifest=result.manifest,
        workspace_relative_path=result.workspace_relative_path,
        design_context=design_context,
    )
    return {
        "root": root,
        "workspace": workspace,
        "result": result,
        "snapshot": snapshot,
        "traceability": traceability,
        "store": store,
        "request": request,
        "corrected_source": corrected_source,
    }


def _service(env, client, *, store=None, attempts=2):
    return ScopedRegenerationService(
        env["root"],
        env["traceability"],
        client,
        model_evidence_class="SIMULATED_RAG_TEST_DOUBLE",
        defect_context_store=store if store is not None else env["store"],
        rag_runtime=_rag_b(),
        rag_a_backend="chroma-test",
        rag_a_embedding_model="fake",
        attempt_limit=attempts,
    )


def test_c3_06_gpa_trigger_c_records_both_rags_and_changes_only_course_service(
    gpa_trigger_c,
) -> None:
    env = gpa_trigger_c
    client = SimulatedModelClient(
        [model_output(COURSE_SERVICE, env["corrected_source"])]
    )
    outcome = asyncio.run(_service(env, client).regenerate(env["request"]))

    assert outcome.status is RegenerationStatus.PATCHED_PENDING_INDEPENDENT_RETEST
    assert outcome.repair_execution_mode == "SIMULATED_RAG_TEST_DOUBLE"
    assert outcome.artifact_versioning is not None
    assert outcome.artifact_versioning.new_artifact_digest_sha256 != (
        outcome.artifact_versioning.source_artifact_digest_sha256
    )
    assert outcome.preservation is not None
    assert outcome.preservation.changed_file_count == 1
    assert outcome.preservation.all_unselected_files_byte_identical is True
    assert [item.relative_path for item in outcome.patches] == [COURSE_SERVICE]
    assert outcome.graph_versioning is not None
    assert outcome.graph_versioning.new_graph_version == env["snapshot"].graph_version + 1
    assert outcome.patch_event is not None
    assert outcome.patch_event.changed_files == (COURSE_SERVICE,)
    assert outcome.patch_event.changed_symbol_basis == (
        "GRAPH_CORROBORATED_C4_LOCATION_CLAIM"
    )
    assert outcome.patch_event.graph_version_after == env["snapshot"].graph_version + 1
    evidence = outcome.retrieval_evidence[0]
    assert evidence.rag_a_chunk_ids
    assert evidence.rag_b_rule_ids
    assert outcome.patch_event.retrievals == outcome.retrieval_evidence
    prompt = client.requests[0].messages[-1].content
    assert "DEFECT_CONTEXT_EVIDENCE_JSON_BEGIN" in prompt
    assert "BEST_PRACTICE_RULES_BEGIN" in prompt
    assert evidence.rag_a_chunk_ids[0] in prompt
    assert evidence.rag_b_rule_ids[0] in prompt

    new_workspace = env["root"] / outcome.artifact_versioning.new_workspace_relative_path
    new_manifest = GenerationManifest.model_validate_json(
        (new_workspace / "artifact-manifest.json").read_text(encoding="utf-8")
    )
    old_hashes = {item.relative_path: item.sha256 for item in env["result"].manifest.files}
    new_hashes = {item.relative_path: item.sha256 for item in new_manifest.files}
    assert {
        path for path in old_hashes if old_hashes[path] != new_hashes[path]
    } == {COURSE_SERVICE}
    lineage = json.loads((new_workspace / "regeneration-record.json").read_text())
    assert lineage["trigger_c_patch_event"]["retrievals"][0]["rag_a_chunk_ids"]
    assert lineage["trigger_c_patch_event"]["retrievals"][0]["rag_b_rule_ids"]


def test_empty_rag_a_stops_before_model_and_returns_reindex_review_package(
    gpa_trigger_c,
) -> None:
    env = gpa_trigger_c
    client = SimulatedModelClient(
        [model_output(COURSE_SERVICE, env["corrected_source"])]
    )
    outcome = asyncio.run(
        _service(env, client, store=EmptyDefectContextStore()).regenerate(env["request"])
    )
    assert outcome.status is RegenerationStatus.REVIEW_REQUIRED
    assert outcome.reason_codes == (RegenerationReasonCode.INSUFFICIENT_DEFECT_CONTEXT,)
    assert outcome.human_review_package is not None
    assert "Re-index" in outcome.human_review_package.required_action
    assert client.requests == []
    assert outcome.artifact_versioning is None


def test_c3_08_attempt_limit_returns_complete_human_review_package(gpa_trigger_c) -> None:
    env = gpa_trigger_c
    bad = json.dumps({"path": "backend/src/app.js", "content": "unsafe"})
    client = SimulatedModelClient([bad, bad])
    outcome = asyncio.run(_service(env, client, attempts=2).regenerate(env["request"]))

    assert outcome.status is RegenerationStatus.FAILED
    assert outcome.reason_codes == (RegenerationReasonCode.PATCH_ATTEMPTS_EXHAUSTED,)
    assert outcome.human_review_package is not None
    package = outcome.human_review_package
    assert package.defect_report["source_classification"] == "SIMULATED_C4_FIXTURE"
    assert len(package.attempted_patches) == 2
    assert len(package.rejection_reasons) == 2
    assert package.candidate_new_generation_run_id is None
    assert package.candidate_new_artifact_digest_sha256 is None
    assert package.cross_round_history_included is False
    assert outcome.artifact_versioning is None
    assert outcome.graph_versioning is None


def test_c3_07_unknown_module_and_stale_digest_are_explicit(gpa_trigger_c) -> None:
    env = gpa_trigger_c
    client = SimulatedModelClient(
        [model_output(COURSE_SERVICE, env["corrected_source"])]
    )
    unknown = env["request"].model_copy(
        update={
            "defect_report": env["request"].defect_report.model_copy(
                update={
                    "defects": (
                        env["request"].defect_report.defects[0].model_copy(
                            update={
                                "location": env["request"].defect_report.defects[0].location.model_copy(
                                    update={"relative_path": "backend/src/services/missing.js"}
                                )
                            }
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(ApplicationError) as unknown_error:
        asyncio.run(_service(env, client).regenerate(unknown))
    assert unknown_error.value.errors[0].code == "DEFECT_CONTEXT_MODULE_NOT_IN_GRAPH"

    stale = env["request"].model_copy(
        update={
            "defect_report": env["request"].defect_report.model_copy(
                update={"source_artifact_digest_sha256": "f" * 64}
            )
        }
    )
    with pytest.raises(ApplicationError) as stale_error:
        asyncio.run(_service(env, client).regenerate(stale))
    assert stale_error.value.errors[0].code == "DEFECT_REPORT_DIGEST_MISMATCH"
    assert "re-verif" in stale_error.value.errors[0].message.lower()
