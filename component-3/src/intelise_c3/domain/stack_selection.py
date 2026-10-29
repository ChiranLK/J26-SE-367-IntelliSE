"""Immutable evidence report for FR-C3-02 technology-stack selection."""

from enum import StrEnum
from typing import Literal

from intelise_c3.domain.generation_context import DomainModel


class GeneratorAvailability(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class CandidateStack(DomainModel):
    candidate_id: str
    frontend: str
    backend: str


class SelectionWeights(DomainModel):
    requirement_fit: float
    architectural_fit: float
    team_fit: float
    deployment_compatibility: float


class ObservedEvidenceItem(DomainModel):
    criterion: str
    reference: str
    confidence: float
    uncertainty_notes: str | None = None
    evidence_status: Literal["CALLER_SUPPLIED_UNVERIFIED"] = (
        "CALLER_SUPPLIED_UNVERIFIED"
    )
    confidence_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"


class ObservedTeamProficiency(DomainModel):
    react: float
    angular: float
    node_js: float
    spring_boot: float


class ObservedInputEvidence(DomainModel):
    """Caller-declared inputs; references are recorded but not authenticated."""

    evidence_status: Literal["CALLER_SUPPLIED_UNVERIFIED"] = (
        "CALLER_SUPPLIED_UNVERIFIED"
    )
    required_frontend: str | None
    required_backend: str | None
    preferred_frontend: str | None
    preferred_backend: str | None
    prohibited_technologies: tuple[str, ...]
    architecture_style: str
    team_proficiency: ObservedTeamProficiency
    available_backend_runtimes: tuple[str, ...]
    supports_static_spa: bool
    preferred_backend_runtime: str | None
    evidence_items: tuple[ObservedEvidenceItem, ...]


class ArchitectureScoreAssumption(DomainModel):
    classification: Literal["PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"] = (
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    )
    architecture_style: str
    react: float
    angular: float
    node_js: float
    spring_boot: float


class ConfiguredScoringAssumptions(DomainModel):
    """Explicit values configured by policy rather than observed as facts."""

    classification: Literal["PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"] = (
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    weights_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    architecture_scores_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    preference_scores_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    deployment_scores_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    evidence_confidence_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    hard_constraints_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    tie_break_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    rounding_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    weights: SelectionWeights
    architecture_scores: tuple[ArchitectureScoreAssumption, ...]
    preference_match_score: float
    preference_mismatch_score: float
    no_preference_score: float
    preferred_or_unspecified_runtime_score: float
    non_preferred_runtime_score: float
    evidence_confidence_method: str
    hard_constraints: tuple[str, ...]
    tie_break_order: tuple[str, ...]
    score_rounding_decimals: int


class UncertaintyItem(DomainModel):
    criterion: str
    confidence: float
    uncertainty_notes: str | None = None
    interpretation: str


class UncertaintySummary(DomainModel):
    classification: Literal["PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"] = (
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    )
    evidence_references_verified: Literal[False] = False
    calculation_method: str
    items: tuple[UncertaintyItem, ...]


class ResearcherApproval(DomainModel):
    status: Literal["PENDING_RESEARCHER_APPROVAL"] = "PENDING_RESEARCHER_APPROVAL"
    required: Literal[True] = True
    decisions: tuple[str, ...]


class CriterionScore(DomainModel):
    criterion: str
    weight: float
    raw_score: float
    confidence: float
    uncertainty_adjusted_score: float
    weighted_score: float
    evidence_ref: str
    reason: str
    uncertainty_notes: str | None = None
    calculation_status: Literal["CALCULATED"] = "CALCULATED"
    weight_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    confidence_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTION"


class CandidateEvaluation(DomainModel):
    candidate: CandidateStack
    eligible: bool
    normalized_score: float
    hard_constraint_failures: tuple[str, ...]
    criterion_scores: tuple[CriterionScore, ...]
    generator_availability: GeneratorAvailability
    october_21_mvp_generator_target: bool
    decision_reason: str


class StackSelectionReport(DomainModel):
    """Versioned decision record; generator availability never changes selection."""

    report_version: Literal["1.0"] = "1.0"
    policy_version: Literal["1.0"] = "1.0"
    design_context_version: str
    project_id: str
    criteria_weights: SelectionWeights
    criteria_weights_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    observed_input_evidence: ObservedInputEvidence
    configured_scoring_assumptions: ConfiguredScoringAssumptions
    candidate_calculations: tuple[CandidateEvaluation, ...]
    uncertainty: UncertaintySummary
    selected_stack: CandidateEvaluation
    rejected_alternatives: tuple[CandidateEvaluation, ...]
    evaluated_candidate_count: Literal[4] = 4
    tie_break_policy: str
    tie_break_policy_classification: Literal[
        "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    ] = "PROVISIONAL_RESEARCH_POLICY_ASSUMPTIONS"
    selection_reason: str
    manual_approval_required: Literal[True] = True
    manual_approval_reasons: tuple[str, ...]
    researcher_approval: ResearcherApproval
