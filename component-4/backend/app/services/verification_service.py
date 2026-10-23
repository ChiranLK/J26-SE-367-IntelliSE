import ast
import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.errors import FileValidationException, InvalidInputException, ResourceNotFoundException
from app.core.logging import logger
from app.repositories.base import (
    BaseSubmissionRepository,
    BaseTestSuiteRepository,
    BaseVerificationRunRepository,
)
from app.schemas.delivery import DeliveryConfirmation, DeliveryConfirmationCreate
from app.schemas.test_suite import (
    TestSuiteProvenance,
    TrustedTestSuite,
    TrustedTestSuiteAttachRequest,
    TrustedTestSuiteResponse,
)
from app.schemas.common import VerificationStatus
from app.schemas.defect_report import DefectReportListResponse
from app.schemas.feedback import (
    Component3StatusResponse,
    FeedbackDispatchResponse,
    FeedbackIteration,
    TechnicalFeedbackPreviewResponse,
)
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunListResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)
from app.schemas.xai import PostDeliveryExplanation, XaiExplanationResponse
from app.schemas.research_reports import (
    DeploymentReadinessReport,
    ModuleConvergenceRiskReport,
    SemanticDriftReport,
    TraceabilityScopedXaiPayload,
)
from app.services.component3_client import Component3Client
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.feedback_service import TechnicalFeedbackService
from app.services.governance_report_service import GovernanceReportService
from app.services.ollama_client import OllamaClient
from app.services.semantic_drift_service import SemanticDriftService
from app.services.test_classification import classify_project_tests
from app.services.xai_service import XaiExplanationService
from app.workflows.verification_graph import verification_pipeline


def _has_categorized_project_tests(metadata: Optional[dict]) -> bool:
    """Return whether a ZIP project carries separate trusted test categories."""
    project_files = (metadata or {}).get("project_files") or {}
    classification = classify_project_tests(project_files)
    return (
        classification.has_explicit_metadata
        and not classification.errors
        and any(classification.paths_for(category) for category in ("unit", "integration", "performance"))
    )




class VerificationService:
    """
    Manages verification runs and orchestrates real containerized execution via LangGraph.
    """

    def __init__(
        self,
        submission_repo: BaseSubmissionRepository,
        verification_repo: BaseVerificationRunRepository,
        test_suite_repo: Optional[BaseTestSuiteRepository] = None,
    ) -> None:
        self.submission_repo = submission_repo
        self.verification_repo = verification_repo
        self.test_suite_repo = test_suite_repo

    async def create_verification_run(
        self,
        payload: VerificationRunCreate,
        execute_now: bool = False,
    ) -> VerificationRunResponse:
        """
        Registers a new verification run in PENDING status for an existing submission.
        If execute_now is True, initiates execution immediately.
        """
        # Ensure referenced submission exists
        submission = await self.submission_repo.get_by_id(payload.submission_id)
        if not submission:
            raise ResourceNotFoundException("Submission", payload.submission_id)

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Durably persist the trusted test suite immediately if available
        suite_id = None
        # Categorized ZIP projects retain their complete unit/integration/performance
        # suites in project_files. Do not collapse those suites to the single
        # legacy submission.test_code field selected during archive ingestion.
        source_test_cases = payload.trusted_test_cases
        if not source_test_cases and not _has_categorized_project_tests(submission.metadata):
            source_test_cases = submission.test_code
        if source_test_cases and self.test_suite_repo:
            new_suite = TrustedTestSuite(
                verification_run_id=run_id,
                submission_id=submission.id,
                test_code=source_test_cases,
                content_hash=TrustedTestSuite.compute_hash(source_test_cases),
                provenance=(
                    TestSuiteProvenance.RUN_EXPLICIT
                    if payload.trusted_test_cases
                    else TestSuiteProvenance.SUBMISSION_ATTACHED
                ),
                test_types=payload.test_types or ["unit"],
                execution_config={"timeout_seconds": 30},
            )
            await self.test_suite_repo.save(new_suite)
            suite_id = new_suite.suite_id
            logger.info(
                "Persisted trusted test suite %s for new verification run %s (provenance=%s)",
                suite_id,
                run_id,
                new_suite.provenance.value,
            )

        init_telemetry = {}
        if payload.trusted_test_cases:
            init_telemetry["has_trusted_test_cases"] = True

        verification_run = VerificationRunResponse(
            id=run_id,
            submission_id=submission.id,
            status=VerificationStatus.PENDING,
            triggered_by=payload.triggered_by,
            requested_test_types=payload.test_types,
            test_results=[],
            defect_reports=[],
            feedback_iterations=[],
            execution_telemetry=init_telemetry,
            test_suite_id=suite_id,
            error_message=None,
            created_at=now,
            updated_at=now,
        )

        saved_run = await self.verification_repo.save(verification_run)
        logger.info(
            "Created verification run %s for submission %s with status %s",
            run_id,
            submission.id,
            saved_run.status.value,
        )

        if execute_now:
            return await self.execute_verification_run(
                run_id=run_id,
                trusted_test_cases=payload.trusted_test_cases,
            )

        return saved_run

    async def execute_verification_run(
        self,
        run_id: str,
        trusted_test_cases: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> VerificationRunResponse:
        """
        Orchestrates real Python test execution using the LangGraph verification pipeline
        and containerized test runner sandbox.
        """
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        if not submission:
            raise ResourceNotFoundException("Submission", run.submission_id)

        # Transition to RUNNING status
        await self.verification_repo.update_status(run_id, VerificationStatus.RUNNING)
        logger.info("Starting LangGraph verification workflow for run %s", run_id)

        # Determine effective trusted test oracle
        # Prioritize explicit run parameter, then attached test suite, then submission test_code
        effective_test_cases = trusted_test_cases
        if not effective_test_cases and self.test_suite_repo:
            if getattr(run, "test_suite_id", None):
                existing_suite = await self.test_suite_repo.get_by_id(run.test_suite_id)
                if existing_suite:
                    effective_test_cases = existing_suite.test_code
            if not effective_test_cases:
                existing_suite = await self.test_suite_repo.get_by_run_id(run.id)
                if existing_suite:
                    effective_test_cases = existing_suite.test_code
        if not effective_test_cases and not _has_categorized_project_tests(submission.metadata):
            effective_test_cases = submission.test_code

        eval_mode = getattr(run, "evaluation_mode", None)
        if not eval_mode and hasattr(run, "execution_telemetry") and run.execution_telemetry:
            eval_mode = run.execution_telemetry.get("evaluation_mode")
        if not eval_mode:
            eval_mode = "LLM_ASSISTED"

        meta = submission.metadata or {}
        project_files = meta.get("project_files")
        is_multi_file = meta.get("is_multi_file", False)

        state = {
            "submission_id": submission.id,
            "run_id": run.id,
            "source_code": submission.code,
            "language": submission.language.value,
            "filename": submission.filename,
            "requirement_ids": submission.requirement_ids,
            "trusted_test_cases": effective_test_cases,
            "timeout_seconds": timeout_seconds,
            "requested_test_types": run.requested_test_types or ["unit"],
            "feedback_iterations": list(run.feedback_iterations or []),
            "evaluation_mode": eval_mode,
            "telemetry": {},
            "project_files": project_files,
            "is_multi_file": is_multi_file,
        }

        # Invoke the LangGraph compiled state graph
        result_state = await verification_pipeline.ainvoke(state)

        final_status_str = result_state.get("status", VerificationStatus.ERROR.value)
        try:
            final_status = VerificationStatus(final_status_str)
        except ValueError:
            final_status = VerificationStatus.ERROR

        final_results = result_state.get("test_results", [])
        final_defects = result_state.get("defect_reports", [])
        final_iterations = result_state.get("feedback_iterations", run.feedback_iterations)
        final_error = result_state.get("error_message")
        final_telemetry = result_state.get("telemetry", {})

        # Durably persist the trusted test suite for subsequent re-verification
        saved_suite_id = getattr(run, "test_suite_id", None)
        if effective_test_cases and self.test_suite_repo:
            existing = await self.test_suite_repo.get_by_run_id(run.id)
            if existing and existing.test_code == effective_test_cases:
                saved_suite_id = existing.suite_id
            else:
                new_suite = TrustedTestSuite(
                    verification_run_id=run.id,
                    submission_id=submission.id,
                    test_code=effective_test_cases,
                    content_hash=TrustedTestSuite.compute_hash(effective_test_cases),
                    provenance=(
                        TestSuiteProvenance.RUN_EXPLICIT
                        if trusted_test_cases
                        else TestSuiteProvenance.SUBMISSION_ATTACHED
                    ),
                    test_types=run.requested_test_types or ["unit"],
                    execution_config={"timeout_seconds": timeout_seconds or 30},
                )
                await self.test_suite_repo.save(new_suite)
                saved_suite_id = new_suite.suite_id

        now = datetime.now(timezone.utc)
        updated_run = VerificationRunResponse(
            id=run.id,
            submission_id=run.submission_id,
            status=final_status,
            triggered_by=run.triggered_by,
            requested_test_types=run.requested_test_types,
            test_results=final_results,
            defect_reports=final_defects,
            feedback_iterations=final_iterations,
            execution_telemetry=final_telemetry,
            test_suite_id=saved_suite_id,
            delivery_confirmation=None,
            error_message=final_error,
            created_at=run.created_at,
            updated_at=now,
        )

        saved = await self.verification_repo.save(updated_run)
        logger.info(
            "Completed verification run %s with status %s (test count: %d, defect count: %d, iterations: %d, suite: %s)",
            run_id,
            saved.status.value,
            len(saved.test_results),
            len(saved.defect_reports),
            len(saved.feedback_iterations),
            saved_suite_id,
        )
        return saved


    async def get_verification_run(self, run_id: str) -> VerificationRunResponse:
        """Retrieves complete details for a verification run."""
        run = await self.verification_repo.get_by_id(run_id)
        if not run:
            raise ResourceNotFoundException("VerificationRun", run_id)
        return run

    async def get_verification_status(self, run_id: str) -> VerificationStatusResponse:
        """Retrieves lightweight status information for a verification run."""
        run = await self.get_verification_run(run_id)
        return VerificationStatusResponse(
            id=run.id,
            submission_id=run.submission_id,
            status=run.status,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    async def get_verification_defects(self, run_id: str) -> DefectReportListResponse:
        """
        Retrieves evidence-based defect reports for a specific verification run.
        If the run failed and defect reports have not yet been generated, analyzes the run on-demand.
        """
        run = await self.get_verification_run(run_id)

        # If run is PASSED or PENDING, returns empty list
        if run.status in (VerificationStatus.PASSED, VerificationStatus.PENDING):
            return DefectReportListResponse(total=0, items=[])

        # If defect reports are already present, return them
        if run.defect_reports:
            return DefectReportListResponse(total=len(run.defect_reports), items=run.defect_reports)

        # On-demand fallback analysis if run failed but defect_reports list was empty
        submission = await self.submission_repo.get_by_id(run.submission_id)
        analyzer = DefectAnalysisService()
        reports = analyzer.analyze_run(run, submission)

        if reports:
            # Save updated reports back to repository
            run.defect_reports = reports
            run.updated_at = datetime.now(timezone.utc)
            await self.verification_repo.save(run)

        return DefectReportListResponse(total=len(reports), items=reports)

    async def get_feedback_preview(self, run_id: str) -> TechnicalFeedbackPreviewResponse:
        """
        Retrieves a deterministic read-only preview of technical feedback for a verification run.
        Does NOT mutate repository storage or create duplicate iterations.
        """
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        service = TechnicalFeedbackService()
        return service.get_feedback_preview(run, submission)

    async def get_explanation(self, run_id: str) -> XaiExplanationResponse:
        """
        Retrieves a human-facing XAI explanation for a verification run.
        Strictly enforces the 3-phase delivery gate:
          1. Verification tests passed (zero failed assertions)
          2. Deployment-readiness governance cleared
          3. Successful downstream delivery confirmed for the exact artifact version

        Returns a pending explanation state if delivery confirmation is unavailable,
        or an explicit non-delivery justification if verification failed or was blocked.
        """
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        governance_report = None
        if run.status == VerificationStatus.PASSED:
            try:
                governance_report = await self.get_deployment_readiness_report(run_id)
            except Exception as exc:
                logger.warning("Could not evaluate deployment readiness report for XAI gate: %s", exc)
        service = XaiExplanationService()
        # Ollama's local HTTP client is synchronous. Keep its bounded generation
        # off the ASGI event loop so health checks and unrelated API calls remain responsive.
        return await asyncio.to_thread(
            service.generate_explanation,
            run,
            submission,
            governance_report,
        )

    async def confirm_delivery(
        self,
        run_id: str,
        delivery_channel: str = "user_workspace",
        confirmed_by: Optional[str] = None,
        artifact_version: Optional[str] = None,
        is_simulation: bool = False,
        auth_token: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> DeliveryConfirmation:
        """
        Records confirmed downstream delivery for a verified, governance-approved artifact version.
        Prerequisite gate for unlocking user-facing post-delivery code understanding explanations.
        Enforces backend-verified service credentials for production delivery.
        """
        run = await self.get_verification_run(run_id)
        if run.status != VerificationStatus.PASSED:
            raise InvalidInputException(
                f"Cannot confirm delivery for verification run '{run_id}' with status '{run.status.value}'. "
                "Artifact must pass verification tests before delivery."
            )

        readiness = await self.get_deployment_readiness_report(run_id)
        if not readiness.is_ready_for_deployment:
            blockers = readiness.blocking_reasons or [c.gate_name for c in readiness.gating_checks if c.status != "PASSED"]
            raise InvalidInputException(
                f"Deployment-readiness governance blocked delivery approval for run '{run_id}'. "
                f"Unsatisfied gating checks: {', '.join(blockers)}."
            )

        submission = await self.submission_repo.get_by_id(run.submission_id)
        if not submission or not submission.code:
            raise InvalidInputException(f"Submission code not found for run '{run_id}'.")

        checksum = hashlib.sha256(submission.code.encode("utf-8")).hexdigest()

        if artifact_version and artifact_version != run.submission_id:
            raise InvalidInputException(
                f"Specified artifact version '{artifact_version}' does not match run submission ID '{run.submission_id}'."
            )

        if is_simulation:
            # Enforce simulation environment constraints
            if not settings.is_simulation_permitted():
                raise InvalidInputException(
                    "Simulated delivery confirmation is disabled in production environments. "
                    "Production deployments require authenticated service identity."
                )
            # Server derives identity; do not trust caller role
            effective_confirmer = "simulated_harness"
        else:
            # Production delivery confirmation requires server-side identity validation
            if not artifact_version:
                raise InvalidInputException(
                    "Production delivery confirmation requires explicit artifact_version matching the verified submission ID."
                )

            # Validate authentication token using constant-time comparison
            if not auth_token or not auth_token.strip():
                raise InvalidInputException(
                    "Missing production delivery service credentials. Provide valid X-Delivery-Token header or Bearer token."
                )

            # Explicit defense against compromised or revoked credentials
            REVOKED_COMPROMISED_TOKENS = {
                "intelise_dev_delivery_token_secret",
            }
            if auth_token.strip() in REVOKED_COMPROMISED_TOKENS:
                raise InvalidInputException(
                    "Compromised or revoked delivery credentials. Access denied."
                )

            expected_token = settings.DELIVERY_AUTH_TOKEN
            if not expected_token or expected_token in REVOKED_COMPROMISED_TOKENS:
                raise InvalidInputException(
                    "Production delivery service credentials not configured or using prohibited default in production environment."
                )

            if not secrets.compare_digest(auth_token.strip(), expected_token.strip()):
                raise InvalidInputException(
                    "Invalid production delivery service credentials. Access denied."
                )

            # Server assigns authenticated identity; caller-supplied strings are rejected as proof of identity
            effective_confirmer = "authenticated_delivery_service"

        confirmation = DeliveryConfirmation(
            delivery_id=f"dlv-{uuid.uuid4().hex[:12]}",
            verification_run_id=run.id,
            submission_id=run.submission_id,
            artifact_checksum_sha256=checksum,
            delivery_channel=delivery_channel,
            confirmed_by=effective_confirmer,
            delivered_at=datetime.now(timezone.utc),
            is_delivered=True,
            is_simulation=is_simulation,
            notes=notes,
        )

        run.delivery_confirmation = confirmation
        run.updated_at = datetime.now(timezone.utc)
        await self.verification_repo.save(run)
        logger.info(
            "Delivery confirmed for run '%s' (submission '%s', simulation=%s, entity='%s')",
            run.id,
            run.submission_id,
            is_simulation,
            effective_confirmer,
        )
        return confirmation

    async def get_delivery_confirmation(self, run_id: str) -> Optional[DeliveryConfirmation]:
        """Retrieves the delivery confirmation status for a verification run."""
        run = await self.get_verification_run(run_id)
        return run.delivery_confirmation

    async def get_post_delivery_explanation(self, run_id: str) -> PostDeliveryExplanation:
        """
        Retrieves the dedicated post-delivery software understanding package.
        Raises InvalidInputException if the delivery gate is not fully satisfied.
        Allows an explicitly labeled development-only simulation when the server
        environment permits it; production still requires authenticated delivery.
        """
        explanation = await self.get_explanation(run_id)
        if not explanation.post_delivery_explanation:
            raise InvalidInputException(
                f"Post-delivery code understanding explanation is unavailable for run '{run_id}'. "
                f"Reason: {explanation.eligibility_reason}"
            )
        return explanation.post_delivery_explanation

    async def record_feedback_iteration(
        self,
        run_id: str,
        notes: Optional[str] = None,
    ) -> FeedbackIteration:
        """
        Explicitly records a feedback iteration for an eligible verification run.
        Idempotent: will not create duplicates if an iteration for identical defects already exists.
        """
        run = await self.get_verification_run(run_id)
        service = TechnicalFeedbackService()
        is_eligible, reason = service.check_eligibility(run)
        if not is_eligible:
            raise InvalidInputException(f"Cannot record feedback iteration: {reason}")

        submission = await self.submission_repo.get_by_id(run.submission_id)
        payload = service.build_feedback_payload(run, submission)
        updated_run, iteration, created = service.record_feedback_iteration(run, payload, notes=notes)
        if created:
            await self.verification_repo.save(updated_run)
        return iteration

    _dispatch_locks: Dict[str, asyncio.Lock] = {}

    def get_component3_status(self) -> Component3StatusResponse:
        """Retrieves Component 3 connectivity, configuration, and contract readiness status."""
        client = Component3Client()
        return client.get_status()

    async def approve_feedback(
        self,
        run_id: str,
        approver: str = "human_engineer",
        notes: Optional[str] = None,
    ) -> FeedbackIteration:
        """
        Explicitly records human approval for an eligible verification run's technical feedback.
        Repeated approvals for the same defect set do not create duplicate iterations.
        Approval does not automatically trigger dispatch.
        """
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        service = TechnicalFeedbackService()
        updated_run, iteration = service.approve_feedback(
            run=run, submission=submission, approver=approver, notes=notes
        )
        await self.verification_repo.save(updated_run)
        return iteration

    async def dispatch_feedback(
        self,
        run_id: str,
        approved: bool = True,
        approver: str = "human_engineer",
        notes: Optional[str] = None,
        force_retry: bool = False,
        client: Optional[Component3Client] = None,
    ) -> FeedbackDispatchResponse:
        """
        Dispatches an approved technical feedback package to Component 3.
        Enforces human approval, safe fail-closed behavior when Component 3 is not ready,
        atomic in-flight concurrency protection, and unknown-outcome handling on timeout.
        """
        lock = self._dispatch_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            run = await self.get_verification_run(run_id)
            submission = await self.submission_repo.get_by_id(run.submission_id)
            service = TechnicalFeedbackService()

            # If user explicitly approves in dispatch request and not yet approved, mark approved first
            latest_iter = run.feedback_iterations[-1] if run.feedback_iterations else None
            if (not latest_iter or latest_iter.approval_status != "APPROVED") and approved:
                run, _ = service.approve_feedback(
                    run=run, submission=submission, approver=approver, notes=notes
                )
                await self.verification_repo.save(run)

            updated_run, iteration, already_dispatched, result = await service.dispatch_feedback(
                run=run,
                submission=submission,
                client=client,
                approver=approver,
                notes=notes,
                force_retry=force_retry,
            )
            await self.verification_repo.save(updated_run)

            feedback_id = iteration.payload.feedback_id if iteration.payload else f"fb-{run.id}"

            if already_dispatched:
                return FeedbackDispatchResponse(
                    verification_run_id=run.id,
                    feedback_id=feedback_id,
                    dispatch_attempt_id=iteration.dispatch_attempt_id or f"disp-{uuid.uuid4().hex[:12]}",
                    approval_status=iteration.approval_status,
                    delivery_status=iteration.delivery_status,
                    component_3_acknowledged=iteration.component_3_acknowledged,
                    component_3_job_id=iteration.component_3_job_id,
                    correlation_id=iteration.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                    message="Feedback already delivered and acknowledged by Component 3.",
                    error_category=None,
                    sanitized_error_message=None,
                    attempt_count=iteration.attempt_count or 1,
                    iteration=iteration,
                )

            return FeedbackDispatchResponse(
                verification_run_id=run.id,
                feedback_id=feedback_id,
                dispatch_attempt_id=result.dispatch_attempt_id,
                approval_status=iteration.approval_status,
                delivery_status=iteration.delivery_status,
                component_3_acknowledged=result.acknowledged,
                component_3_job_id=result.job_id,
                correlation_id=result.correlation_id,
                message=result.message,
                error_category=result.error_category,
                sanitized_error_message=iteration.sanitized_error_message,
                attempt_count=iteration.attempt_count or 1,
                iteration=iteration,
            )

    async def list_runs(
        self,
        submission_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> VerificationRunListResponse:
        """Lists verification runs, optionally filtered by submission ID."""
        if submission_id:
            items = await self.verification_repo.get_by_submission_id(submission_id)
            total = len(items)
            paged_items = items[skip : skip + limit]
            return VerificationRunListResponse(total=total, items=paged_items)

        items = await self.verification_repo.list_all(skip=skip, limit=limit)
        total = await self.verification_repo.count()
        return VerificationRunListResponse(total=total, items=items)

    async def attach_trusted_test_suite(
        self,
        run_id: str,
        request: TrustedTestSuiteAttachRequest,
    ) -> TrustedTestSuiteResponse:
        """
        Secure recovery workflow to explicitly supply an independently authorized original test artifact
        for a historical verification run lacking durable test specifications.
        Validates syntax statically without host execution, persists the immutable test suite,
        and associates it with the verification run without altering its original defect history or results.
        """
        run = await self.get_verification_run(run_id)
        if not run:
            raise ResourceNotFoundException("VerificationRun", run_id)

        # 1. Static AST parsing on the host (NEVER execute code on host)
        try:
            ast.parse(request.test_code, filename="trusted_test_recovery.py")
        except SyntaxError as syn_err:
            raise FileValidationException(
                f"Authorized test code contains syntax errors: {syn_err.msg} (line {syn_err.lineno})"
            )
        except Exception as parse_err:
            raise FileValidationException(f"Failed to parse test code statically: {parse_err}")

        # 2. Compute deterministic content hash
        content_hash = TrustedTestSuite.compute_hash(request.test_code)

        # 3. Create trusted test suite specification
        suite = TrustedTestSuite(
            verification_run_id=run.id,
            submission_id=run.submission_id,
            test_code=request.test_code,
            content_hash=content_hash,
            provenance=request.provenance,
            test_types=run.requested_test_types or ["unit"],
            notes=request.notes,
        )

        if self.test_suite_repo:
            await self.test_suite_repo.save(suite)

        # 4. Associate with the run WITHOUT altering test_results, defect_reports, or feedback_iterations
        if not run.test_suite_id or run.test_suite_id != suite.suite_id:
            run.test_suite_id = suite.suite_id
            run.updated_at = datetime.now(timezone.utc)
            await self.verification_repo.save(run)

        # 5. If this run has an original submission with missing test_code, attach it safely
        submission = await self.submission_repo.get_by_id(run.submission_id)
        if submission and not submission.test_code:
            submission.test_code = request.test_code
            await self.submission_repo.save(submission)

        logger.info(
            "Attached authorized trusted test suite %s (hash %s, provenance %s) to run %s",
            suite.suite_id,
            content_hash[:12],
            suite.provenance.value,
            run.id,
        )

        return TrustedTestSuiteResponse(
            suite_id=suite.suite_id,
            verification_run_id=suite.verification_run_id,
            submission_id=suite.submission_id,
            content_hash=suite.content_hash,
            provenance=suite.provenance,
            test_types=suite.test_types,
            notes=suite.notes,
            created_at=suite.created_at,
        )

    async def get_trusted_test_suite_metadata(
        self,
        run_id: str,
    ) -> TrustedTestSuiteResponse:
        """
        Retrieves public metadata for the trusted test suite associated with a verification run.
        Avoids exposing raw executable test source code.
        """
        run = await self.get_verification_run(run_id)
        if not run:
            raise ResourceNotFoundException("VerificationRun", run_id)

        suite = None
        if self.test_suite_repo:
            if run.test_suite_id:
                suite = await self.test_suite_repo.get_by_id(run.test_suite_id)
            if not suite:
                suite = await self.test_suite_repo.get_by_run_id(run_id)

        if not suite:
            # Check if submission has test_code
            sub = await self.submission_repo.get_by_id(run.submission_id)
            if sub and sub.test_code:
                return TrustedTestSuiteResponse(
                    suite_id=f"legacy-sub-{sub.id}",
                    verification_run_id=run.id,
                    submission_id=sub.id,
                    content_hash=TrustedTestSuite.compute_hash(sub.test_code),
                    provenance=TestSuiteProvenance.SUBMISSION_ATTACHED,
                    test_types=run.requested_test_types or ["unit"],
                    notes="Discovered from original submission test_code",
                    created_at=sub.created_at,
                )
            raise ResourceNotFoundException("TrustedTestSuite", f"run:{run_id}")

        return TrustedTestSuiteResponse(
            suite_id=suite.suite_id,
            verification_run_id=suite.verification_run_id,
            submission_id=suite.submission_id,
            content_hash=suite.content_hash,
            provenance=suite.provenance,
            test_types=suite.test_types,
            notes=suite.notes,
            created_at=suite.created_at,
        )

    async def get_trusted_test_code_for_run(
        self,
        run_id: str,
    ) -> Optional[str]:
        """Internal helper to retrieve authorized test code for containerized execution."""
        run = await self.verification_repo.get_by_id(run_id)
        if not run:
            return None
        if self.test_suite_repo:
            if getattr(run, "test_suite_id", None):
                suite = await self.test_suite_repo.get_by_id(run.test_suite_id)
                if suite and suite.test_code:
                    return suite.test_code
            suite = await self.test_suite_repo.get_by_run_id(run_id)
            if suite and suite.test_code:
                return suite.test_code

        sub = await self.submission_repo.get_by_id(run.submission_id)
        if sub and sub.test_code:
            return sub.test_code

        return None

    async def get_convergence_risk_report(self, run_id: str) -> ModuleConvergenceRiskReport:
        """Synthesizes proposal-required Module Convergence Risk Report (SO5, FR10)."""
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        drift_report = None
        if self.test_suite_repo:
            suite = await self.test_suite_repo.get_by_run_id(run_id)
            if suite and submission and submission.test_code and suite.test_code != submission.test_code:
                drift_service = SemanticDriftService()
                drift_report = drift_service.analyze_test_suite_drift(
                    original_test_code=suite.test_code,
                    candidate_test_code=submission.test_code,
                    verification_run_id=run.id,
                )
        gov_service = GovernanceReportService()
        return gov_service.generate_convergence_risk_report(run, submission, drift_report)

    async def get_deployment_readiness_report(self, run_id: str) -> DeploymentReadinessReport:
        """Synthesizes proposal-required Deployment Readiness Report with gating checks (FR11, NFR01)."""
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        drift_report = None
        if self.test_suite_repo:
            suite = await self.test_suite_repo.get_by_run_id(run_id)
            if suite and submission and submission.test_code and suite.test_code != submission.test_code:
                drift_service = SemanticDriftService()
                drift_report = drift_service.analyze_test_suite_drift(
                    original_test_code=suite.test_code,
                    candidate_test_code=submission.test_code,
                    verification_run_id=run.id,
                )
        gov_service = GovernanceReportService()
        conv_report = gov_service.generate_convergence_risk_report(run, submission, drift_report)
        return gov_service.generate_deployment_readiness_report(run, submission, drift_report, conv_report)

    async def analyze_test_suite_drift(self, run_id: str, candidate_test_code: str) -> SemanticDriftReport:
        """Performs AST-based semantic drift analysis on a candidate test suite (FR07, NFR01)."""
        run = await self.get_verification_run(run_id)
        original_test_code = ""
        if self.test_suite_repo:
            suite = await self.test_suite_repo.get_by_run_id(run_id)
            if suite:
                original_test_code = suite.test_code
        if not original_test_code:
            submission = await self.submission_repo.get_by_id(run.submission_id)
            if submission:
                original_test_code = submission.test_code or ""

        drift_service = SemanticDriftService()
        return drift_service.analyze_test_suite_drift(
            original_test_code=original_test_code,
            candidate_test_code=candidate_test_code,
            verification_run_id=run_id,
        )

    async def get_traceability_scoped_explanations(self, run_id: str) -> List[TraceabilityScopedXaiPayload]:
        """Synthesizes machine-readable defect reports scoped to RTM and test seams (SO3, FR04)."""
        run = await self.get_verification_run(run_id)
        submission = await self.submission_repo.get_by_id(run.submission_id)
        service = XaiExplanationService()
        explanations = []
        for defect in run.defect_reports:
            exp = service.generate_traceability_scoped_explanation(run, defect, submission)
            explanations.append(exp)
        return explanations

    async def get_ai_engine_status(self) -> Dict[str, Any]:
        """Queries local Ollama runtime and reports model availability and active XAI provider."""
        client = OllamaClient()
        is_ok, models, msg = await client.check_availability()
        return {
            "ollama_enabled": client.enabled,
            "ollama_base_url": client.base_url,
            "configured_model": client.model_name,
            "ollama_connected": is_ok,
            "available_models": models,
            "status_message": msg,
            "active_xai_provider": "ollama_inference_v1 (with deterministic fallback)",
        }

