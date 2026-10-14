import uuid
from datetime import datetime, timezone
from typing import List, Optional
from app.core.errors import ResourceNotFoundException
from app.core.logging import logger
from app.repositories.base import BaseSubmissionRepository, BaseVerificationRunRepository
from app.schemas.common import VerificationStatus
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunListResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)


class VerificationService:
    """
    Manages verification runs.

    CRITICAL ARCHITECTURAL CONSTRAINTS (Phase 1):
    - Real testing agents, LangGraph orchestration, and test execution are scheduled for Phase 2.
    - Code is NOT executed during Phase 1.
    - Verification runs are initialized in PENDING status.
    - NO mock/fake passing test results or fabricated defects are generated.
    """

    def __init__(
        self,
        submission_repo: BaseSubmissionRepository,
        verification_repo: BaseVerificationRunRepository,
    ) -> None:
        self.submission_repo = submission_repo
        self.verification_repo = verification_repo

    async def create_verification_run(
        self, payload: VerificationRunCreate
    ) -> VerificationRunResponse:
        """
        Registers a new verification run in PENDING status for an existing submission.
        Does NOT execute code or fabricate test results in Phase 1.
        """
        # Ensure referenced submission exists
        submission = await self.submission_repo.get_by_id(payload.submission_id)
        if not submission:
            raise ResourceNotFoundException("Submission", payload.submission_id)

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        verification_run = VerificationRunResponse(
            id=run_id,
            submission_id=submission.id,
            status=VerificationStatus.PENDING,
            triggered_by=payload.triggered_by,
            requested_test_types=payload.test_types,
            test_results=[],
            defect_reports=[],
            feedback_iterations=[],
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
        return saved_run

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
