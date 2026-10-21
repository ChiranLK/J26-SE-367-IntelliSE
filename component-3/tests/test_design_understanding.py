"""Tests for deterministic design understanding from GenerationContext."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.design_context import DesignContext, ParsedElementKind
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.services.design_understanding import DesignUnderstandingService

C2_FIXTURE = (
    Path(__file__).parent / "fixtures" / "simulated" / "c2" / "web_CLASS_final.puml"
)


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


# --- Real C2 calculator diagram (abstract class, enum, skinparam, CRLF) -----


def _calculator_source() -> str:
    raw = C2_FIXTURE.read_bytes().decode("utf-8")
    # Force CRLF regardless of any git line-ending conversion on checkout.
    return raw.replace("\r\n", "\n").replace("\n", "\r\n")


def _calculator_design(generation_context: GenerationContext) -> DesignContext:
    return DesignUnderstandingService().build(
        _with_plantuml(generation_context, _calculator_source())
    )


def _signature(method) -> str:
    parameters = ",".join(f"{p.name}:{p.type_name}" for p in method.parameters)
    return f"{method.name}({parameters}):{method.return_type}"


def test_real_c2_fixture_is_59_lines() -> None:
    assert len(_calculator_source().split("\r\n")) - 1 == 59


def test_real_c2_calculator_diagram_has_nine_elements(
    generation_context: GenerationContext,
) -> None:
    design = _calculator_design(generation_context)

    assert [item.name for item in design.classes] == [
        "Operation",
        "Addition",
        "Subtraction",
        "Multiplication",
        "Division",
        "Calculation",
        "CalculationStatus",
        "History",
        "Calculator",
    ]
    assert len(design.relationships) == 8


def test_real_c2_abstract_class_and_enum_are_recorded(
    generation_context: GenerationContext,
) -> None:
    classes = {item.name: item for item in _calculator_design(generation_context).classes}

    assert classes["Operation"].is_abstract is True
    assert classes["Operation"].kind is ParsedElementKind.CLASS
    assert [a.name for a in classes["Operation"].attributes] == ["symbol"]
    assert all(
        not item.is_abstract for name, item in classes.items() if name != "Operation"
    )

    status = classes["CalculationStatus"]
    assert status.kind is ParsedElementKind.ENUM
    assert status.values == ("SUCCESS", "ERROR")
    assert status.attributes == ()
    assert status.methods == ()
    assert all(
        item.kind is ParsedElementKind.CLASS
        for name, item in classes.items()
        if name != "CalculationStatus"
    )


def test_real_c2_relationships_are_preserved(
    generation_context: GenerationContext,
) -> None:
    relationships = {
        (r.source_class, r.target_class): r
        for r in _calculator_design(generation_context).relationships
    }

    for operation in ("Addition", "Subtraction", "Multiplication", "Division"):
        inheritance = relationships[("Operation", operation)]
        assert inheritance.connector == "<|--"
        assert inheritance.relationship_type == "INHERITANCE"
        assert inheritance.source_multiplicity is None
        assert inheritance.target_multiplicity is None
        assert inheritance.label is None

    uses = relationships[("Calculation", "Operation")]
    assert (uses.relationship_type, uses.source_multiplicity) == ("ASSOCIATION", "1")
    assert (uses.target_multiplicity, uses.label) == ("1", "uses")

    contains = relationships[("History", "Calculation")]
    assert contains.relationship_type == "COMPOSITION"
    assert contains.connector == "*--"
    assert (contains.source_multiplicity, contains.target_multiplicity) == ("1", "0..*")
    assert contains.label == "contains"

    has_history = relationships[("Calculator", "History")]
    assert has_history.relationship_type == "ASSOCIATION"
    assert has_history.label == "has"

    assert relationships[("Calculation", "CalculationStatus")].label == "has"


def test_real_c2_member_signatures_are_intact(
    generation_context: GenerationContext,
) -> None:
    classes = {item.name: item for item in _calculator_design(generation_context).classes}

    assert [_signature(m) for m in classes["Addition"].methods] == [
        "calculate(firstNumber:double,secondNumber:double):double"
    ]
    assert [_signature(m) for m in classes["Calculation"].methods] == [
        "calculate():void"
    ]
    assert [(a.name, a.type_name) for a in classes["Calculation"].attributes] == [
        ("firstNumber", "double"),
        ("secondNumber", "double"),
        ("result", "double"),
        ("status", "String"),
    ]
    assert [_signature(m) for m in classes["Calculator"].methods] == [
        "enterNumber(number:double):void",
        "selectOperation(operation:Operation):void",
        "calculateResult():void",
        "clearHistory():void",
    ]
    assert [_signature(m) for m in classes["History"].methods] == [
        "addCalculation(calculation:Calculation):void"
    ]


def test_skinparam_line_has_no_model_effect(
    generation_context: GenerationContext,
) -> None:
    with_skin = DesignUnderstandingService().build(
        _with_plantuml(
            generation_context,
            "@startuml\nskinparam classAttributeIconSize 0\nclass A\n@enduml",
        )
    )
    without = DesignUnderstandingService().build(
        _with_plantuml(generation_context, "@startuml\nclass A\n@enduml")
    )

    assert with_skin.classes == without.classes
    assert with_skin.relationships == without.relationships


def test_skinparam_block_form_still_fails(
    generation_context: GenerationContext,
) -> None:
    with pytest.raises(ApplicationError) as captured:
        DesignUnderstandingService().build(
            _with_plantuml(
                generation_context, "@startuml\nskinparam class {\nclass A\n@enduml"
            )
        )

    assert captured.value.errors[0].code == "UNSUPPORTED_PLANTUML_CONSTRUCT"
    assert captured.value.errors[0].field.endswith("plantuml_source.line.2")


def test_unknown_line_in_real_diagram_fails_with_correct_line_number(
    generation_context: GenerationContext,
) -> None:
    lines = _calculator_source().split("\r\n")
    assert lines[49] == "Operation <|-- Addition"  # 1-based line 50
    lines.insert(49, "interface Traceable")  # the new line is now 1-based line 50

    with pytest.raises(ApplicationError) as captured:
        DesignUnderstandingService().build(
            _with_plantuml(generation_context, "\r\n".join(lines))
        )

    error = captured.value.errors[0]
    assert error.code == "UNSUPPORTED_PLANTUML_CONSTRUCT"
    assert error.field.endswith("plantuml_source.line.50")
    assert captured.value.status_code == 422


def test_enum_rejects_non_value_members_and_duplicates(
    generation_context: GenerationContext,
) -> None:
    for body, code, line in (
        ("enum E {\nA : int\n}", "UNSUPPORTED_PLANTUML_MEMBER", 3),
        ("enum E {\nA\nA\n}", "DUPLICATE_ENUM_VALUE", 4),
    ):
        with pytest.raises(ApplicationError) as captured:
            DesignUnderstandingService().build(
                _with_plantuml(generation_context, f"@startuml\n{body}\n@enduml")
            )
        assert captured.value.errors[0].code == code
        assert captured.value.errors[0].field.endswith(f"plantuml_source.line.{line}")


def test_abstract_class_and_enum_are_rejected_by_crud_spec(
    generation_context: GenerationContext,
) -> None:
    for body, kind in (
        ("abstract class Thing {\n  - id : String\n}", "abstract class"),
        ("enum Status {\n  A\n}", "enum"),
    ):
        design = DesignUnderstandingService().build(
            _with_plantuml(generation_context, f"@startuml\n{body}\n@enduml")
        )
        with pytest.raises(ApplicationError) as captured:
            CrudApplicationSpecBuilder().build(design)
        assert captured.value.errors[0].code == "UNSUPPORTED_CRUD_CLASS_KIND"
        assert kind in captured.value.errors[0].message


def test_plain_class_serialization_is_unchanged_by_new_fields(
    generation_context: GenerationContext,
) -> None:
    dumped = DesignUnderstandingService().build(generation_context).model_dump(mode="json")

    for item in dumped["classes"]:
        assert set(item) == {"source_uml_id", "name", "attributes", "methods"}
