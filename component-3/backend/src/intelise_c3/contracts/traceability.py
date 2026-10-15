"""API contracts for persistent living-traceability operations."""

from typing import Annotated

from pydantic import Field

from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.domain.generation_context import DomainModel
from intelise_c3.domain.traceability import (
    ResearchGroundTruth,
    SourceVersionTransitionEvidence,
)


class GraphManifestInput(DomainModel):
    manifest: GenerationManifest
    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]


class GraphCreateRequest(GraphManifestInput):
    pass


class GraphComparisonRequest(GraphManifestInput):
    base_graph_version: Annotated[int, Field(ge=1)]
    source_transition_evidence: SourceVersionTransitionEvidence | None = None


class GraphUpdateRequest(GraphComparisonRequest):
    pass


class GraphEvaluationRequest(DomainModel):
    ground_truth: ResearchGroundTruth
