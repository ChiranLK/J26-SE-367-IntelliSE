"""Versioned endpoint for deterministic design-to-code structural verification."""

from fastapi import APIRouter, Request

from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.structural_verification import StructuralVerificationReport
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.traceability.verification import ManifestVerificationService


router = APIRouter(tags=["structural-verification"])


@router.post(
    "/structural-verifications",
    response_model=StructuralVerificationReport,
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Manifest integrity, design identity, or stack conflict.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Malformed request or unsafe workspace path.",
        },
    },
    summary="Verify generated Task MVP structure without executing it",
)
def verify_generated_structure(
    payload: StructuralVerificationRequest,
    request: Request,
) -> StructuralVerificationReport:
    service = StructuralVerificationService(
        ManifestVerificationService(request.app.state.settings.generated_workspace_root)
    )
    return service.verify(payload)
