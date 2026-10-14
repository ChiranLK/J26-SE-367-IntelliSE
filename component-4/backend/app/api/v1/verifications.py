from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_verification_service
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunListResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/verifications", tags=["Verifications"])


@router.post(
    "",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Verification Run",
    description=(
        "Registers a verification run in PENDING status for an existing submission. "
        "In Phase 1, test execution and agent workflows are NOT executed; the run is prepared "
        "with PENDING status for Phase 2 agentic execution."
    ),
)
async def create_verification_run(
    payload: VerificationRunCreate,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRunResponse:
    return await service.create_verification_run(payload)


@router.get(
    "",
    response_model=VerificationRunListResponse,
    summary="List Verification Runs",
    description="Lists all verification runs, optionally filtered by submission ID.",
)
async def list_verification_runs(
    submission_id: Optional[str] = Query(
        None, description="Optional filter by submission ID"
    ),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRunListResponse:
    return await service.list_runs(
        submission_id=submission_id, skip=skip, limit=limit
    )


@router.get(
    "/{run_id}",
    response_model=VerificationRunResponse,
    summary="Get Verification Run Details",
    description="Retrieves full details of a specific verification run.",
)
async def get_verification_run(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRunResponse:
    return await service.get_verification_run(run_id)


@router.get(
    "/{run_id}/status",
    response_model=VerificationStatusResponse,
    summary="Get Verification Run Status",
    description="Retrieves the current status of a verification run.",
)
async def get_verification_status(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationStatusResponse:
    return await service.get_verification_status(run_id)
