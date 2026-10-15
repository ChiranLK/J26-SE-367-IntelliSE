import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.core.errors import InvalidInputException, ResourceNotFoundException
from app.core.logging import logger
from app.repositories.base import BaseSubmissionRepository, BaseVerificationRunRepository
from app.schemas.common import VerificationStatus
from app.schemas.defect_report import DefectReportListResponse
from app.schemas.feedback import FeedbackIteration, TechnicalFeedbackPreviewResponse
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunListResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.feedback_service import TechnicalFeedbackService
from app.workflows.verification_graph import verification_pipeline




class VerificationService:
    """
    Manages verification runs and orchestrates real containerized execution via LangGraph.
    """

    def __init__(
        self,
        submission_repo: BaseSubmissionRepository,
        verification_repo: BaseVerificationRunRepository,
    ) -> None:
        self.submission_repo = submission_repo
        self.verification_repo = verification_repo

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
        # Prioritize explicit run parameter, then submission test_code
        effective_test_cases = trusted_test_cases or submission.test_code

        state = {
            "submission_id": submission.id,
            "run_id": run.id,
            "source_code": submission.code,
            "language": submission.language.value,
            "filename": submission.filename,
            "requirement_ids": submission.requirement_ids,
            "trusted_test_cases": effective_test_cases,
            "timeout_seconds": timeout_seconds,
            "feedback_iterations": list(run.feedback_iterations or []),
            "telemetry": {},
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
            error_message=final_error,
            created_at=run.created_at,
            updated_at=now,
        )

        saved = await self.verification_repo.save(updated_run)
        logger.info(
            "Completed verification run %s with status %s (test count: %d, defect count: %d, iterations: %d)",
            run_id,
            saved.status.value,
            len(saved.test_results),
            len(saved.defect_reports),
            len(saved.feedback_iterations),
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


