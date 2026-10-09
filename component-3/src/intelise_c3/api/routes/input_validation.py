"""FR-C3-01 endpoint for validating provisional C1/C2 input packages."""

from fastapi import APIRouter, status

from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.input_validation import InputValidationService

router = APIRouter(tags=["input-validation"])
validation_service = InputValidationService()


@router.post(
    "/validate-input",
    response_model=GenerationContext,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Semantic, approval-state, or version conflict.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Malformed input or schema validation failure.",
        },
    },
    summary="Validate provisional approved C1/C2 inputs",
)
async def validate_input(package: ProvisionalInputPackage) -> GenerationContext:
    """Return a normalized context only when every FR-C3-01 rule passes."""
    return validation_service.validate(package)
