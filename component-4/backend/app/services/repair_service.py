import ast
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from app.core.errors import (
    FileValidationException,
    InvalidInputException,
    ResourceNotFoundException,
)
from app.core.logging import logger
from app.repositories.base import (
    BaseRepairRepository,
    BaseSubmissionRepository,
    BaseTestSuiteRepository,
    BaseVerificationRunRepository,
)
from app.schemas.common import ProgrammingLanguage, SubmissionSource, VerificationStatus
from app.schemas.repair import (
    DefectResolutionComparison,
    DefectResolutionDetail,
    OverallResolutionVerdict,
    RepairAttempt,
    RepairResponseIngestRequest,
    RepairResponseStatus,
    ResolutionStatus,
    is_inconsistent_repair_attempt,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.verification import VerificationRunCreate
from app.services.defect_resolution_service import DefectResolutionService
from app.services.verification_service import VerificationService


class RepairService:
    """
    Service managing controlled local repair ingestion, re-verification execution,
    and defect resolution tracking.
    """

    def __init__(
        self,
        repair_repo: BaseRepairRepository,
        submission_repo: BaseSubmissionRepository,
        verification_repo: BaseVerificationRunRepository,
        verification_service: VerificationService,
        defect_resolution_service: Optional[DefectResolutionService] = None,
        test_suite_repo: Optional[BaseTestSuiteRepository] = None,
    ) -> None:
        self.repair_repo = repair_repo
        self.submission_repo = submission_repo
        self.verification_repo = verification_repo
        self.verification_service = verification_service
        self.defect_resolution_service = defect_resolution_service or DefectResolutionService()
        self.test_suite_repo = test_suite_repo

    async def ingest_repair_response(
        self,
        original_run_id: str,
        request: RepairResponseIngestRequest,
    ) -> RepairAttempt:
        """
        Securely ingests corrected source code for an eligible failed verification run.
        Validates syntax statically without host execution, creates a new submission,
        and records a RepairAttempt.
        """
        # 1. Validate original run existence and eligibility
        orig_run = await self.verification_repo.get_by_id(original_run_id)
        if not orig_run:
            raise ResourceNotFoundException("VerificationRun", original_run_id)

        # Check eligibility: must have failed tests, defects, or FAILED/ERROR status
        has_failed_tests = any(
            t.status.value == "FAILED" for t in (orig_run.test_results or [])
        )
        has_defects = len(orig_run.defect_reports or []) > 0
        is_failed_status = orig_run.status in [VerificationStatus.FAILED, VerificationStatus.ERROR]

        if not (has_failed_tests or has_defects or is_failed_status):
            raise InvalidInputException(
                f"Verification run '{original_run_id}' is not eligible for repair: "
                f"the run does not contain any recorded failures or defects."
            )

        # 2. Validate feedback iteration reference & human approval boundary
        feedback_iterations = orig_run.feedback_iterations or []
        target_iteration = None

        if request.feedback_iteration_id:
            for it in feedback_iterations:
                if it.iteration_id == request.feedback_iteration_id:
                    target_iteration = it
                    break
            if not target_iteration:
                raise ResourceNotFoundException(
                    "FeedbackIteration",
                    request.feedback_iteration_id,
                )
            if target_iteration.approval_status != "APPROVED":
                raise InvalidInputException(
                    f"Feedback iteration '{request.feedback_iteration_id}' has approval status "
                    f"'{target_iteration.approval_status}'. Corrected code ingestion requires approved feedback."
                )
        else:
            # Find the latest approved feedback iteration
            approved_iterations = [it for it in feedback_iterations if it.approval_status == "APPROVED"]
            if not approved_iterations:
                raise InvalidInputException(
                    f"Verification run '{original_run_id}' has no approved feedback iterations. "
                    "Technical feedback must be reviewed and approved before ingesting corrected code."
                )
            target_iteration = approved_iterations[-1]

        # Validate correlation ID match if both iteration and request specify it
        if request.correlation_id and target_iteration.correlation_id:
            if request.correlation_id.strip() != target_iteration.correlation_id.strip():
                raise InvalidInputException(
                    f"Correlation identifier mismatch: request correlation_id '{request.correlation_id}' "
                    f"does not match approved feedback iteration correlation_id '{target_iteration.correlation_id}'."
                )

        # 3. Fetch original submission
        orig_submission = await self.submission_repo.get_by_id(orig_run.submission_id)
        if not orig_submission:
            raise ResourceNotFoundException("Submission", orig_run.submission_id)

        # 4. Validate corrected code and filename security
        raw_filename = (request.filename or orig_submission.filename or "solution.py").strip()

        # Reject path traversal, absolute paths, null bytes, slashes
        if (
            "\x00" in raw_filename
            or "/" in raw_filename
            or "\\" in raw_filename
            or ".." in raw_filename
            or raw_filename in (".", "..")
        ):
            raise FileValidationException(
                "Invalid filename: path traversal sequences, absolute paths, or path separators are not permitted."
            )

        sanitized_filename = os.path.basename(raw_filename).strip()
        _, ext = os.path.splitext(sanitized_filename)
        if ext.lower() != ".py":
            raise FileValidationException(
                f"Invalid file extension '{ext}'. Only Python (.py) source artifacts are authorized for repair ingestion."
            )

        # Validate code text
        cleaned_code = request.corrected_code.strip()
        if not cleaned_code:
            raise FileValidationException("Corrected source code cannot be empty or whitespace only.")

        if len(cleaned_code.encode("utf-8")) > 500_000:
            raise FileValidationException("Corrected source code exceeds maximum permitted size of 500 KB.")

        # Static AST parsing on the host (NEVER execute code on host)
        try:
            ast.parse(request.corrected_code, filename=sanitized_filename)
        except SyntaxError as syn_err:
            raise FileValidationException(
                f"Corrected code contains syntax errors: {syn_err.msg} (line {syn_err.lineno})"
            )
        except Exception as parse_err:
            raise FileValidationException(f"Failed to parse source code statically: {parse_err}")

        # 5. Check idempotency for existing repair attempts (by content or external_repair_job_id)
        existing_attempts = await self.repair_repo.get_by_original_run_id(orig_run.id)
        for att in existing_attempts:
            same_code = (
                att.feedback_iteration_id == target_iteration.iteration_id
                and att.corrected_code
                and att.corrected_code.strip() == cleaned_code
            )
            same_job_id = bool(
                request.external_repair_job_id
                and att.external_repair_job_id
                and att.external_repair_job_id.strip() == request.external_repair_job_id.strip()
            )
            if same_code or same_job_id:
                logger.info(
                    "Idempotent repair ingestion detected (same_code=%s, same_job_id=%s): returning existing repair attempt %s",
                    same_code,
                    same_job_id,
                    att.id,
                )
                return att

        # 6. Preserve original submission: create a brand new submission for the corrected code
        # Retrieve authorized trusted test suite: prioritize test_suite_repo, then orig_submission.test_code, then telemetry
        trusted_test_code = None
        if self.test_suite_repo:
            if getattr(orig_run, "test_suite_id", None):
                suite = await self.test_suite_repo.get_by_id(orig_run.test_suite_id)
                if suite and suite.test_code:
                    trusted_test_code = suite.test_code
            if not trusted_test_code:
                suite = await self.test_suite_repo.get_by_run_id(orig_run.id)
                if suite and suite.test_code:
                    trusted_test_code = suite.test_code
        if not trusted_test_code:
            trusted_test_code = (
                orig_submission.test_code
                or (orig_run.execution_telemetry or {}).get("trusted_test_cases")
            )

        new_submission_id = f"sub-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        new_submission = CodeSubmissionResponse(
            id=new_submission_id,
            code=request.corrected_code,
            language=ProgrammingLanguage.PYTHON,
            filename=sanitized_filename,
            requirement_ids=list(orig_submission.requirement_ids or []),
            test_code=trusted_test_code,
            source_type=SubmissionSource.MANUAL_ENTRY,
            created_at=now,
            metadata={
                "parent_submission_id": orig_submission.id,
                "repair_for_run_id": orig_run.id,
                "repair_source": request.repair_source.value,
                "feedback_iteration_id": target_iteration.iteration_id,
            },
        )
        await self.submission_repo.save(new_submission)
        logger.info(
            "Created separate corrected submission %s (parent %s) for repair of run %s",
            new_submission.id,
            orig_submission.id,
            orig_run.id,
        )

        # 7. Record the RepairAttempt
        repair_id = f"rep-{uuid.uuid4().hex[:12]}"
        repair_attempt = RepairAttempt(
            repair_id=repair_id,
            id=repair_id,
            original_run_id=orig_run.id,
            original_submission_id=orig_submission.id,
            feedback_iteration_id=target_iteration.iteration_id,
            corrected_submission_id=new_submission.id,
            corrected_code=request.corrected_code,
            corrected_filename=sanitized_filename,
            filename=sanitized_filename,
            repair_source=request.repair_source,
            status=RepairResponseStatus.INGESTED,
            correlation_id=request.correlation_id,
            external_repair_job_id=request.external_repair_job_id,
            notes=request.notes,
            created_at=now,
            updated_at=now,
        )

        saved_attempt = await self.repair_repo.save(repair_attempt)
        logger.info(
            "Recorded repair attempt %s for run %s (iteration %s)",
            saved_attempt.id,
            orig_run.id,
            target_iteration.iteration_id,
        )
        return saved_attempt

    async def execute_reverification(
        self,
        original_run_id: str,
        repair_id: str,
        force_reverify: bool = False,
    ) -> RepairAttempt:
        """
        Executes re-verification for an ingested repair attempt using the existing Docker runner.
        Computes deterministic defect resolution comparison upon completion.
        """
        repair = await self.repair_repo.get_by_id(repair_id)
        if not repair or repair.original_run_id != original_run_id:
            raise ResourceNotFoundException("RepairAttempt", repair_id)

        # Concurrency / idempotency protection
        if repair.status == RepairResponseStatus.REVERIFYING:
            raise InvalidInputException(
                f"Re-verification is currently in progress for repair attempt '{repair_id}'."
            )

        if repair.status == RepairResponseStatus.REVERIFIED and not force_reverify:
            if repair.corrected_run_id:
                logger.info("Repair attempt %s has already been re-verified. Returning existing outcome.", repair_id)
                return repair

        orig_run = await self.verification_repo.get_by_id(original_run_id)
        if not orig_run:
            raise ResourceNotFoundException("VerificationRun", original_run_id)

        corr_submission = await self.submission_repo.get_by_id(repair.corrected_submission_id)
        if not corr_submission:
            raise ResourceNotFoundException("Submission", repair.corrected_submission_id)

        # Retrieve authorized trusted test suite from durable persistence
        # Priority: test_suite_repo for orig_run, then corr_submission.test_code, then orig_submission, then telemetry
        trusted_test_cases = None
        if self.test_suite_repo:
            if getattr(orig_run, "test_suite_id", None):
                suite = await self.test_suite_repo.get_by_id(orig_run.test_suite_id)
                if suite and suite.test_code:
                    trusted_test_cases = suite.test_code
            if not trusted_test_cases:
                suite = await self.test_suite_repo.get_by_run_id(orig_run.id)
                if suite and suite.test_code:
                    trusted_test_cases = suite.test_code
        if not trusted_test_cases:
            trusted_test_cases = corr_submission.test_code
        if not trusted_test_cases:
            orig_sub = await self.submission_repo.get_by_id(orig_run.submission_id)
            trusted_test_cases = (
                (orig_sub.test_code if orig_sub else None)
                or (orig_run.execution_telemetry or {}).get("trusted_test_cases")
            )


        # Validate syntax and availability; produce explicit BLOCKED / INCONCLUSIVE outcome if missing or incompatible
        is_incompatible = False
        incompatible_reason = ""
        if trusted_test_cases:
            try:
                ast.parse(trusted_test_cases, filename="trusted_test_check.py")
            except Exception as parse_err:
                is_incompatible = True
                incompatible_reason = f"Trusted test suite failed static validation: {parse_err}"

        if not trusted_test_cases or is_incompatible:
            reason = (
                incompatible_reason
                or "Original trusted test suite is unavailable; cannot safely execute re-verification."
            )
            logger.warning(
                "Cannot safely execute re-verification for repair %s: %s",
                repair.id,
                reason,
            )
            comparison = DefectResolutionComparison(
                original_run_id=orig_run.id,
                corrected_run_id=None,
                original_status=orig_run.status.value,
                corrected_status="BLOCKED",
                verdict=OverallResolutionVerdict.INCONCLUSIVE,
                original_defects_count=len(orig_run.defect_reports or []),
                resolved_defects_count=0,
                remaining_defects_count=0,
                new_defects_count=0,
                resolution_rate=0.0,
                test_comparisons=[],
                defect_comparisons=[
                    DefectResolutionDetail(
                        defect_id=d.defect_id,
                        title=d.title,
                        failed_test=d.failed_test or d.title or "unknown",
                        resolution_status=ResolutionStatus.INCONCLUSIVE,
                        original_assertion=d.assertion_or_exception,
                        notes=f"Re-verification blocked: {reason}",
                    )
                    for d in (orig_run.defect_reports or [])
                ],
                notes=reason,
            )
            repair.status = RepairResponseStatus.BLOCKED
            repair.corrected_run_id = None
            repair.comparison = comparison
            repair.notes = reason
            repair.updated_at = datetime.now(timezone.utc)
            return await self.repair_repo.save(repair)

        # Mark in progress
        repair.status = RepairResponseStatus.REVERIFYING
        repair.updated_at = datetime.now(timezone.utc)
        await self.repair_repo.save(repair)

        try:
            # Create a new verification run for the corrected submission
            new_run_payload = VerificationRunCreate(
                submission_id=corr_submission.id,
                triggered_by="repair_reverification",
                test_types=orig_run.requested_test_types or [],
                trusted_test_cases=trusted_test_cases,
            )
            new_run = await self.verification_service.create_verification_run(
                new_run_payload,
                execute_now=False,
            )

            # Execute re-verification using existing Docker sandbox runner
            logger.info(
                "Executing re-verification run %s for repair attempt %s",
                new_run.id,
                repair.id,
            )
            executed_run = await self.verification_service.execute_verification_run(
                run_id=new_run.id,
                trusted_test_cases=trusted_test_cases,
            )

            # Perform deterministic defect resolution comparison
            comparison = self.defect_resolution_service.compare_runs(
                original_run=orig_run,
                corrected_run=executed_run,
            )

            repair.corrected_run_id = executed_run.id
            repair.status = RepairResponseStatus.REVERIFIED
            repair.comparison = comparison
            repair.updated_at = datetime.now(timezone.utc)

            saved = await self.repair_repo.save(repair)
            logger.info(
                "Completed re-verification for repair %s. Verdict: %s (Resolution rate: %s%%)",
                repair.id,
                comparison.verdict.value,
                comparison.resolution_rate,
            )
            return saved

        except Exception as exc:
            logger.exception("Re-verification execution failed for repair attempt %s: %s", repair.id, exc)
            repair.status = RepairResponseStatus.FAILED
            repair.notes = (
                f"Re-verification execution encountered an internal error: {str(exc)}"
            )
            repair.updated_at = datetime.now(timezone.utc)
            await self.repair_repo.save(repair)
            raise

    async def get_repair_attempt(
        self,
        original_run_id: str,
        repair_id: str,
    ) -> RepairAttempt:
        """Retrieves a specific repair attempt by run and repair identifier."""
        repair = await self.repair_repo.get_by_id(repair_id)
        if not repair or repair.original_run_id != original_run_id:
            raise ResourceNotFoundException("RepairAttempt", repair_id)
        return repair

    async def list_repair_attempts(
        self,
        original_run_id: str,
    ) -> List[RepairAttempt]:
        """Lists all repair attempts associated with a verification run."""
        orig_run = await self.verification_repo.get_by_id(original_run_id)
        if not orig_run:
            raise ResourceNotFoundException("VerificationRun", original_run_id)
        return await self.repair_repo.get_by_original_run_id(original_run_id)

    async def get_repair_comparison(
        self,
        original_run_id: str,
        repair_id: str,
    ) -> DefectResolutionComparison:
        """Retrieves the before-and-after resolution comparison for a re-verified repair attempt."""
        repair = await self.get_repair_attempt(original_run_id, repair_id)
        if not repair.comparison:
            raise InvalidInputException(
                f"Repair attempt '{repair_id}' has not been re-verified yet. Status is '{repair.status.value}'."
            )
        return repair.comparison

    def is_inconsistent_repair(self, repair: RepairAttempt) -> bool:
        """
        Detects if a repair attempt record has an inconsistent lifecycle status:
        Marked REVERIFIED/VERIFIED without a genuine corrected_run_id, and with INCONCLUSIVE comparison.
        """
        return is_inconsistent_repair_attempt(repair)

    async def detect_inconsistent_repairs(self, run_id: Optional[str] = None) -> List[RepairAttempt]:
        """Scans for inconsistent repair attempts matching legacy missing-suite pattern."""
        if run_id:
            attempts = await self.repair_repo.get_by_original_run_id(run_id)
        else:
            attempts = await self.repair_repo.list_all()
        return [att for att in attempts if self.is_inconsistent_repair(att)]

    async def reconcile_repair_attempt(
        self,
        repair_id: str,
        dry_run: bool = False,
    ) -> RepairAttempt:
        """
        Narrowly scoped, idempotent reconciliation for a repair attempt record.
        Transitions REVERIFIED with null corrected_run_id and INCONCLUSIVE verdict to BLOCKED.
        Preserves original comparison, notes, and audit timestamps.
        """
        repair = await self.repair_repo.get_by_id(repair_id)
        if not repair:
            raise ResourceNotFoundException("RepairAttempt", repair_id)

        if not self.is_inconsistent_repair(repair):
            logger.info("Repair attempt %s is not inconsistent; no reconciliation needed.", repair_id)
            return repair

        logger.info(
            "Reconciling inconsistent repair attempt %s: transitioning %s -> BLOCKED",
            repair.repair_id,
            repair.status.value,
        )

        if dry_run:
            return repair

        repair.status = RepairResponseStatus.BLOCKED
        repair.corrected_run_id = None
        if repair.comparison:
            repair.comparison.corrected_run_id = None
            repair.comparison.corrected_status = "BLOCKED"
            repair.comparison.remaining_defects_count = 0
            if not repair.comparison.notes:
                repair.comparison.notes = "Re-verification blocked: original trusted test suite is unavailable."

        repair.updated_at = datetime.now(timezone.utc)
        return await self.repair_repo.save(repair)
