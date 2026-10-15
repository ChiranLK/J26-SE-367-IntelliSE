from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_repair_service, get_verification_service
from app.schemas.defect_report import DefectReportListResponse
from app.schemas.feedback import (
    Component3StatusResponse,
    FeedbackApprovalRequest,
    FeedbackDispatchRequest,
    FeedbackDispatchResponse,
    FeedbackIteration,
    TechnicalFeedbackPreviewResponse,
)
from app.schemas.repair import (
    DefectResolutionComparison,
    RepairAttemptListResponse,
    RepairAttemptResponse,
    RepairResponseIngestRequest,
)
from app.schemas.test_suite import (
    TrustedTestSuiteAttachRequest,
    TrustedTestSuiteResponse,
)
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunExecute,
    VerificationRunListResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)
from app.schemas.xai import XaiExplanationResponse
from app.services.repair_service import RepairService
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
    "/integrations/component-3/status",
    response_model=Component3StatusResponse,
    summary="Get Component 3 Integration Status",
    description=(
        "Retrieves the configuration, readiness, and contract discovery status of the Component 3 integration. "
        "Allows frontend and clients to verify if automated feedback dispatch is enabled and safe."
    ),
)
async def get_component3_status(
    service: VerificationService = Depends(get_verification_service),
) -> Component3StatusResponse:
    return service.get_component3_status()


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


@router.get(
    "/{run_id}/feedback-preview",
    response_model=TechnicalFeedbackPreviewResponse,
    summary="Preview Technical Feedback Package",
    description=(
        "Returns a deterministic, read-only preview of the structured technical feedback package "
        "and eligibility decision for Component 3. Does not mutate storage or send data to Component 3."
    ),
)
async def get_feedback_preview(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> TechnicalFeedbackPreviewResponse:
    return await service.get_feedback_preview(run_id)


@router.post(
    "/{run_id}/feedback-iterations",
    response_model=FeedbackIteration,
    status_code=status.HTTP_201_CREATED,
    summary="Record Technical Feedback Iteration",
    description=(
        "Explicitly records a feedback iteration for an eligible verification run. "
        "Idempotent: prevents duplicate iteration creation if an identical defect set was already recorded."
    ),
)
async def record_feedback_iteration(
    run_id: str,
    notes: Optional[str] = Query(None, description="Optional notes regarding this feedback iteration"),
    service: VerificationService = Depends(get_verification_service),
) -> FeedbackIteration:
    return await service.record_feedback_iteration(run_id, notes=notes)


@router.get(
    "/{run_id}/explanation",
    response_model=XaiExplanationResponse,
    summary="Get Human-Facing XAI Explanation",
    description=(
        "Retrieves a human-facing, evidence-grounded Explainable AI (XAI) explanation for a specific verification run. "
        "Strictly intended for human engineers and reviewers, NOT for Component 3. Does not mutate storage or execute code."
    ),
)
async def get_verification_explanation(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> XaiExplanationResponse:
    return await service.get_explanation(run_id)


@router.post(
    "/{run_id}/approve-feedback",
    response_model=FeedbackIteration,
    summary="Approve Feedback for Component 3 Dispatch",
    description=(
        "Explicitly records human approval for an eligible verification run's technical feedback. "
        "Strictly requires the run to be in FAILED status with valid defect reports. "
        "Repeated approvals do not create duplicate iterations. "
        "Does not transmit data to Component 3. "
        "Note: Reviewer identity is client-supplied for audit trail and is not independently authenticated."
    ),
)
async def approve_feedback(
    run_id: str,
    payload: Optional[FeedbackApprovalRequest] = None,
    service: VerificationService = Depends(get_verification_service),
) -> FeedbackIteration:
    approver = payload.approver if payload and payload.approver else "human_engineer"
    notes = payload.notes if payload else None
    return await service.approve_feedback(run_id=run_id, approver=approver, notes=notes)


@router.post(
    "/{run_id}/dispatch-feedback",
    response_model=FeedbackDispatchResponse,
    summary="Dispatch Technical Feedback to Component 3",
    description=(
        "Dispatches an approved technical feedback package to Component 3. "
        "Strictly requires prior human approval and eligible FAILED status with defects. "
        "Guarantees idempotency (returns existing record for already acknowledged iterations) "
        "and concurrency protection (rejects overlapping in-flight dispatch attempts). "
        "Fails closed safely if Component 3 integration is disabled, receiver is self-referential, "
        "or contract is unconfirmed. If request times out after transmission, returns UNKNOWN delivery status."
    ),
)
async def dispatch_feedback(
    run_id: str,
    payload: Optional[FeedbackDispatchRequest] = None,
    service: VerificationService = Depends(get_verification_service),
) -> FeedbackDispatchResponse:
    approved = payload.approved if payload is not None else True
    approver = payload.approver if payload and payload.approver else "human_engineer"
    notes = payload.notes if payload else None
    force_retry = payload.force_retry if payload else False
    return await service.dispatch_feedback(
        run_id=run_id,
        approved=approved,
        approver=approver,
        notes=notes,
        force_retry=force_retry,
    )


@router.post(
    "/{run_id}/repair-responses",
    response_model=RepairAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Corrected Code for Failed Verification Run",
    description=(
        "Controlled local ingestion of corrected source code for an eligible failed verification run. "
        "Strictly enforces human approval prerequisite, file extension validation (.py only), "
        "path traversal defense, and host AST static parsing without executing untrusted code on the host. "
        "Preserves the original failed submission completely unchanged and records a new submission and repair attempt."
    ),
)
async def ingest_repair_response(
    run_id: str,
    payload: RepairResponseIngestRequest,
    service: RepairService = Depends(get_repair_service),
) -> RepairAttemptResponse:
    attempt = await service.ingest_repair_response(original_run_id=run_id, request=payload)
    return RepairAttemptResponse.model_validate(attempt.model_dump())


@router.post(
    "/{run_id}/repair-responses/{repair_id}/re-verify",
    response_model=RepairAttemptResponse,
    summary="Execute Re-Verification for Ingested Repair",
    description=(
        "Executes a new verification run for an ingested repair attempt using the existing Docker-isolated pytest runner. "
        "Reuses the original authorized test suite and computes a deterministic defect resolution comparison upon completion."
    ),
)
async def reverify_repair(
    run_id: str,
    repair_id: str,
    force_reverify: bool = Query(False, description="Force re-verification even if already executed"),
    service: RepairService = Depends(get_repair_service),
) -> RepairAttemptResponse:
    attempt = await service.execute_reverification(
        original_run_id=run_id,
        repair_id=repair_id,
        force_reverify=force_reverify,
    )
    return RepairAttemptResponse.model_validate(attempt.model_dump())


@router.get(
    "/{run_id}/repair-responses",
    response_model=RepairAttemptListResponse,
    summary="List Repair Attempts for Verification Run",
    description="Retrieves all recorded repair attempts and their resolution outcomes for a specific verification run.",
)
async def list_repair_attempts(
    run_id: str,
    service: RepairService = Depends(get_repair_service),
) -> RepairAttemptListResponse:
    items = await service.list_repair_attempts(original_run_id=run_id)
    return RepairAttemptListResponse(
        total=len(items),
        items=[RepairAttemptResponse.model_validate(i.model_dump()) for i in items],
    )


@router.get(
    "/{run_id}/repair-responses/{repair_id}",
    response_model=RepairAttemptResponse,
    summary="Get Repair Attempt Details",
    description="Retrieves a specific repair attempt and its status for a verification run.",
)
async def get_repair_attempt(
    run_id: str,
    repair_id: str,
    service: RepairService = Depends(get_repair_service),
) -> RepairAttemptResponse:
    attempt = await service.get_repair_attempt(original_run_id=run_id, repair_id=repair_id)
    return RepairAttemptResponse.model_validate(attempt.model_dump())


@router.get(
    "/{run_id}/repair-responses/{repair_id}/comparison",
    response_model=DefectResolutionComparison,
    summary="Get Defect Resolution Comparison",
    description=(
        "Retrieves the deterministic before-and-after defect and test resolution comparison "
        "between the original verification and the re-verification run."
    ),
)
async def get_repair_comparison(
    run_id: str,
    repair_id: str,
    service: RepairService = Depends(get_repair_service),
) -> DefectResolutionComparison:
    return await service.get_repair_comparison(original_run_id=run_id, repair_id=repair_id)


@router.post(
    "/{run_id}/trusted-test-suite",
    response_model=TrustedTestSuiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach or Recover Authorized Trusted Test Suite",
    description=(
        "Safely attaches an independently authorized original test artifact to a verification run. "
        "Validates syntax statically on the host (no host execution) and persists the immutable test specification "
        "without modifying original defect reports or feedback iterations."
    ),
)
async def attach_trusted_test_suite(
    run_id: str,
    payload: TrustedTestSuiteAttachRequest,
    service: VerificationService = Depends(get_verification_service),
) -> TrustedTestSuiteResponse:
    return await service.attach_trusted_test_suite(run_id=run_id, request=payload)


@router.get(
    "/{run_id}/trusted-test-suite",
    response_model=TrustedTestSuiteResponse,
    summary="Get Trusted Test Suite Metadata",
    description=(
        "Retrieves public metadata and content hash for the trusted test suite associated with a verification run. "
        "Does not expose raw executable test code unnecessarily."
    ),
)
async def get_trusted_test_suite(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> TrustedTestSuiteResponse:
    return await service.get_trusted_test_suite_metadata(run_id=run_id)




