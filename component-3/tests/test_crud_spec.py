"""Tests for deterministic DesignContext to CRUD-spec translation."""

import json
from pathlib import Path

import pytest

from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.crud_spec import CrudOperation, CrudScalarType
from intelise_c3.generation.crud_templates import render_crud_application
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService

FIXTURES = Path(__file__).parent / "fixtures" / "simulated"


def _payload(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}_input_package.json").read_text(encoding="utf-8"))


def _spec(name: str):
    package = ProvisionalInputPackage.model_validate(_payload(name))
    generation = InputValidationService().validate(package)
    design = DesignUnderstandingService().build(generation)
    return CrudApplicationSpecBuilder().build(design)


@pytest.mark.parametrize(
    ("fixture", "application_name", "entities"),
    (
        ("student_management", "Student Management", ("Student",)),
        ("library_management", "Library Management", ("Book", "Member")),
        ("inventory_management", "Inventory Management", ("InventoryItem",)),
    ),
)
def test_supported_inputs_build_different_specs(
    fixture: str,
    application_name: str,
    entities: tuple[str, ...],
) -> None:
    spec = _spec(fixture)

    assert spec.spec_version == "1.0"
    assert spec.application_name == application_name
    assert tuple(entity.class_name for entity in spec.entities) == entities
    assert all(entity.operations == tuple(CrudOperation) for entity in spec.entities)
    assert all(entity.requirement_ids for entity in spec.entities)
    assert all(entity.design_anchor_ids for entity in spec.entities)


def test_supported_scalar_types_are_normalized_from_uml() -> None:
    student = _spec("student_management").entities[0]

    assert {field.name: field.scalar_type for field in student.fields} == {
        "id": CrudScalarType.STRING,
        "name": CrudScalarType.STRING,
        "age": CrudScalarType.INTEGER,
        "gpa": CrudScalarType.NUMBER,
        "enrolled": CrudScalarType.BOOLEAN,
        "birthDate": CrudScalarType.DATE,
    }
    assert next(field for field in student.fields if field.name == "id").generated


def test_renderer_uses_the_spec_for_fields_validation_routes_and_sql() -> None:
    rendered = render_crud_application(_spec("student_management"))
    artifacts = {item.relative_path: item.content for item in rendered.artifacts}

    form = artifacts["frontend/src/components/StudentForm.jsx"]
    assert 'name="age" type="number" step="1"' in form
    assert 'name="gpa" type="number" step="any"' in form
    assert 'name="enrolled" type="checkbox"' in form
    assert 'name="birthDate" type="date"' in form

    service = artifacts["backend/src/services/studentService.js"]
    assert "Number.isInteger(input.age)" in service
    assert "Number.isFinite(input.gpa)" in service
    assert "typeof input.enrolled !== 'boolean'" in service
    assert "INVALID_STUDENT_INPUT" in service
    assert "INVALID_CRUD_INPUT" not in service
    assert "globalThis.crypto.randomUUID()" in service
    assert "const isUuid = (id)" in service

    routes = artifacts["backend/src/app.js"]
    assert "app.use('/api/v1/students'" in routes
    assert "process.env.HOST ?? '127.0.0.1'" in routes
    api_client = artifacts["frontend/src/api/student.js"]
    assert "import.meta.env.VITE_API_BASE_URL" in api_client
    schema = artifacts["backend/src/db/schema.sql"]
    assert "CREATE TABLE IF NOT EXISTS students" in schema
    assert "age INTEGER NOT NULL" in schema
    assert "gpa REAL NOT NULL" in schema


def test_renderer_openapi_is_parseable_and_matches_two_entity_spec() -> None:
    rendered = render_crud_application(_spec("library_management"))
    openapi_text = next(
        item.content
        for item in rendered.artifacts
        if item.relative_path == "api/openapi.yaml"
    )
    document = json.loads(openapi_text)

    assert set(document["paths"]) == {
        "/api/v1/books",
        "/api/v1/books/{id}",
        "/api/v1/members",
        "/api/v1/members/{id}",
    }
    assert "CreateBookRequest" in document["components"]["schemas"]
    assert "CreateMemberRequest" in document["components"]["schemas"]
    assert set(document["paths"]["/api/v1/books/{id}"]["delete"]["responses"]) == {
        "204",
        "400",
        "404",
    }


def test_unsupported_entity_relationship_is_rejected_explicitly() -> None:
    payload = _payload("student_management")
    source = payload["c2"]["uml_elements"][0]["plantuml_source"]
    payload["c2"]["uml_elements"][0]["plantuml_source"] = source.replace(
        "@enduml", "Student --> Student : mentors\n@enduml"
    )
    generation = InputValidationService().validate(
        ProvisionalInputPackage.model_validate(payload)
    )
    design = DesignUnderstandingService().build(generation)

    with pytest.raises(ApplicationError) as captured:
        CrudApplicationSpecBuilder().build(design)

    assert captured.value.errors[0].code == "UNSUPPORTED_CRUD_RELATIONSHIP"


def test_ambiguous_requirement_is_rejected_instead_of_guessed() -> None:
    payload = _payload("student_management")
    payload["c1"]["requirements"][0]["title"] = "Users can create and list records"
    generation = InputValidationService().validate(
        ProvisionalInputPackage.model_validate(payload)
    )
    design = DesignUnderstandingService().build(generation)

    with pytest.raises(ApplicationError) as captured:
        CrudApplicationSpecBuilder().build(design)

    assert captured.value.errors[0].code == "AMBIGUOUS_CRUD_REQUIREMENT"


def test_unsupported_field_type_is_rejected_instead_of_coerced() -> None:
    payload = _payload("student_management")
    source = payload["c2"]["uml_elements"][0]["plantuml_source"]
    payload["c2"]["uml_elements"][0]["plantuml_source"] = source.replace(
        "+gpa: Number", "+gpa: Json"
    )
    generation = InputValidationService().validate(
        ProvisionalInputPackage.model_validate(payload)
    )
    design = DesignUnderstandingService().build(generation)

    with pytest.raises(ApplicationError) as captured:
        CrudApplicationSpecBuilder().build(design)

    assert captured.value.errors[0].code == "UNSUPPORTED_CRUD_FIELD_TYPE"


def test_requirement_anchor_must_target_the_entity_source_diagram() -> None:
    payload = _payload("student_management")
    payload["c2"]["uml_elements"].append(
        {
            "uml_id": "UML-STUDENT-SEQUENCE-001",
            "element_type": "SEQUENCE_DIAGRAM",
            "name": "StudentSequence",
            "plantuml_source": "@startuml\nactor User\n@enduml",
        }
    )
    payload["c2"]["requirement_uml_anchors"][0]["uml_id"] = (
        "UML-STUDENT-SEQUENCE-001"
    )
    generation = InputValidationService().validate(
        ProvisionalInputPackage.model_validate(payload)
    )
    design = DesignUnderstandingService().build(generation)

    with pytest.raises(ApplicationError) as captured:
        CrudApplicationSpecBuilder().build(design)

    assert (
        captured.value.errors[0].code
        == "MISSING_ENTITY_DIAGRAM_CRUD_ANCHOR_EVIDENCE"
    )

