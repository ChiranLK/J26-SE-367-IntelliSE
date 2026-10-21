"""Compatibility boundary tests for the currently available upstream shapes."""

import pytest
from pydantic import ValidationError

from intelise_c3.contracts.provisional_input import C1ApprovedSRS, C2DesignRelease


def test_tracked_c1_extraction_shape_is_not_falsely_accepted_as_approved_srs() -> None:
    tracked_c1_extraction_shape = {
        "run_id": "example-run",
        "project_id": "example-project",
        "source_discussion_hash": "0" * 64,
        "created_at": "2026-10-19T00:00:00Z",
        "model_identifier": "example-model",
        "prompt_version": "c1-atomic-evidence-v1",
        "candidates": [
            {
                "requirement_id": "example-requirement",
                "requirement_text": "Users can create records.",
                "evidence": [{"quote": "Users can create records.", "start": 0, "end": 25}],
                "actor": "Users",
                "action": "create records",
                "review_status": "unreviewed",
            }
        ],
    }

    with pytest.raises(ValidationError) as captured:
        C1ApprovedSRS.model_validate(tracked_c1_extraction_shape)

    missing = {error["loc"][0] for error in captured.value.errors() if error["type"] == "missing"}
    assert {
        "contract_version",
        "srs_version",
        "approval_status",
        "approval_provenance_ref",
        "validation_report_ref",
        "requirements",
    }.issubset(missing)


def test_c3_does_not_treat_a_plantuml_document_as_a_complete_c2_release() -> None:
    with pytest.raises(ValidationError):
        C2DesignRelease.model_validate(
            {
                "uml_elements": [
                    {
                        "uml_id": "UML-EXAMPLE",
                        "element_type": "CLASS_DIAGRAM",
                        "name": "Example",
                        "plantuml_source": "@startuml\nclass Example\n@enduml",
                    }
                ]
            }
        )
