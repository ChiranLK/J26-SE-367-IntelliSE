"""Standalone RAG A tests; no generation or regeneration flow imports it."""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re

import pytest
from pydantic import ValidationError

pytest.importorskip("chromadb")

from intelise_c3.contracts.defect_report import (  # noqa: E402
    DefectCategory,
    DefectEvidence,
    DefectItem,
    DefectLocation,
    DefectReport,
    DefectSeverity,
    FailingTestHookType,
    FailingTestReference,
)
from intelise_c3.contracts.generation import (  # noqa: E402
    CodeGenerationRequest,
    GenerationMode,
    ProvisionalApprovalStatus,
    ProvisionalStackApproval,
)
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage  # noqa: E402
from intelise_c3.contracts.stack_selection import StackSelectionRequest  # noqa: E402
from intelise_c3.contracts.traceability import GraphCreateRequest  # noqa: E402
from intelise_c3.core.errors import ApplicationError  # noqa: E402
from intelise_c3.domain.generation import TraceRelationType  # noqa: E402
from intelise_c3.domain.traceability import GraphNodeType  # noqa: E402
from intelise_c3.rag.defect_context import (  # noqa: E402
    ChromaDefectContextStore,
    DefectContextGraph,
    get_defect_context,
    index_defect_context,
)
from intelise_c3.scripts.generate_task_mvp import build_simulated_stack_criteria  # noqa: E402
from intelise_c3.services.code_generation import CodeGenerationService  # noqa: E402
from intelise_c3.services.design_understanding import DesignUnderstandingService  # noqa: E402
from intelise_c3.services.input_validation import InputValidationService  # noqa: E402
from intelise_c3.services.stack_selection import StackSelectionService  # noqa: E402
from intelise_c3.services.traceability import TraceabilityService  # noqa: E402
from intelise_c3.traceability.builder import TraceabilityGraphBuilder  # noqa: E402
from intelise_c3.traceability.queries import impact_set, requirements_for_module  # noqa: E402
from intelise_c3.traceability.store import SQLiteTraceabilityStore  # noqa: E402
from intelise_c3.traceability.verification import ManifestVerificationService  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "simulated" / "gpa_input_package.json"
DIM = 128


class FakeEmbedding:
    @staticmethod
    def name():
        return "raga-fake-hash"

    def __call__(self, input):
        output = []
        for text in input:
            vector = [0.0] * DIM
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                index = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM
                vector[index] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            output.append([value / norm for value in vector])
        return output

    def embed_query(self, input):
        return self.__call__(input)

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return FakeEmbedding()

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine"]


class ConstantEmbedding(FakeEmbedding):
    @staticmethod
    def name():
        return "raga-constant"

    def __call__(self, input):
        return [[1.0] + [0.0] * (DIM - 1) for _ in input]

    @staticmethod
    def build_from_config(config):
        return ConstantEmbedding()


@pytest.fixture()
def gpa_environment(tmp_path: Path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation_context = InputValidationService().validate(package)
    design_context = DesignUnderstandingService().build(generation_context)
    stack_report = StackSelectionService().select(
        StackSelectionRequest(
            design_context=design_context,
            criteria=build_simulated_stack_criteria(),
        )
    )
    request = CodeGenerationRequest(
        generation_context=generation_context,
        design_context=design_context,
        stack_selection_report=stack_report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference="SIMULATED-GPA-RAGA-APPROVAL",
            approved_by="LOCAL-RESEARCHER-TEST",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.TEMPLATE_ONLY,
        workspace_name="gpa-raga-test",
    )
    workspace_root = tmp_path / "workspaces"
    result = asyncio.run(CodeGenerationService(workspace_root, None).generate(request))
    service = TraceabilityService(
        verifier=ManifestVerificationService(workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(tmp_path / "graphs.sqlite3"),
    )
    snapshot = service.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )
    store = ChromaDefectContextStore(
        tmp_path / "raga-db", "fake", FakeEmbedding()
    )
    graph = DefectContextGraph(
        snapshot=snapshot,
        manifest=result.manifest,
        workspace_root=workspace_root,
        workspace_relative_path=result.workspace_relative_path,
        store=store,
        top_k=8,
    )
    service_node = next(
        node
        for node in snapshot.nodes
        if node.node_type is GraphNodeType.CODE_MODULE
        and "/services/" in str(node.attributes.get("relative_path"))
    )
    requirement_ids = requirements_for_module(
        snapshot, service_node.node_id, result.manifest
    )
    requirement_id = (
        "REQ-GPA-002" if "REQ-GPA-002" in requirement_ids else requirement_ids[0]
    )
    return graph, service_node, requirement_id


def _report(
    graph: DefectContextGraph,
    module_path: str,
    requirement_id: str,
    *,
    explanation: str | None = (
        "The update method does not validate the current course before applying changes."
    ),
) -> DefectReport:
    item = DefectItem(
        defect_id="SIM-GPA-DEFECT-001",
        category=DefectCategory.BUSINESS_LOGIC,
        severity=DefectSeverity.HIGH,
        title="Course update accepts an unknown course",
        affected_requirement_ids=(requirement_id,),
        failing_tests=(
            FailingTestReference(
                test_case_id="SIM-GPA-TEST-001",
                hook_type=FailingTestHookType.TEST_FILE,
                hook_ref="backend/tests/courseService.test.js",
            ),
        ),
        location=DefectLocation(relative_path=module_path, symbol="update"),
        evidence=DefectEvidence(
            observed_behavior="Unknown course update is accepted.",
            expected_behavior="Unknown course update must be rejected.",
        ),
        explanation=explanation,
    )
    return DefectReport(
        source_classification="SIMULATED_C4_FIXTURE",
        defect_report_id="SIM-GPA-RAGA-REPORT-001",
        reported_at_utc="2026-10-20T00:00:00Z",
        source_generation_run_id=graph.manifest.generation_run_id,
        source_artifact_digest_sha256=graph.manifest.artifact_digest_sha256,
        source_graph_version=graph.snapshot.graph_version,
        defects=(item,),
    )


def _error_code(exception: pytest.ExceptionInfo[ApplicationError]) -> str:
    return exception.value.errors[0].code


def test_indexes_real_gpa_generated_code_and_retrieves_only_graph_scope(
    gpa_environment,
) -> None:
    graph, service_node, requirement_id = gpa_environment
    chunks = index_defect_context(graph)
    report = _report(
        graph, str(service_node.attributes["relative_path"]), requirement_id
    )

    retrieved = get_defect_context(report, graph)
    expected_scope = set(
        impact_set(graph.snapshot, requirement_id, graph.manifest).code_node_ids
    )

    assert chunks
    assert retrieved
    assert all(item.module_id in expected_scope for item in retrieved)
    assert all(item.requirement_id.startswith("REQ-GPA-") for item in retrieved)
    assert all(item.uml_id == "UML-GPA-CLASS-001" for item in retrieved)
    assert all(item.chunk_id.startswith("RAGA-") for item in retrieved)
    assert all(0.0 <= item.similarity_score <= 1.0 for item in retrieved)
    assert any(item.symbol.endswith(".update") for item in retrieved)


def test_raga_uses_a_separate_chroma_collection(gpa_environment) -> None:
    graph, _, _ = gpa_environment
    assert graph.store.collection_name == "defect_context__fake"
    assert not graph.store.collection_name.startswith("best_practices__")


def test_unknown_module_is_rejected(gpa_environment) -> None:
    graph, _, requirement_id = gpa_environment
    index_defect_context(graph)
    report = _report(graph, "backend/src/services/missingService.js", requirement_id)

    with pytest.raises(ApplicationError) as captured:
        get_defect_context(report, graph)

    assert _error_code(captured) == "DEFECT_CONTEXT_MODULE_NOT_IN_GRAPH"


def test_unknown_rtm_reference_is_rejected_by_existing_chain_query(
    gpa_environment,
) -> None:
    graph, service_node, _ = gpa_environment
    index_defect_context(graph)
    report = _report(
        graph, str(service_node.attributes["relative_path"]), "REQ-GPA-NOT-IN-GRAPH"
    )

    with pytest.raises(ApplicationError) as captured:
        get_defect_context(report, graph)

    assert _error_code(captured) == "UNKNOWN_REQUIREMENT_ID"


@pytest.mark.parametrize("explanation", [None, "   "])
def test_missing_or_blank_xai_from_gpa_report_is_rejected(
    gpa_environment,
    explanation: str | None,
) -> None:
    graph, service_node, requirement_id = gpa_environment
    # The report is built from the generated real GPA fixture; no fallback or
    # synthetic XAI text is inserted when the explanation is absent/blank.
    report = _report(
        graph,
        str(service_node.attributes["relative_path"]),
        requirement_id,
        explanation=explanation,
    )

    with pytest.raises(ApplicationError) as captured:
        get_defect_context(report, graph)

    assert _error_code(captured) == "DEFECT_CONTEXT_XAI_REQUIRED"


def test_schema_rejects_empty_xai_string_in_gpa_report(gpa_environment) -> None:
    graph, service_node, requirement_id = gpa_environment
    with pytest.raises(ValidationError):
        _report(
            graph,
            str(service_node.attributes["relative_path"]),
            requirement_id,
            explanation="",
        )


def test_malformed_report_is_rejected(gpa_environment) -> None:
    graph, _, _ = gpa_environment
    with pytest.raises(ApplicationError) as captured:
        get_defect_context({"not": "a report"}, graph)  # type: ignore[arg-type]
    assert _error_code(captured) == "MALFORMED_DEFECT_REPORT"


def test_all_stale_chunks_return_empty_without_error(gpa_environment, tmp_path: Path) -> None:
    graph, service_node, requirement_id = gpa_environment
    chunks = index_defect_context(graph)
    stale_store = ChromaDefectContextStore(
        tmp_path / "stale-raga-db", "fake", FakeEmbedding()
    )
    stale_store.upsert(
        tuple(replace(item, artifact_digest="0" * 64) for item in chunks)
    )
    stale_graph = replace(graph, store=stale_store)
    report = _report(
        stale_graph, str(service_node.attributes["relative_path"]), requirement_id
    )

    assert get_defect_context(report, stale_graph) == []


def test_requirement_with_no_downstream_code_is_rejected(gpa_environment) -> None:
    graph, service_node, requirement_id = gpa_environment
    requirement_node_id = f"REQUIREMENT:{requirement_id}"
    isolated_snapshot = graph.snapshot.model_copy(
        update={
            "links": tuple(
                link
                for link in graph.snapshot.links
                if not (
                    link.relation_type is TraceRelationType.IMPLEMENTS
                    and link.target_node_id == requirement_node_id
                )
            )
        }
    )
    isolated_graph = replace(graph, snapshot=isolated_snapshot)
    report = _report(
        isolated_graph, str(service_node.attributes["relative_path"]), requirement_id
    )

    with pytest.raises(ApplicationError) as captured:
        get_defect_context(report, isolated_graph)

    assert _error_code(captured) == "DEFECT_CONTEXT_NO_DOWNSTREAM_CODE"


def test_ranking_ties_are_deterministic_by_chunk_id(
    gpa_environment, tmp_path: Path
) -> None:
    graph, service_node, requirement_id = gpa_environment
    constant_store = ChromaDefectContextStore(
        tmp_path / "tie-raga-db", "constant", ConstantEmbedding()
    )
    tie_graph = replace(graph, store=constant_store, top_k=20)
    index_defect_context(tie_graph)
    report = _report(
        tie_graph, str(service_node.attributes["relative_path"]), requirement_id
    )

    first = get_defect_context(report, tie_graph)
    second = get_defect_context(report, tie_graph)

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert [item.chunk_id for item in first] == sorted(item.chunk_id for item in first)


def test_report_whole_artifact_digest_must_match_current_graph(gpa_environment) -> None:
    graph, service_node, requirement_id = gpa_environment
    report = _report(
        graph, str(service_node.attributes["relative_path"]), requirement_id
    ).model_copy(update={"source_artifact_digest_sha256": "f" * 64})

    with pytest.raises(ApplicationError) as captured:
        get_defect_context(report, graph)

    assert _error_code(captured) == "DEFECT_CONTEXT_ARTIFACT_DIGEST_MISMATCH"
