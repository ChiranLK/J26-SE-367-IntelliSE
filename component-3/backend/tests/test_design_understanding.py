"""Tests for deterministic design understanding from GenerationContext."""

import pytest
from fastapi.testclient import TestClient

from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_understanding import DesignUnderstandingService


def _with_plantuml(
    context: GenerationContext, source: str | None, *, element_type: str = "CLASS_DIAGRAM"
) -> GenerationContext:
    payload = context.model_dump(mode="json")
    payload["uml_elements"][0]["element_type"] = element_type
    payload["uml_elements"][0]["plantuml_source"] = source
    return GenerationContext.model_validate(payload)


def test_accepted_generation_context_is_processed(
    client: TestClient, generation_context: GenerationContext
) -> None:
    response = client.post(
        "/api/v1/design-context",
        json=generation_context.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["design_context_version"] == "1.0"


def test_requirement_uml_anchor_ui_and_provenance_are_preserved(
    generation_context: GenerationContext,
) -> None:
    design = DesignUnderstandingService().build(generation_context)

    assert design.requirements == generation_context.requirements
    assert design.source_uml_elements == generation_context.uml_elements
    assert design.requirement_uml_anchors == generation_context.requirement_uml_anchors
    assert design.ui_artifacts == generation_context.ui_artifacts
    assert design.srs_version == generation_context.srs_version
    assert design.upstream_provenance == generation_context.upstream_provenance


def test_supported_plantuml_subset_extracts_structure(
    generation_context: GenerationContext,
) -> None:
    design = DesignUnderstandingService().build(generation_context)

    classes = {parsed.name: parsed for parsed in design.classes}
    assert set(classes) == {"TraceabilityRecord", "GenerationFlow"}
    assert [attribute.name for attribute in classes["TraceabilityRecord"].attributes] == [
        "requirement_id",
        "uml_id",
    ]
    assert [method.name for method in classes["TraceabilityRecord"].methods] == [
        "link"
    ]
    assert classes["TraceabilityRecord"].methods[0].parameters[0].name == (
        "requirement_id"
    )
    assert len(design.relationships) == 1
    assert design.relationships[0].source_class == "TraceabilityRecord"
    assert design.relationships[0].target_class == "GenerationFlow"
    assert design.relationships[0].relationship_type == "ASSOCIATION"


def test_unsupported_plantuml_construct_fails_explicitly(
    generation_context: GenerationContext,
) -> None:
    unsupported = _with_plantuml(
        generation_context,
        "@startuml\ninterface Traceable\n@enduml",
    )

    with pytest.raises(ApplicationError) as captured:
        DesignUnderstandingService().build(unsupported)

    assert captured.value.status_code == 422
    assert captured.value.errors[0].code == "UNSUPPORTED_PLANTUML_CONSTRUCT"


def test_missing_class_diagram_fails_explicitly(
    generation_context: GenerationContext,
) -> None:
    missing = _with_plantuml(
        generation_context,
        None,
        element_type="SEQUENCE_DIAGRAM",
    )

    with pytest.raises(ApplicationError) as captured:
        DesignUnderstandingService().build(missing)

    assert captured.value.errors[0].code == "MISSING_CLASS_DIAGRAM"


def test_missing_class_diagram_source_fails_explicitly(
    generation_context: GenerationContext,
) -> None:
    missing = _with_plantuml(generation_context, None)

    with pytest.raises(ApplicationError) as captured:
        DesignUnderstandingService().build(missing)

    assert captured.value.errors[0].code == "MISSING_PLANTUML_SOURCE"
