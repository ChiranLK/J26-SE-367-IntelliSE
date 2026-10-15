"""Deterministic and explainable FR-C3-02 stack-selection policy."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import status

from intelise_c3.contracts.stack_selection import (
    ArchitectureStyle,
    BackendRuntime,
    BackendTechnology,
    CriterionEvidence,
    FrontendTechnology,
    StackSelectionRequest,
    Technology,
)
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.stack_selection import (
    ArchitectureScoreAssumption,
    CandidateEvaluation,
    CandidateStack,
    ConfiguredScoringAssumptions,
    CriterionScore,
    GeneratorAvailability,
    ObservedEvidenceItem,
    ObservedInputEvidence,
    ObservedTeamProficiency,
    ResearcherApproval,
    SelectionWeights,
    StackSelectionReport,
    UncertaintyItem,
    UncertaintySummary,
)

STACK_SELECTION_POLICY_VERSION = "1.0"
TIE_BREAK_POLICY = (
    "Equal normalized scores use the canonical research-candidate order: "
    "React+Node.js, Angular+Node.js, React+Spring Boot, Angular+Spring Boot."
)

_WEIGHTS = {
    "requirement_fit": 0.35,
    "architectural_fit": 0.25,
    "team_fit": 0.20,
    "deployment_compatibility": 0.20,
}

_ARCHITECTURE_COMPATIBILITY = {
    ArchitectureStyle.RAPID_MVP: {
        Technology.REACT: 0.95,
        Technology.ANGULAR: 0.75,
        Technology.NODE_JS: 0.95,
        Technology.SPRING_BOOT: 0.65,
    },
    ArchitectureStyle.REST_SPA: {
        Technology.REACT: 0.90,
        Technology.ANGULAR: 0.90,
        Technology.NODE_JS: 0.90,
        Technology.SPRING_BOOT: 0.90,
    },
    ArchitectureStyle.ENTERPRISE_LAYERED: {
        Technology.REACT: 0.80,
        Technology.ANGULAR: 0.95,
        Technology.NODE_JS: 0.70,
        Technology.SPRING_BOOT: 1.00,
    },
}


@dataclass(frozen=True)
class _CandidateDefinition:
    candidate_id: str
    frontend: FrontendTechnology
    backend: BackendTechnology


_CANDIDATES = (
    _CandidateDefinition("react-nodejs", FrontendTechnology.REACT, BackendTechnology.NODE_JS),
    _CandidateDefinition(
        "angular-nodejs", FrontendTechnology.ANGULAR, BackendTechnology.NODE_JS
    ),
    _CandidateDefinition(
        "react-spring-boot", FrontendTechnology.REACT, BackendTechnology.SPRING_BOOT
    ),
    _CandidateDefinition(
        "angular-spring-boot",
        FrontendTechnology.ANGULAR,
        BackendTechnology.SPRING_BOOT,
    ),
)


class StackSelectionService:
    """Score exactly four candidates; never substitute based on generator support."""

    def __init__(self, *, weights: SelectionWeights | None = None) -> None:
        """Use the documented default policy or explicit research-test weights."""
        self._weights = weights or SelectionWeights(**_WEIGHTS)
        values = self._weights.model_dump().values()
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("Each selection weight must be between 0 and 1.")
        if abs(sum(values) - 1.0) > 1e-9:
            raise ValueError("Selection weights must sum to 1.0.")

    def select(self, request: StackSelectionRequest) -> StackSelectionReport:
        """Return the highest eligible evidence-adjusted candidate and alternatives."""
        evaluations = tuple(
            self._evaluate(candidate, request) for candidate in _CANDIDATES
        )
        eligible = [evaluation for evaluation in evaluations if evaluation.eligible]
        if not eligible:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="NO_COMPATIBLE_STACK",
                        field="criteria",
                        message=(
                            "All four technology combinations violate one or more "
                            "hard compatibility constraints."
                        ),
                    )
                ],
                status_code=status.HTTP_409_CONFLICT,
            )

        priority = {
            candidate.candidate_id: index for index, candidate in enumerate(_CANDIDATES)
        }
        ranked = sorted(
            eligible,
            key=lambda evaluation: (
                -evaluation.normalized_score,
                priority[evaluation.candidate.candidate_id],
            ),
        )
        selected = ranked[0]
        tied = [
            evaluation
            for evaluation in eligible
            if evaluation.normalized_score == selected.normalized_score
        ]
        if len(tied) > 1:
            selection_reason = (
                f"{selected.candidate.candidate_id} won a {len(tied)}-candidate "
                "score tie using the documented canonical order."
            )
        else:
            selection_reason = (
                f"{selected.candidate.candidate_id} has the highest normalized "
                "score among eligible candidates."
            )

        selected = selected.model_copy(
            update={"decision_reason": selection_reason}
        )
        alternatives: list[CandidateEvaluation] = []
        for evaluation in evaluations:
            if evaluation.candidate.candidate_id == selected.candidate.candidate_id:
                continue
            if not evaluation.eligible:
                reason = "Rejected by hard compatibility constraint(s)."
            elif evaluation.normalized_score == selected.normalized_score:
                reason = "Rejected by the documented deterministic tie-break policy."
            else:
                reason = "Rejected because its normalized score is lower."
            alternatives.append(evaluation.model_copy(update={"decision_reason": reason}))

        final_evaluations = {
            evaluation.candidate.candidate_id: evaluation
            for evaluation in (selected, *alternatives)
        }
        candidate_calculations = tuple(
            final_evaluations[candidate.candidate_id] for candidate in _CANDIDATES
        )

        return StackSelectionReport(
            design_context_version=request.design_context.design_context_version,
            project_id=request.design_context.project_id,
            criteria_weights=self._weights,
            observed_input_evidence=self._observed_input_evidence(request),
            configured_scoring_assumptions=self._configured_assumptions(),
            candidate_calculations=candidate_calculations,
            uncertainty=self._uncertainty_summary(request),
            selected_stack=selected,
            rejected_alternatives=tuple(alternatives),
            tie_break_policy=TIE_BREAK_POLICY,
            selection_reason=selection_reason,
            manual_approval_reasons=(
                "C1/C2 contracts and evidence references remain provisional.",
                "Criteria values, confidence levels, and policy weights require review.",
                "A human must approve the selected stack before code generation.",
                (
                    "Task 6 implements only the React + Node.js MVP generator; "
                    "Angular and Spring Boot combinations remain NOT_IMPLEMENTED."
                ),
            ),
            researcher_approval=ResearcherApproval(
                decisions=(
                    "Approve or revise the scoring weights.",
                    "Approve or revise the architecture compatibility scores.",
                    "Approve or revise preference and deployment penalties.",
                    "Approve the supplied evidence confidence values.",
                    "Approve or revise the deterministic tie-break order.",
                    "Approve the selected stack before downstream generation.",
                )
            ),
        )

    def _evaluate(
        self, candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> CandidateEvaluation:
        criteria = request.criteria
        failures = self._hard_constraint_failures(candidate, request)
        criterion_scores = (
            self._criterion_score(
                "requirement_fit",
                self._requirement_fit(candidate, request),
                criteria.evidence.requirements,
                self._requirement_reason(candidate, request),
            ),
            self._criterion_score(
                "architectural_fit",
                self._architecture_fit(candidate, request),
                criteria.evidence.architecture,
                (
                    f"Uses the policy matrix for "
                    f"{criteria.architecture_style.value}."
                ),
            ),
            self._criterion_score(
                "team_fit",
                self._team_fit(candidate, request),
                criteria.evidence.team,
                "Average of the supplied frontend and backend proficiency values.",
            ),
            self._criterion_score(
                "deployment_compatibility",
                self._deployment_fit(candidate, request),
                criteria.evidence.deployment,
                "Matches declared runtime availability and deployment preference.",
            ),
        )
        normalized_score = round(
            sum(score.weighted_score for score in criterion_scores), 6
        )
        candidate_stack = CandidateStack(
            candidate_id=candidate.candidate_id,
            frontend=candidate.frontend.value,
            backend=candidate.backend.value,
        )
        return CandidateEvaluation(
            candidate=candidate_stack,
            eligible=not failures,
            normalized_score=normalized_score,
            hard_constraint_failures=tuple(failures),
            criterion_scores=criterion_scores,
            generator_availability=(
                GeneratorAvailability.IMPLEMENTED
                if self._is_mvp_generator_target(candidate)
                else GeneratorAvailability.NOT_IMPLEMENTED
            ),
            october_21_mvp_generator_target=self._is_mvp_generator_target(candidate),
            decision_reason=(
                "Eligible pending comparison."
                if not failures
                else "Rejected by hard compatibility constraint(s)."
            ),
        )

    @staticmethod
    def _hard_constraint_failures(
        candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> list[str]:
        criteria = request.criteria
        failures: list[str] = []
        requirement_ref = criteria.evidence.requirements.reference
        deployment_ref = criteria.evidence.deployment.reference

        if (
            criteria.required_frontend is not None
            and candidate.frontend is not criteria.required_frontend
        ):
            failures.append(
                f"Required frontend is {criteria.required_frontend.value} "
                f"(evidence: {requirement_ref})."
            )
        if (
            criteria.required_backend is not None
            and candidate.backend is not criteria.required_backend
        ):
            failures.append(
                f"Required backend is {criteria.required_backend.value} "
                f"(evidence: {requirement_ref})."
            )

        candidate_technologies = {
            Technology(candidate.frontend.value),
            Technology(candidate.backend.value),
        }
        prohibited = candidate_technologies.intersection(
            criteria.prohibited_technologies
        )
        if prohibited:
            failures.append(
                "Contains prohibited technology/technologies "
                + ", ".join(sorted(item.value for item in prohibited))
                + f" (evidence: {requirement_ref})."
            )

        required_runtime = (
            BackendRuntime.NODE
            if candidate.backend is BackendTechnology.NODE_JS
            else BackendRuntime.JVM
        )
        if required_runtime not in criteria.available_backend_runtimes:
            failures.append(
                f"Required runtime {required_runtime.value} is unavailable "
                f"(evidence: {deployment_ref})."
            )
        if not criteria.supports_static_spa:
            failures.append(
                "Static SPA delivery is unavailable for both supported frontends "
                f"(evidence: {deployment_ref})."
            )
        return failures

    @staticmethod
    def _requirement_fit(
        candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> float:
        preferences: list[float] = []
        if request.criteria.preferred_frontend is not None:
            preferences.append(
                1.0
                if candidate.frontend is request.criteria.preferred_frontend
                else 0.5
            )
        if request.criteria.preferred_backend is not None:
            preferences.append(
                1.0
                if candidate.backend is request.criteria.preferred_backend
                else 0.5
            )
        return sum(preferences) / len(preferences) if preferences else 1.0

    @staticmethod
    def _requirement_reason(
        candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> str:
        if (
            request.criteria.preferred_frontend is None
            and request.criteria.preferred_backend is None
        ):
            return "No soft technology preference was asserted; score remains neutral."
        return (
            "Compares the candidate with the explicitly supplied soft frontend and "
            "backend preferences."
        )

    @staticmethod
    def _architecture_fit(
        candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> float:
        matrix = _ARCHITECTURE_COMPATIBILITY[request.criteria.architecture_style]
        return (
            matrix[Technology(candidate.frontend.value)]
            + matrix[Technology(candidate.backend.value)]
        ) / 2

    @staticmethod
    def _team_fit(candidate: _CandidateDefinition, request: StackSelectionRequest) -> float:
        proficiency = request.criteria.team_proficiency
        frontend_score = (
            proficiency.react
            if candidate.frontend is FrontendTechnology.REACT
            else proficiency.angular
        )
        backend_score = (
            proficiency.node_js
            if candidate.backend is BackendTechnology.NODE_JS
            else proficiency.spring_boot
        )
        return (frontend_score + backend_score) / 2

    @staticmethod
    def _deployment_fit(
        candidate: _CandidateDefinition, request: StackSelectionRequest
    ) -> float:
        preferred_runtime = request.criteria.preferred_backend_runtime
        if preferred_runtime is None:
            return 1.0
        candidate_runtime = (
            BackendRuntime.NODE
            if candidate.backend is BackendTechnology.NODE_JS
            else BackendRuntime.JVM
        )
        return 1.0 if candidate_runtime is preferred_runtime else 0.6

    def _criterion_score(
        self,
        criterion: str,
        raw_score: float,
        evidence: CriterionEvidence,
        reason: str,
    ) -> CriterionScore:
        adjusted = raw_score * evidence.confidence
        return CriterionScore(
            criterion=criterion,
            weight=getattr(self._weights, criterion),
            raw_score=round(raw_score, 6),
            confidence=evidence.confidence,
            uncertainty_adjusted_score=round(adjusted, 6),
            weighted_score=round(
                adjusted * getattr(self._weights, criterion), 6
            ),
            evidence_ref=evidence.reference,
            reason=reason,
            uncertainty_notes=evidence.uncertainty_notes,
        )

    @staticmethod
    def _observed_input_evidence(
        request: StackSelectionRequest,
    ) -> ObservedInputEvidence:
        criteria = request.criteria
        evidence = criteria.evidence
        return ObservedInputEvidence(
            required_frontend=(
                criteria.required_frontend.value
                if criteria.required_frontend is not None
                else None
            ),
            required_backend=(
                criteria.required_backend.value
                if criteria.required_backend is not None
                else None
            ),
            preferred_frontend=(
                criteria.preferred_frontend.value
                if criteria.preferred_frontend is not None
                else None
            ),
            preferred_backend=(
                criteria.preferred_backend.value
                if criteria.preferred_backend is not None
                else None
            ),
            prohibited_technologies=tuple(
                technology.value for technology in criteria.prohibited_technologies
            ),
            architecture_style=criteria.architecture_style.value,
            team_proficiency=ObservedTeamProficiency(
                **criteria.team_proficiency.model_dump()
            ),
            available_backend_runtimes=tuple(
                runtime.value for runtime in criteria.available_backend_runtimes
            ),
            supports_static_spa=criteria.supports_static_spa,
            preferred_backend_runtime=(
                criteria.preferred_backend_runtime.value
                if criteria.preferred_backend_runtime is not None
                else None
            ),
            evidence_items=tuple(
                ObservedEvidenceItem(
                    criterion=name,
                    reference=item.reference,
                    confidence=item.confidence,
                    uncertainty_notes=item.uncertainty_notes,
                )
                for name, item in (
                    ("requirement_fit", evidence.requirements),
                    ("architectural_fit", evidence.architecture),
                    ("team_fit", evidence.team),
                    ("deployment_compatibility", evidence.deployment),
                )
            ),
        )

    def _configured_assumptions(self) -> ConfiguredScoringAssumptions:
        return ConfiguredScoringAssumptions(
            weights=self._weights,
            architecture_scores=tuple(
                ArchitectureScoreAssumption(
                    architecture_style=style.value,
                    react=scores[Technology.REACT],
                    angular=scores[Technology.ANGULAR],
                    node_js=scores[Technology.NODE_JS],
                    spring_boot=scores[Technology.SPRING_BOOT],
                )
                for style, scores in _ARCHITECTURE_COMPATIBILITY.items()
            ),
            preference_match_score=1.0,
            preference_mismatch_score=0.5,
            no_preference_score=1.0,
            preferred_or_unspecified_runtime_score=1.0,
            non_preferred_runtime_score=0.6,
            evidence_confidence_method=(
                "Multiply each raw criterion score by its caller-supplied "
                "confidence before applying the criterion weight."
            ),
            hard_constraints=(
                "Explicitly required frontend and backend must match.",
                "Explicitly prohibited technologies are ineligible.",
                "The candidate backend runtime must be available.",
                "Static SPA delivery must be supported.",
            ),
            tie_break_order=tuple(
                candidate.candidate_id for candidate in _CANDIDATES
            ),
            score_rounding_decimals=6,
        )

    @staticmethod
    def _uncertainty_summary(
        request: StackSelectionRequest,
    ) -> UncertaintySummary:
        evidence = request.criteria.evidence
        return UncertaintySummary(
            calculation_method=(
                "Each configured confidence value scales its raw criterion score; "
                "lower confidence reduces that criterion's calculated contribution."
            ),
            items=tuple(
                UncertaintyItem(
                    criterion=name,
                    confidence=item.confidence,
                    uncertainty_notes=item.uncertainty_notes,
                    interpretation=(
                        f"Confidence {item.confidence:.3f} is a provisional "
                        "research-policy input; its evidence reference has not "
                        "been independently verified by Component 3."
                    ),
                )
                for name, item in (
                    ("requirement_fit", evidence.requirements),
                    ("architectural_fit", evidence.architecture),
                    ("team_fit", evidence.team),
                    ("deployment_compatibility", evidence.deployment),
                )
            ),
        )

    @staticmethod
    def _is_mvp_generator_target(
        candidate: _CandidateDefinition,
    ) -> bool:
        return (
            candidate.frontend is FrontendTechnology.REACT
            and candidate.backend is BackendTechnology.NODE_JS
        )
