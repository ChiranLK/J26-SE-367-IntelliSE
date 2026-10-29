"""Tests for requirement_type authorization and the /design-coverage endpoint."""

import pytest
from fastapi.testclient import TestClient

from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation_context import (
    GenerationContext,
    NormalizedRequirement,
)
from intelise_c3.services.code_generation import CodeGenerationService
from test_code_generation import (  # noqa: F401  (task_contexts is a fixture)
    StubLLMClient,
    _model_output,
    _request,
    task_contexts,
)

EXTRA_ID = "REQ-EXTRA-UNANCHORED"


def _with_unanchored(
    generation: GenerationContext, design: DesignContext, requirement_type: str | None
) -> tuple[GenerationContext, DesignContext]:
    extra = NormalizedRequirement(
        requirement_id=EXTRA_ID,
        title="Requirement with no UML anchor",
        approval_status="APPROVED",
        requirement_type=requirement_type,
    )
    requirements = (*generation.requirements, extra)
    return (
        generation.model_copy(update={"requirements": requirements}),
        design.model_copy(update={"requirements": requirements}),
    )


def _authorize(tmp_path, generation, design) -> None:
    service = CodeGenerationService(tmp_path, StubLLMClient(_model_output()))
    service._validate_authorization(_request(generation, design))


def test_unanchored_fr_is_still_blocked(
    tmp_path, task_contexts: tuple[GenerationContext, DesignContext]
) -> None:
    generation, design = _with_unanchored(*task_contexts, "FR")

    with pytest.raises(ApplicationError) as captured:
        _authorize(tmp_path, generation, design)

    assert "MISSING_GENERATION_DESIGN_REFERENCE" in {e.code for e in captured.value.errors}


def test_unanchored_nfr_is_allowed(
    tmp_path, task_contexts: tuple[GenerationContext, DesignContext]
) -> None:
    generation, design = _with_unanchored(*task_contexts, "NFR")

    _authorize(tmp_path, generation, design)


def test_unanchored_untyped_requirement_is_blocked_as_before(
    tmp_path, task_contexts: tuple[GenerationContext, DesignContext]
) -> None:
    generation, design = _with_unanchored(*task_contexts, None)

    with pytest.raises(ApplicationError) as captured:
        _authorize(tmp_path, generation, design)

    assert "MISSING_GENERATION_DESIGN_REFERENCE" in {e.code for e in captured.value.errors}


def test_nfr_does_not_waive_the_need_for_some_anchor(
    tmp_path, task_contexts: tuple[GenerationContext, DesignContext]
) -> None:
    generation, design = task_contexts
    design = design.model_copy(update={"requirement_uml_anchors": ()})

    with pytest.raises(ApplicationError):
        _authorize(tmp_path, generation, design)


def test_untyped_requirement_serialization_is_unchanged(
    generation_context: GenerationContext,
) -> None:
    dumped = generation_context.model_dump(mode="json")

    assert all("requirement_type" not in item for item in dumped["requirements"])
    assert GenerationContext.model_validate(dumped) == generation_context


def test_coverage_endpoint_reports_anchors_and_is_deterministic(
    client: TestClient, generation_context: GenerationContext
) -> None:
    typed = _with_unanchored(generation_context, generation_context, "FR")[0]
    payload = typed.model_dump(mode="json")

    first = client.post("/api/v1/design-coverage", json=payload)
    second = client.post("/api/v1/design-coverage", json=payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    by_id = {item["requirement_id"]: item for item in body["requirements"]}
    assert by_id[EXTRA_ID]["status"] == "UNANCHORED_FR"
    assert body["totals"]["frs_unanchored"] == 1
    assert {"code": "FR_WITHOUT_ANCHOR", "subject_id": EXTRA_ID} == {
        k: v for k, v in body["diagnostics"][0].items() if k != "message"
    }
    assert "semantic" in body["note"]
    ids = [item["requirement_id"] for item in body["requirements"]]
    assert ids == sorted(ids)


def test_coverage_endpoint_marks_nfr_not_applicable(
    client: TestClient, generation_context: GenerationContext
) -> None:
    typed = _with_unanchored(generation_context, generation_context, "NFR")[0]

    body = client.post(
        "/api/v1/design-coverage", json=typed.model_dump(mode="json")
    ).json()

    entry = next(r for r in body["requirements"] if r["requirement_id"] == EXTRA_ID)
    assert entry["status"] == "NFR_NOT_APPLICABLE"
    assert body["totals"]["nfrs"] == 1
    assert all(d["code"] != "FR_WITHOUT_ANCHOR" for d in body["diagnostics"])
