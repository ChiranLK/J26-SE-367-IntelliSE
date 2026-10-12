"""Tests for deterministic, evidence-based four-candidate stack selection."""

import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.stack_selection import (
    ArchitectureStyle,
    BackendRuntime,
    BackendTechnology,
    CriterionEvidence,
    FrontendTechnology,
    SelectionEvidence,
    StackSelectionCriteria,
    StackSelectionRequest,
    TeamProficiency,
)
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.stack_selection import GeneratorAvailability, SelectionWeights
from intelise_c3.services.stack_selection import StackSelectionService


def _evidence() -> SelectionEvidence:
    return SelectionEvidence(
        requirements=CriterionEvidence(
            reference="SIMULATED-REQUIREMENTS-EVIDENCE",
            confidence=1.0,
        ),
        architecture=CriterionEvidence(
            reference="SIMULATED-ARCHITECTURE-EVIDENCE",
            confidence=1.0,
        ),
        team=CriterionEvidence(
            reference="SIMULATED-TEAM-EVIDENCE",
            confidence=1.0,
        ),
        deployment=CriterionEvidence(
            reference="SIMULATED-DEPLOYMENT-EVIDENCE",
            confidence=1.0,
        ),
    )


def _criteria(**updates: object) -> StackSelectionCriteria:
    values: dict[str, object] = {
        "architecture_style": ArchitectureStyle.REST_SPA,
        "team_proficiency": TeamProficiency(
            react=0.5,
            angular=0.5,
            node_js=0.5,
            spring_boot=0.5,
        ),
        "available_backend_runtimes": (BackendRuntime.NODE, BackendRuntime.JVM),
        "supports_static_spa": True,
        "evidence": _evidence(),
    }
    values.update(updates)
    return StackSelectionCriteria.model_validate(values)


def test_scoring_is_deterministic_and_evaluates_exactly_four_candidates(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            preferred_frontend=FrontendTechnology.REACT,
            preferred_backend=BackendTechnology.NODE_JS,
        ),
    )
    service = StackSelectionService()

    first = service.select(request)
    second = service.select(request)

    assert first == second
    assert first.evaluated_candidate_count == 4
    assert len(first.rejected_alternatives) == 3
    assert first.selected_stack.candidate.candidate_id == "react-nodejs"
    assert first.selected_stack.october_21_mvp_generator_target is True
    assert (
        first.selected_stack.generator_availability
        is GeneratorAvailability.NOT_IMPLEMENTED
    )
    assert sum(first.criteria_weights.model_dump().values()) == pytest.approx(1.0)
    assert [
        item.candidate.candidate_id for item in first.candidate_calculations
    ] == [
        "react-nodejs",
        "angular-nodejs",
        "react-spring-boot",
        "angular-spring-boot",
    ]
    assert all(
        len(item.criterion_scores) == 4 for item in first.candidate_calculations
    )
    assert all(
        score.calculation_status == "CALCULATED"
        and score.weight_classification
        == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
        and score.confidence_classification
        == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
        for item in first.candidate_calculations
        for score in item.criterion_scores
    )
    assert (
        first.configured_scoring_assumptions.classification
        == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    assumptions = first.configured_scoring_assumptions
    assert assumptions.weights.model_dump() == {
        "requirement_fit": 0.35,
        "architectural_fit": 0.25,
        "team_fit": 0.20,
        "deployment_compatibility": 0.20,
    }
    architecture_scores = [
        item.model_dump(exclude={"classification"})
        for item in assumptions.architecture_scores
    ]
    assert architecture_scores == [
        {
            "architecture_style": "RAPID_MVP",
            "react": 0.95,
            "angular": 0.75,
            "node_js": 0.95,
            "spring_boot": 0.65,
        },
        {
            "architecture_style": "REST_SPA",
            "react": 0.90,
            "angular": 0.90,
            "node_js": 0.90,
            "spring_boot": 0.90,
        },
        {
            "architecture_style": "ENTERPRISE_LAYERED",
            "react": 0.80,
            "angular": 0.95,
            "node_js": 0.70,
            "spring_boot": 1.00,
        },
    ]
    assert assumptions.preference_match_score == pytest.approx(1.0)
    assert assumptions.preference_mismatch_score == pytest.approx(0.5)
    assert assumptions.no_preference_score == pytest.approx(1.0)
    assert assumptions.preferred_or_unspecified_runtime_score == pytest.approx(1.0)
    assert assumptions.non_preferred_runtime_score == pytest.approx(0.6)
    assert all(
        item.classification == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
        for item in assumptions.architecture_scores
    )
    assert (
        first.criteria_weights_classification
        == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    assert (
        first.tie_break_policy_classification
        == "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    assert first.researcher_approval.status == "PENDING_RESEARCHER_APPROVAL"


def test_hard_constraints_reject_incompatible_candidates(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            required_frontend=FrontendTechnology.ANGULAR,
            required_backend=BackendTechnology.NODE_JS,
            available_backend_runtimes=(BackendRuntime.NODE,),
        ),
    )

    report = StackSelectionService().select(request)

    assert report.selected_stack.candidate.candidate_id == "angular-nodejs"
    rejected = {
        item.candidate.candidate_id: item for item in report.rejected_alternatives
    }
    assert not rejected["react-nodejs"].eligible
    assert rejected["react-nodejs"].hard_constraint_failures
    assert not rejected["angular-spring-boot"].eligible


def test_hard_constraints_override_even_maximum_scoring_weight(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            required_frontend=FrontendTechnology.ANGULAR,
            required_backend=BackendTechnology.NODE_JS,
            team_proficiency=TeamProficiency(
                react=1.0,
                angular=0.0,
                node_js=1.0,
                spring_boot=0.0,
            ),
            available_backend_runtimes=(BackendRuntime.NODE,),
        ),
    )
    provisional_team_only_weights = SelectionWeights(
        requirement_fit=0.0,
        architectural_fit=0.0,
        team_fit=1.0,
        deployment_compatibility=0.0,
    )

    report = StackSelectionService(weights=provisional_team_only_weights).select(
        request
    )

    assert report.selected_stack.candidate.candidate_id == "angular-nodejs"
    disallowed = next(
        item
        for item in report.candidate_calculations
        if item.candidate.candidate_id == "react-nodejs"
    )
    assert disallowed.normalized_score > report.selected_stack.normalized_score
    assert disallowed.eligible is False
    assert disallowed.hard_constraint_failures


def test_equal_scores_use_documented_tie_break_order(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(),
    )

    service = StackSelectionService()
    first = service.select(request)
    second = service.select(request)

    assert first == second
    assert first.selected_stack.candidate.candidate_id == "react-nodejs"
    assert "score tie" in first.selection_reason
    assert "canonical" in first.tie_break_policy
    assert first.configured_scoring_assumptions.tie_break_order == (
        "react-nodejs",
        "angular-nodejs",
        "react-spring-boot",
        "angular-spring-boot",
    )


def test_changing_provisional_weights_can_change_selected_stack(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            preferred_frontend=FrontendTechnology.REACT,
            preferred_backend=BackendTechnology.NODE_JS,
            architecture_style=ArchitectureStyle.ENTERPRISE_LAYERED,
            team_proficiency=TeamProficiency(
                react=0.1,
                angular=1.0,
                node_js=0.1,
                spring_boot=1.0,
            ),
            preferred_backend_runtime=BackendRuntime.JVM,
        ),
    )
    provisional_preference_heavy_weights = SelectionWeights(
        requirement_fit=0.8,
        architectural_fit=0.05,
        team_fit=0.05,
        deployment_compatibility=0.1,
    )

    default_report = StackSelectionService().select(request)
    sensitivity_report = StackSelectionService(
        weights=provisional_preference_heavy_weights
    ).select(request)

    assert default_report.selected_stack.candidate.candidate_id == (
        "angular-spring-boot"
    )
    assert sensitivity_report.selected_stack.candidate.candidate_id == (
        "react-nodejs"
    )
    assert (
        sensitivity_report.configured_scoring_assumptions.weights
        == provisional_preference_heavy_weights
    )


def test_evidence_uncertainty_reduces_criterion_contribution(
    design_context: DesignContext,
) -> None:
    uncertain_evidence = _evidence().model_copy(
        update={
            "team": CriterionEvidence(
                reference="SIMULATED-UNCERTAIN-TEAM-EVIDENCE",
                confidence=0.25,
                uncertainty_notes="Provisional self-assessment",
            )
        }
    )
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(evidence=uncertain_evidence),
    )

    report = StackSelectionService().select(request)

    team_score = next(
        score
        for score in report.selected_stack.criterion_scores
        if score.criterion == "team_fit"
    )
    assert team_score.uncertainty_adjusted_score == pytest.approx(
        team_score.raw_score * 0.25
    )
    assert team_score.uncertainty_notes == "Provisional self-assessment"
    uncertainty = next(
        item for item in report.uncertainty.items if item.criterion == "team_fit"
    )
    assert uncertainty.confidence == pytest.approx(0.25)
    assert "provisional" in uncertainty.interpretation.lower()
    assert report.uncertainty.evidence_references_verified is False
    observed_team = next(
        item
        for item in report.observed_input_evidence.evidence_items
        if item.criterion == "team_fit"
    )
    assert observed_team.evidence_status == "CALLER_SUPPLIED_UNVERIFIED"
    assert observed_team.confidence_classification == (
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    )


def test_unavailable_generator_is_reported_without_substitution(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            required_frontend=FrontendTechnology.ANGULAR,
            required_backend=BackendTechnology.NODE_JS,
            available_backend_runtimes=(BackendRuntime.NODE,),
        ),
    )

    report = StackSelectionService().select(request)

    assert report.selected_stack.candidate.candidate_id == "angular-nodejs"
    assert (
        report.selected_stack.generator_availability
        is GeneratorAvailability.NOT_IMPLEMENTED
    )


def test_all_candidates_rejected_fails_explicitly(
    design_context: DesignContext,
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            required_backend=BackendTechnology.SPRING_BOOT,
            available_backend_runtimes=(BackendRuntime.NODE,),
        ),
    )

    with pytest.raises(ApplicationError) as captured:
        StackSelectionService().select(request)

    assert captured.value.status_code == 409
    assert captured.value.errors[0].code == "NO_COMPATIBLE_STACK"


def test_stack_selection_endpoint_returns_evidence_report(
    client: TestClient, design_context: DesignContext
) -> None:
    request = StackSelectionRequest(
        design_context=design_context,
        criteria=_criteria(
            preferred_frontend=FrontendTechnology.REACT,
            preferred_backend=BackendTechnology.NODE_JS,
        ),
    )

    response = client.post(
        "/api/v1/stack-selection",
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report_version"] == "1.0"
    assert body["selected_stack"]["candidate"]["candidate_id"] == "react-nodejs"
    assert body["manual_approval_required"] is True
    assert body["observed_input_evidence"]["evidence_status"] == (
        "CALLER_SUPPLIED_UNVERIFIED"
    )
    assert body["configured_scoring_assumptions"]["classification"] == (
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    assert len(body["candidate_calculations"]) == 4
    assert len(body["uncertainty"]["items"]) == 4
    assert body["researcher_approval"]["status"] == (
        "PENDING_RESEARCHER_APPROVAL"
    )
