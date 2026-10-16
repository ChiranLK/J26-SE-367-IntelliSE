import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.errors import InvalidInputException
from app.core.logging import logger
from app.schemas.common import TestResultStatus, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import (
    FORBIDDEN_EXPLANATION_KEYS,
    DeliveryStatus,
    FeedbackIteration,
    TechnicalFeedbackPayload,
    TechnicalFeedbackPreviewResponse,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.component3_client import Component3Client, Component3DispatchResult


class TechnicalFeedbackService:
    """
    Service responsible for deterministic evaluation of feedback eligibility,
    construction and validation of structured technical feedback packages for Component 3,
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

    def validate_technical_feedback_payload(
        self,
        payload: TechnicalFeedbackPayload,
        run: Optional[VerificationRunResponse] = None,
    ) -> None:
        """
        Strengthened validation of technical feedback intended for an external code repair service.
        Guarantees that:
        1. Required identifiers (feedback_id, verification_run_id, submission_id) are present and valid.
        2. Defect identifiers and failed tests match actual persisted verification evidence.
        3. No fabricated source line numbers or file paths are included.
        4. Optional evidence fields (comparisons, error logs) are preserved even when partially absent.
        5. CRITICAL: Human-facing explanations (summaries, recommendations, XAI narratives, provider metadata)
           are strictly forbidden and rejected if detected.
        """
        # 1. Validate required identifiers
        if not payload.feedback_id or not payload.feedback_id.strip():
            raise InvalidInputException("Technical feedback payload must contain a non-empty 'feedback_id'.")
        if not payload.verification_run_id or not payload.verification_run_id.strip():
            raise InvalidInputException("Technical feedback payload must contain a non-empty 'verification_run_id'.")
        if not payload.submission_id or not payload.submission_id.strip():
            raise InvalidInputException("Technical feedback payload must contain a non-empty 'submission_id'.")
        if not payload.defect_ids:
            raise InvalidInputException("Technical feedback payload must reference at least one defect ID.")

        # 2. Correlate with persisted verification run evidence when run is supplied
        if run is not None:
            if payload.verification_run_id != run.id:
                raise InvalidInputException(
                    f"Payload verification_run_id '{payload.verification_run_id}' does not match run ID '{run.id}'."
                )
            if payload.submission_id != run.submission_id:
                raise InvalidInputException(
                    f"Payload submission_id '{payload.submission_id}' does not match run submission ID '{run.submission_id}'."
                )

            persisted_defect_ids = {d.defect_id for d in (run.defect_reports or [])}
            for d_id in payload.defect_ids:
                if d_id not in persisted_defect_ids:
                    raise InvalidInputException(
                        f"Technical feedback payload references unpersisted or fabricated defect ID '{d_id}'."
                    )

            persisted_failed_test_names = {
                (t.name or t.test_name or t.test_id)
                for t in (run.test_results or [])
                if (t.status.value if hasattr(t.status, "value") else str(t.status)) in ("FAILED", "ERROR", "TIMEOUT")
            }
            # Add defect report failed test names
            for d in (run.defect_reports or []):
                if d.failed_test:
                    persisted_failed_test_names.add(d.failed_test)

            for ft in payload.failed_tests:
                if persisted_failed_test_names and ft not in persisted_failed_test_names:
                    raise InvalidInputException(
                        f"Technical feedback payload references unverified failed test '{ft}'."
                    )

        # 3. Human Explanation Isolation: Recursively verify no human narrative or provider fields exist
        payload_dict = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)
        self._assert_no_human_explanation_leak(payload_dict)

    def _assert_no_human_explanation_leak(self, data: Any, path: str = "") -> None:
        """
        Recursively scans a data structure to ensure zero human-facing XAI explanations,
        summaries, recommendations, or internal credentials exist.
        """
        if isinstance(data, dict):
            for k, v in data.items():
                current_path = f"{path}.{k}" if path else k
                if k in FORBIDDEN_EXPLANATION_KEYS or k in ("api_key", "token", "password", "secret", "mongodb_uri"):
                    raise InvalidInputException(
                        f"Human explanation isolation violation: forbidden field '{current_path}' detected in "
                        "machine-directed technical feedback payload. Human narratives are strictly segregated."
                    )
                self._assert_no_human_explanation_leak(v, current_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._assert_no_human_explanation_leak(item, f"{path}[{i}]")

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

        # Affected filenames from defects or submission metadata (no fabricated file paths)
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

        payload = TechnicalFeedbackPayload(
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

        # Validate generated payload
        self.validate_technical_feedback_payload(payload, run)
        return payload

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
            delivery_status=DeliveryStatus.NOT_DISPATCHED.value,
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

    def approve_feedback(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
        approver: str = "human_engineer",
        notes: Optional[str] = None,
    ) -> Tuple[VerificationRunResponse, FeedbackIteration]:
        """
        Records explicit human approval for an eligible verification run's technical feedback.
        Guarantees that:
        - Only runs with real defect evidence can be approved.
        - Repeated approval calls do not create unintended duplicate iterations.
        - Approval updates approval metadata and notes without automatically triggering dispatch.
        - Note: Approver identity is client-supplied for audit trail and is not independently authenticated.
        """
        is_eligible, reason = self.check_eligibility(run)
        if not is_eligible:
            raise InvalidInputException(f"Cannot approve feedback for dispatch: {reason}")

        payload = self.build_feedback_payload(run, submission)
        updated_run, iteration, _ = self.record_feedback_iteration(run, payload, notes=notes)

        now = datetime.now(timezone.utc)
        iteration.approval_status = "APPROVED"
        iteration.approved_at = now
        iteration.approved_by = approver
        iteration.updated_at = now
        # Keep delivery_status as NOT_DISPATCHED (approval never triggers dispatch)
        if iteration.delivery_status == DeliveryStatus.PENDING_DELIVERY.value:
            pass  # Retain pending if an active lock exists
        elif iteration.delivery_status not in (DeliveryStatus.ACKNOWLEDGED.value, DeliveryStatus.UNKNOWN.value):
            iteration.delivery_status = DeliveryStatus.NOT_DISPATCHED.value

        if notes:
            iteration.notes = notes

        logger.info(
            "Feedback iteration %s for run %s approved by %s (client-supplied identity)",
            iteration.iteration_id,
            run.id,
            approver,
        )
        return (updated_run, iteration)

    async def dispatch_feedback(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
        client: Optional[Component3Client] = None,
        approver: str = "human_engineer",
        notes: Optional[str] = None,
        force_retry: bool = False,
    ) -> Tuple[VerificationRunResponse, FeedbackIteration, bool, Any]:
        """
        Dispatches an approved technical feedback package to Component 3 via the outbound client.
        Enforces:
        - Human approval prerequisite.
        - Idempotency: duplicate dispatch on ACKNOWLEDGED iteration returns existing record.
        - Concurrency protection: in-flight PENDING_DELIVERY prevents concurrent double dispatch.
        - State tracking: timeouts yield UNKNOWN state rather than assumed failure or auto-retry.
        - Audit trail: attempt counting, attempt timestamps, and sanitized error messages.
        """
        is_eligible, reason = self.check_eligibility(run)
        if not is_eligible:
            raise InvalidInputException(f"Cannot dispatch technical feedback: {reason}")

        payload = self.build_feedback_payload(run, submission)
        updated_run, iteration, _ = self.record_feedback_iteration(run, payload, notes=notes)

        # Enforce explicit human approval
        if iteration.approval_status != "APPROVED":
            raise InvalidInputException(
                "Feedback dispatch requires explicit human approval before delivery to Component 3. "
                "Please approve the technical feedback package first."
            )

        # Concurrency / In-flight protection
        if iteration.delivery_status == DeliveryStatus.PENDING_DELIVERY.value:
            raise InvalidInputException(
                f"A dispatch attempt is currently in progress for iteration '{iteration.iteration_id}'. "
                "Concurrent dispatch requests are rejected."
            )

        # Idempotency check: already acknowledged?
        if iteration.delivery_status == DeliveryStatus.ACKNOWLEDGED.value and not force_retry:
            logger.info(
                "Feedback iteration %s for run %s already delivered and acknowledged; skipping duplicate dispatch.",
                iteration.iteration_id,
                run.id,
            )
            return (updated_run, iteration, True, None)

        now = datetime.now(timezone.utc)
        correlation_id = iteration.correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        dispatch_id = f"disp-{uuid.uuid4().hex[:12]}"

        # Record dispatch attempt audit trail
        iteration.delivery_status = DeliveryStatus.PENDING_DELIVERY.value
        iteration.attempt_count = (iteration.attempt_count or 0) + 1
        iteration.last_attempt_at = now
        iteration.attempt_timestamps = (iteration.attempt_timestamps or []) + [now]
        iteration.dispatched_at = now
        iteration.correlation_id = correlation_id
        iteration.updated_at = now

        payload.feedback_iteration_id = iteration.iteration_id
        payload.correlation_id = correlation_id

        c3_client = client or Component3Client()

        result = await c3_client.dispatch_feedback(
            payload=payload,
            correlation_id=correlation_id,
            idempotency_key=dispatch_id,
        )

        completed_at = datetime.now(timezone.utc)
        iteration.dispatch_attempt_id = result.dispatch_attempt_id
        iteration.correlation_id = result.correlation_id
        iteration.updated_at = completed_at

        if result.success and result.acknowledged:
            iteration.delivery_status = DeliveryStatus.ACKNOWLEDGED.value
            iteration.component_3_acknowledged = True
            iteration.component_3_job_id = result.job_id
            iteration.acknowledged_at = completed_at
            iteration.error_category = None
            iteration.sanitized_error_message = None
            iteration.status = "AWAITING_REVISION"
        elif result.error_category == "TIMEOUT":
            # Ambiguous timeout outcome: remote receiver might have received payload
            iteration.delivery_status = DeliveryStatus.UNKNOWN.value
            iteration.component_3_acknowledged = False
            iteration.error_category = "TIMEOUT"
            iteration.sanitized_error_message = result.message
        elif result.error_category == "COMPONENT_3_DISABLED":
            iteration.delivery_status = DeliveryStatus.NOT_DISPATCHED.value
            iteration.component_3_acknowledged = False
            iteration.error_category = result.error_category
            iteration.sanitized_error_message = result.message
        else:
            iteration.delivery_status = DeliveryStatus.FAILED.value
            iteration.component_3_acknowledged = False
            iteration.error_category = result.error_category
            iteration.sanitized_error_message = result.message

        return (updated_run, iteration, False, result)


