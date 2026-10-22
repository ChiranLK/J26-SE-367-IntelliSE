"""FR-C3-02 design-understanding and stack-selection API routes."""

from fastapi import APIRouter, status

from intelise_c3.contracts.stack_selection import StackSelectionRequest
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.domain.stack_selection import StackSelectionReport
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.stack_selection import StackSelectionService

router = APIRouter(tags=["design-and-stack-selection"])

# Reuse stateless deterministic services for every request.
design_understanding_service = DesignUnderstandingService()
stack_selection_service = StackSelectionService()


# Analyze Design button: parse the accepted C2 class diagram.
@router.post(
    "/design-context",
    response_model=DesignContext,
    status_code=status.HTTP_200_OK,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "Incomplete or unsupported design structure.",
        }
    },
    summary="Build a normalized design context",
)
async def build_design_context(
    generation_context: GenerationContext,
) -> DesignContext:
    """Understand only a previously accepted immutable GenerationContext."""
    return design_understanding_service.build(generation_context)


# Compare Technology Options button: score and rank four candidate stacks.
@router.post(
    "/stack-selection",
    response_model=StackSelectionReport,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "No candidate satisfies the hard compatibility rules.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Malformed selection criteria or design context.",
        },
    },
    summary="Select a technology stack using documented evidence",
)
async def select_stack(request: StackSelectionRequest) -> StackSelectionReport:
    """Evaluate exactly four candidates with the deterministic policy."""
    return stack_selection_service.select(request)
