from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from app.api.deps import get_repair_service, get_verification_service
from app.core.errors import InvalidInputException
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
    Component3RepairDeliveryRequest,
    Component3RepairDeliveryResponse,
    DefectResolutionComparison,
    RepairAttemptListResponse,
    RepairAttemptResponse,
    RepairResponseIngestRequest,
)
from app.schemas.research_reports import (
    DeploymentReadinessReport,
    ModuleConvergenceRiskReport,
    SemanticDriftReport,
    TestSuiteDriftAnalysisRequest,
    TraceabilityScopedXaiPayload,
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
from app.schemas.delivery import DeliveryConfirmation, DeliveryConfirmationCreate
from app.schemas.xai import PostDeliveryExplanation, XaiExplanationResponse
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
    "/{run_id}/delivery-confirmation",
    response_model=DeliveryConfirmation,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm Artifact Delivery Gate",
    description=(
        "Records confirmed downstream delivery for a verified, governance-approved artifact. "
        "Enforces that the run has passed verification and satisfied deployment-readiness governance. "
        "Requires authenticated service identity (X-Delivery-Token or Bearer header) for production delivery. "
        "Prerequisite gate for unlocking user-facing post-delivery code understanding explanations."
    ),
)
async def confirm_delivery(
    run_id: str,
    payload: Optional[DeliveryConfirmationCreate] = None,
    x_delivery_token: Optional[str] = Header(None, alias="X-Delivery-Token"),
    authorization: Optional[str] = Header(None),
    service: VerificationService = Depends(get_verification_service),
) -> DeliveryConfirmation:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_delivery_token:
        token = x_delivery_token.strip()

    channel = payload.delivery_channel if payload else "user_workspace"
    confirmed_by = payload.confirmed_by if payload else None
    artifact_version = payload.artifact_version if payload else None
    is_simulation = payload.is_simulation if payload else False
    notes = payload.notes if payload else None

    return await service.confirm_delivery(
        run_id=run_id,
        delivery_channel=channel,
        confirmed_by=confirmed_by,
        artifact_version=artifact_version,
        is_simulation=is_simulation,
        auth_token=token,
        notes=notes,
    )


@router.get(
    "/{run_id}/delivery-confirmation",
    response_model=Optional[DeliveryConfirmation],
    summary="Get Delivery Confirmation Status",
    description="Retrieves the delivery confirmation status for a verification run.",
)
async def get_delivery_confirmation(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> Optional[DeliveryConfirmation]:
    return await service.get_delivery_confirmation(run_id)


@router.get(
    "/{run_id}/post-delivery-explanation",
    response_model=PostDeliveryExplanation,
    summary="Get Dedicated Post-Delivery Software Understanding Package",
    description=(
        "Retrieves the comprehensive 8-dimension post-delivery software understanding package "
        "comprising beginner and technical layers. Available strictly upon confirmed delivery of verified code."
    ),
)
async def get_post_delivery_explanation(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> PostDeliveryExplanation:
    return await service.get_post_delivery_explanation(run_id)


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
    "/{run_id}/integrations/component-3/repair-delivery",
    response_model=Component3RepairDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deliver Component 3 Generated Repair Response",
    description=(
        "Formal inbound integration endpoint for Component 3 to deliver repaired source code. "
        "Enforces contract version validation ('1.0'), run and approved iteration matching, "
        "correlation validation, safe host static AST validation (zero host execution), "
        "and idempotent duplicate ingestion protection."
    ),
)
async def deliver_component3_repair(
    run_id: str,
    payload: Component3RepairDeliveryRequest,
    service: RepairService = Depends(get_repair_service),
) -> Component3RepairDeliveryResponse:
    if payload.verification_run_id != run_id:
        raise InvalidInputException(
            f"Path parameter run_id '{run_id}' does not match body verification_run_id '{payload.verification_run_id}'."
        )

    ingest_req = RepairResponseIngestRequest(
        corrected_code=payload.corrected_code,
        filename=payload.filename or "solution.py",
        feedback_iteration_id=payload.feedback_iteration_id,
        repair_source=payload.repair_provenance,
        notes=payload.notes,
        correlation_id=payload.correlation_id,
        external_repair_job_id=payload.external_repair_job_id,
    )
    attempt = await service.ingest_repair_response(original_run_id=run_id, request=ingest_req)

    return Component3RepairDeliveryResponse(
        repair_id=attempt.repair_id or attempt.id,
        original_run_id=attempt.original_run_id,
        feedback_iteration_id=attempt.feedback_iteration_id,
        external_repair_job_id=payload.external_repair_job_id,
        correlation_id=attempt.correlation_id,
        status=attempt.status,
        corrected_submission_id=attempt.corrected_submission_id,
        filename=attempt.corrected_filename or attempt.filename or "solution.py",
        message="Component 3 repair successfully ingested. Ready for authorized re-verification.",
        ingested_at=attempt.created_at,
    )


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


@router.get(
    "/status/ai-engine",
    summary="Get Local AI / Ollama Engine Status",
    description="Reports connectivity to local Ollama runtime, installed models, and active XAI provider.",
)
async def get_ai_engine_status(
    service: VerificationService = Depends(get_verification_service),
):
    return await service.get_ai_engine_status()


@router.get(
    "/{run_id}/convergence-risk-report",
    response_model=ModuleConvergenceRiskReport,
    summary="Get Module Convergence Risk Report",
    description=(
        "Synthesizes proposal-required Module Convergence Risk Report (SO5, FR10). "
        "Evaluates loop iteration count as an architectural-risk signal and flags superficial convergence."
    ),
)
async def get_convergence_risk_report(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> ModuleConvergenceRiskReport:
    return await service.get_convergence_risk_report(run_id=run_id)


@router.get(
    "/{run_id}/deployment-readiness-report",
    response_model=DeploymentReadinessReport,
    summary="Get Deployment Readiness Report",
    description=(
        "Synthesizes proposal-required Deployment Readiness Report (FR11, NFR01). "
        "Evaluates mandatory release safety gates: all tests passed, 0 critical/security defects, "
        "0 performance bottlenecks, and zero unresolved test semantic drift."
    ),
)
async def get_deployment_readiness_report(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> DeploymentReadinessReport:
    return await service.get_deployment_readiness_report(run_id=run_id)


@router.post(
    "/{run_id}/test-suite-drift-analysis",
    response_model=SemanticDriftReport,
    summary="Analyze Candidate Test Suite for Semantic Drift",
    description=(
        "Compares a candidate test suite against the authorized frozen suite using AST inspection (FR07, NFR01). "
        "Detects assertion weakening, deleted test cases, or altered thresholds."
    ),
)
async def analyze_test_suite_drift(
    run_id: str,
    payload: TestSuiteDriftAnalysisRequest,
    service: VerificationService = Depends(get_verification_service),
) -> SemanticDriftReport:
    return await service.analyze_test_suite_drift(run_id=run_id, candidate_test_code=payload.candidate_test_code)


@router.get(
    "/{run_id}/xai/machine-scoped",
    response_model=List[TraceabilityScopedXaiPayload],
    summary="Get Machine-Readable Traceability-Scoped Defect Reports",
    description=(
        "Synthesizes machine-readable defect reports scoped to Component 3's traceability context (SO3, FR04). "
        "Includes RTM requirement IDs, test seam references, defect classification, and regeneration guidance."
    ),
)
async def get_machine_scoped_xai(
    run_id: str,
    service: VerificationService = Depends(get_verification_service),
) -> List[TraceabilityScopedXaiPayload]:
    return await service.get_traceability_scoped_explanations(run_id=run_id)





