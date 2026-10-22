"""Pure-compute requirement/UML anchor coverage route."""

from fastapi import APIRouter, status

from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.design_coverage import DesignCoverageReport
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_coverage import DesignCoverageService

router = APIRouter(tags=["design-coverage"])

# Reuse the stateless deterministic coverage service for every request.
design_coverage_service = DesignCoverageService()


# Check Requirement Coverage button: compare C1 FRs with C2 UML anchors.
@router.post(
    "/design-coverage",
    response_model=DesignCoverageReport,
    status_code=status.HTTP_200_OK,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "Incomplete or unsupported design structure.",
        }
    },
    summary="Report requirement/UML anchor coverage (no persistence)",
)
async def design_coverage(generation_context: GenerationContext) -> DesignCoverageReport:
    """Compute anchor coverage from an accepted GenerationContext; writes nothing."""
    return design_coverage_service.build(generation_context)
