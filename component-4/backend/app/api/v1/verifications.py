from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_verification_service
from app.schemas.defect_report import DefectReportListResponse
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunExecute,
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
        "Registers a verification run for an existing submission. Defaults to PENDING status. "
        "If execute_now=true, immediately executes the LangGraph verification pipeline in an isolated Docker sandbox."
    ),
)
async def create_verification_run(
    payload: VerificationRunCreate,
    execute_now: bool = Query(False, description="Optionally execute verification run immediately"),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRunResponse:
    return await service.create_verification_run(payload, execute_now=execute_now)


@router.post(
    "/{run_id}/execute",
    response_model=VerificationRunResponse,
    summary="Execute Verification Run",
    description=(
        "Triggers the LangGraph verification pipeline for an existing verification run, "
        "executing pytest against trusted test cases inside an isolated, non-root Docker container."
    ),
)
async def execute_verification_run(
    run_id: str,
    payload: Optional[VerificationRunExecute] = None,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationRunResponse:
    trusted_tests = payload.trusted_test_cases if payload else None
    return await service.execute_verification_run(run_id, trusted_test_cases=trusted_tests)


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


@router.get(
    "/{run_id}/defects",
    response_model=DefectReportListResponse,
    summary="Get Verification Run Defect Reports",
    description=(
        "Retrieves empirical, evidence-based defect reports generated from real pytest execution outcomes "
        "for a specific verification run. Returns zero defects for PASSED or PENDING runs."
    ),
)
async def get_verification_defects(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> DefectReportListResponse:
    return await service.get_verification_defects(run_id)

