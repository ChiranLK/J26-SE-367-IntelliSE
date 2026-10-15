import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.schemas.common import TestResultStatus, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import (
    FeedbackIteration,
    TechnicalFeedbackPayload,
    TechnicalFeedbackPreviewResponse,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse


class TechnicalFeedbackService:
    """
    Service responsible for deterministic evaluation of feedback eligibility,
    construction of structured technical feedback packages for Component 3,
    and idempotent feedback iteration tracking.
    """

    SCHEMA_VERSION = "1.0"
    MAX_EXCERPT_LINES = 15
    MAX_LOG_LINE_CHARS = 500

    def check_eligibility(self, run: VerificationRunResponse) -> Tuple[bool, str]:
        """
        Applies explicit deterministic rules to evaluate if a verification run is eligible
        for technical feedback generation.
        """
        # Rule 1: PASSED verification -> no corrective feedback payload
        if run.status == VerificationStatus.PASSED:
            return (
                False,
                "Verification run passed successfully; zero defects detected, so no corrective feedback is applicable.",
            )

        # Rule 2: PENDING or RUNNING verification -> not eligible
        if run.status in (VerificationStatus.PENDING, VerificationStatus.RUNNING):
            return (
                False,
                f"Verification run is currently in '{run.status.value}' state. Feedback can only be evaluated after verification completes.",
            )

        # Rule 3: Infrastructure-only failure -> do not misrepresent as defective application code
        if self._is_infrastructure_failure(run):
            return (
                False,
                "Verification run failed due to container sandbox or host infrastructure isolation issues. "
                "Infrastructure errors are segregated from application-code defects.",
            )

        # Rule 4: FAILED run without application code defects
        if not run.defect_reports:
            # Check if there are failed test results that have not yet generated defect reports
            failed_tests = [
                t for t in run.test_results
                if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
            ]
            if not failed_tests:
                return (
                    False,
                    "No application-code defects were detected for this verification run; corrective feedback is not applicable.",
                )

        # Rule 5: FAILED run with application code defects -> eligible
        defect_count = len(run.defect_reports)
        return (
            True,
            f"Verification failed with {defect_count} application-code defect(s) detected across test assertions.",
        )

    def _is_infrastructure_failure(self, run: VerificationRunResponse) -> bool:
        """Determines if the verification run failed purely due to infrastructure/environment."""
        telemetry = run.execution_telemetry or {}
        if telemetry.get("docker_available") is False or telemetry.get("image_ready") is False:
            return True
        error_msg = (run.error_message or "").lower()
        if "infrastructure isolation failure" in error_msg or "docker isolation unavailable" in error_msg:
            return True
        if "sandbox runner image unavailable" in error_msg or "sandbox image failure" in error_msg:
            return True
        if run.status == VerificationStatus.ERROR and not run.test_results:
            return True
        return False

    def build_feedback_payload(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> TechnicalFeedbackPayload:
        """
        Constructs a structured, schema-compliant technical feedback package directly
        from persisted verification results and defect reports.
        """
        defect_reports = run.defect_reports or []
        test_results = run.test_results or []

        # Deterministic feedback package ID
        feedback_id = f"fb-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:{len(defect_reports)}').hex[:12]}"

        # Affected filenames from defects or submission metadata
        affected_files_set = set()
        for d in defect_reports:
            if d.file_path and d.file_path.strip():
                affected_files_set.add(d.file_path.strip())

        if not affected_files_set and submission and submission.filename:
            affected_files_set.add(submission.filename.strip())

        if not affected_files_set:
            affected_files_set.add("solution.py")

        affected_files = sorted(list(affected_files_set))

        # Failed test names
        failed_tests_set = set()
        for d in defect_reports:
            if d.failed_test:
                failed_tests_set.add(d.failed_test)
        if not failed_tests_set:
            for t in test_results:
                if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT):
                    failed_tests_set.add(t.name or t.test_name or t.test_id)
        failed_tests = sorted(list(failed_tests_set))

        # Failed assertions and value comparisons
        failed_assertions: List[str] = []
        value_comparisons: List[Dict[str, Any]] = []
        defect_ids: List[str] = []

        for d in defect_reports:
            defect_ids.append(d.defect_id)
            if d.assertion_or_exception:
                failed_assertions.append(d.assertion_or_exception)

            comparison = {
                "test_name": d.failed_test or d.title,
                "defect_id": d.defect_id,
                "expected": d.expected_value,
                "observed": d.actual_value,
                "assertion": d.assertion_or_exception,
            }
            value_comparisons.append(comparison)

        # Sanitize and bound error logs
        error_logs: List[str] = []
        for d in defect_reports:
            if d.traceback_excerpt:
                clean_lines = [
                    line[:self.MAX_LOG_LINE_CHARS]
                    for line in d.traceback_excerpt.strip().split("\n")
                ]
                truncated = "\n".join(clean_lines[-self.MAX_EXCERPT_LINES:])
                error_logs.append(truncated)
            elif d.assertion_or_exception:
                error_logs.append(d.assertion_or_exception[:self.MAX_LOG_LINE_CHARS])

        if not error_logs and run.error_message:
            error_logs.append(run.error_message[:self.MAX_LOG_LINE_CHARS])

        # Sanitized evidence references (no credentials, tokens, or environment data)
        raw_telemetry = run.execution_telemetry or {}
        evidence_references = {
            "total_tests": len(test_results),
            "failed_tests_count": len(failed_tests),
            "defect_count": len(defect_reports),
            "exit_code": raw_telemetry.get("exit_code"),
            "duration_ms": raw_telemetry.get("duration_ms"),
            "is_timeout": raw_telemetry.get("is_timeout", False),
        }

        test_failure_details = [
            {
                "test_id": t.test_id,
                "name": t.name or t.test_name,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "duration_ms": t.duration_ms,
                "error_message": t.error_message,
            }
            for t in test_results
            if (t.status.value if hasattr(t.status, "value") else str(t.status)) in ("FAILED", "ERROR", "TIMEOUT")
        ]

        return TechnicalFeedbackPayload(
            feedback_id=feedback_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status=run.status.value,
            affected_files=affected_files,
            failed_tests=failed_tests,
            failed_assertions=failed_assertions,
            value_comparisons=value_comparisons,
            error_logs=error_logs,
            test_failure_details=test_failure_details,
            defect_ids=defect_ids,
            evidence_references=evidence_references,
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    def get_feedback_preview(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> TechnicalFeedbackPreviewResponse:
        """
        Generates a deterministic read-only preview of technical feedback without side-effects.
        """
        is_eligible, reason = self.check_eligibility(run)
        now = datetime.now(timezone.utc)

        if not is_eligible:
            return TechnicalFeedbackPreviewResponse(
                eligible=False,
                reason=reason,
                feedback=None,
                generated_at=now,
            )

        payload = self.build_feedback_payload(run, submission)
        return TechnicalFeedbackPreviewResponse(
            eligible=True,
            reason=reason,
            feedback=payload,
            generated_at=now,
        )

    def record_feedback_iteration(
        self,
        run: VerificationRunResponse,
        payload: TechnicalFeedbackPayload,
        notes: Optional[str] = None,
    ) -> Tuple[VerificationRunResponse, FeedbackIteration, bool]:
        """
        Idempotently records a feedback iteration on the verification run record.
        Preserves existing history and prevents duplicate iterations for identical defects.
        Returns: (updated_run, iteration, created_flag)
        """
        existing_iterations = run.feedback_iterations or []
        payload_defect_ids = set(payload.defect_ids)

        # Check for existing iteration with identical defect IDs
        for it in existing_iterations:
            if set(it.defect_ids) == payload_defect_ids:
                logger.debug(
                    "Iteration %s on run %s already covers defect IDs %s; skipping duplicate creation.",
                    it.iteration_id,
                    run.id,
                    payload_defect_ids,
                )
                return (run, it, False)

        # Increment iteration sequence
        iteration_number = len(existing_iterations) + 1
        iteration_id = f"iter-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:{iteration_number}').hex[:12]}"
        now = datetime.now(timezone.utc)

        iteration = FeedbackIteration(
            iteration_id=iteration_id,
            iteration_number=iteration_number,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            defects_count=len(payload.defect_ids),
            defect_ids=payload.defect_ids,
            status="AWAITING_REVISION",
            component_3_acknowledged=False,
            notes=notes or f"Generated technical feedback cycle #{iteration_number}",
            payload=payload,
            created_at=now,
        )

        run.feedback_iterations.append(iteration)
        run.updated_at = now
        logger.info(
            "Recorded feedback iteration %s (#%d) for verification run %s",
            iteration_id,
            iteration_number,
            run.id,
        )
        return (run, iteration, True)
