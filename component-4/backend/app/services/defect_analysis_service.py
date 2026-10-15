import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.schemas.common import DefectSeverity, TestResultStatus, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import TechnicalFeedbackPayload
from app.schemas.submission import SubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse


class DefectAnalysisService:
    """
    Evidence-based defect analysis service.

    Analyzes pytest execution outcomes from verification runs to extract structured,
    empirically verified defect reports without re-executing code or speculating on root causes.
    """

    # Common Python runtime exception class names
    RUNTIME_EXCEPTIONS = {
        "ZeroDivisionError",
        "TypeError",
        "ValueError",
        "IndexError",
        "KeyError",
        "AttributeError",
        "NameError",
        "UnboundLocalError",
        "FileNotFoundError",
        "ImportError",
        "ModuleNotFoundError",
        "RecursionError",
        "MemoryError",
        "OverflowError",
        "NotImplementedError",
        "RuntimeError",
        "Exception",
    }

    def analyze_run(
        self,
        run: VerificationRunResponse,
        submission: Optional[SubmissionResponse] = None,
    ) -> List[DefectReport]:
        """
        Analyzes test results of a verification run and produces structured defect reports.
        """
        req_id = submission.requirement_ids[0] if submission and submission.requirement_ids else None
        filename = submission.filename if submission else None
        return self.analyze_test_results(
            run_id=run.id,
            submission_id=run.submission_id,
            status=run.status.value if isinstance(run.status, VerificationStatus) else str(run.status),
            test_results=run.test_results,
            affected_filename=filename,
            execution_telemetry=run.execution_telemetry,
            error_message=run.error_message,
            requirement_id=req_id,
        )

    def analyze_test_results(
        self,
        run_id: str,
        submission_id: str,
        status: str,
        test_results: List[TestResult],
        affected_filename: Optional[str] = None,
        execution_telemetry: Optional[dict] = None,
        error_message: Optional[str] = None,
        requirement_id: Optional[str] = None,
    ) -> List[DefectReport]:
        """
        Analyzes test results and produces structured defect reports.

        Guarantees:
        - If run status is PASSED or PENDING: returns empty list (zero defects).
        - If run status is ERROR due to sandbox infrastructure: returns empty list.
        - Idempotent: repeated analysis produces identical defect IDs without duplicates.
        - Never executes submitted code.
        - Localizes line numbers strictly when supported by traceback evidence.
        """
        # Rule: PASSED verification -> no defect reports
        if status == VerificationStatus.PASSED.value:
            logger.debug("Verification run %s PASSED; 0 defect reports generated.", run_id)
            return []

        # Rule: PENDING verification -> do not claim a defect exists
        if status == VerificationStatus.PENDING.value:
            logger.debug("Verification run %s PENDING; no defects claimed.", run_id)
            return []

        # Rule: Infrastructure errors must be classified separately from application code defects
        if self._is_infrastructure_failure_raw(status, execution_telemetry, error_message, test_results):
            logger.info("Verification run %s classified as infrastructure error; 0 code defects.", run_id)
            return []

        # Identify candidate failed test results
        failed_tests = [
            t for t in test_results
            if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
        ]

        if not failed_tests:
            logger.debug("No failed test cases in verification run %s; 0 defect reports.", run_id)
            return []

        effective_filename = affected_filename.strip() if affected_filename and affected_filename.strip() else "solution.py"
        defect_reports: List[DefectReport] = []
        seen_test_names = set()

        for test in failed_tests:
            test_name = test.name or test.test_name or test.test_id
            # Idempotency / deduplication within the run
            if test_name in seen_test_names:
                continue
            seen_test_names.add(test_name)

            report = self._analyze_test_failure(
                run_id=run_id,
                submission_id=submission_id,
                test=test,
                affected_filename=effective_filename,
                requirement_id=requirement_id,
            )
            defect_reports.append(report)

        logger.info(
            "Analyzed verification run %s: generated %d evidence-based defect report(s)",
            run_id,
            len(defect_reports),
        )
        return defect_reports

    def _is_infrastructure_failure_raw(
        self,
        status: str,
        execution_telemetry: Optional[dict],
        error_message: Optional[str],
        test_results: List[TestResult],
    ) -> bool:
        telemetry = execution_telemetry or {}
        if telemetry.get("docker_available") is False or telemetry.get("image_ready") is False:
            return True
        err_msg = (error_message or "").lower()
        if "infrastructure isolation failure" in err_msg or "docker isolation unavailable" in err_msg:
            return True
        if "sandbox runner image unavailable" in err_msg or "sandbox image failure" in err_msg:
            return True
        if status == VerificationStatus.ERROR.value and not test_results:
            return True
        return False


    def _is_infrastructure_failure(self, run: VerificationRunResponse) -> bool:
        """Determines if the verification run failed due to container or host infrastructure."""
        telemetry = run.execution_telemetry or {}
        if telemetry.get("docker_available") is False or telemetry.get("image_ready") is False:
            return True
        error_msg = (run.error_message or "").lower()
        if "infrastructure isolation failure" in error_msg or "docker isolation unavailable" in error_msg:
            return True
        if "sandbox runner image unavailable" in error_msg or "sandbox image failure" in error_msg:
            return True
        # If there are no test results and status is ERROR, it was an environment/collection failure
        if run.status == VerificationStatus.ERROR and not run.test_results:
            return True
        return False

    def _determine_affected_file(self, submission: Optional[SubmissionResponse]) -> str:
        """Determines the canonical affected source filename from submission metadata."""
        if submission:
            if submission.filename and submission.filename.strip():
                return submission.filename.strip()
        return "solution.py"

    def _analyze_test_failure(
        self,
        run_id: str,
        submission_id: str,
        test: TestResult,
        affected_filename: str,
        requirement_id: Optional[str] = None,
    ) -> DefectReport:
        """Analyzes a single failed test result and extracts empirical evidence."""
        test_name = test.name or test.test_name or test.test_id
        error_msg = test.error_message or ""
        stack_trace = test.stack_trace or ""
        combined_text = f"{error_msg}\n{stack_trace}".strip()

        # Deterministic unique defect ID based on run_id and test_name
        defect_id = f"def-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run_id}:{test_name}').hex[:12]}"

        # Categorize failure and extract diagnostic details
        category, assertion_or_exception, severity = self._classify_failure(test, error_msg, stack_trace)

        # Reliably extract expected vs actual values if assertion diff is present
        expected_val, actual_val = self._extract_expected_and_actual(error_msg, stack_trace)

        # Extract localized source line number strictly if referenced in traceback for the affected file
        line_number = self._extract_localized_line_number(stack_trace, affected_filename)

        # Diagnostic traceback excerpt
        traceback_excerpt = self._extract_traceback_excerpt(stack_trace, error_msg)

        # Title and description strictly using evidence-based phrasing
        title = f"Observed {category.replace('_', ' ').title()} in {test_name}"
        desc = (
            f"Test case '{test_name}' failed under pytest execution. "
            f"Observed diagnostic: {assertion_or_exception or 'Assertion failed without explicit message'}."
        )

        return DefectReport(
            defect_id=defect_id,
            verification_run_id=run_id,
            submission_id=submission_id,
            requirement_id=requirement_id,
            title=title,
            severity=severity,
            description=desc,
            file_path=affected_filename,
            line_number=line_number,
            failed_test=test_name,
            failure_category=category,
            assertion_or_exception=assertion_or_exception,
            expected_value=expected_val,
            actual_value=actual_val,
            traceback_excerpt=traceback_excerpt,
            evidence_references={
                "test_id": test.test_id,
                "test_status": test.status.value,
                "duration_ms": test.duration_ms,
            },
            tags=[category.lower(), f"severity:{severity.value.lower()}"],
            created_at=datetime.now(timezone.utc),
        )

    def _classify_failure(
        self,
        test: TestResult,
        error_msg: str,
        stack_trace: str,
    ) -> Tuple[str, str, DefectSeverity]:
        """
        Classifies failure category, diagnostic summary, and deterministic severity.

        Deterministic Rules:
        - TIMEOUT_ERROR -> CRITICAL
        - SYNTAX_ERROR -> CRITICAL
        - RUNTIME_EXCEPTION -> CRITICAL
        - ASSERTION_FAILURE -> HIGH
        """
        combined = f"{error_msg}\n{stack_trace}".strip()

        # 1. Timeout Check
        if test.status == TestResultStatus.TIMEOUT or "timed out" in combined.lower():
            return (
                "TIMEOUT_ERROR",
                error_msg or "Execution exceeded container timeout limit",
                DefectSeverity.CRITICAL,
            )

        # 2. Syntax Error Check
        if "SyntaxError" in combined:
            syntax_match = re.search(r"(SyntaxError:[^\n]+)", combined)
            diag = syntax_match.group(1) if syntax_match else "SyntaxError in submitted source code"
            return (
                "SYNTAX_ERROR",
                diag,
                DefectSeverity.CRITICAL,
            )

        # 3. Runtime Exceptions (ZeroDivisionError, TypeError, IndexError, etc.)
        for exc in self.RUNTIME_EXCEPTIONS:
            exc_pattern = re.compile(rf"({exc}:[^\n]+)")
            match = exc_pattern.search(combined)
            if match:
                return (
                    "RUNTIME_EXCEPTION",
                    match.group(1).strip(),
                    DefectSeverity.CRITICAL,
                )

        # Check for unhandled exception in traceback: "E       <ExceptionClass>: <msg>"
        exc_line_match = re.search(r"E\s+([A-Za-z0-9_]+Error:[^\n]+)", combined)
        if exc_line_match and "AssertionError" not in exc_line_match.group(1):
            return (
                "RUNTIME_EXCEPTION",
                exc_line_match.group(1).strip(),
                DefectSeverity.CRITICAL,
            )

        # 4. Assertion Failure
        if "assert" in combined.lower() or "AssertionError" in combined:
            # Look for "assert actual == expected" or "AssertionError: ..."
            assert_match = re.search(r"(?:E\s+|AssertionError:\s*)(assert\s+[^\n]+)", combined)
            if assert_match:
                assertion_detail = assert_match.group(1).strip()
            elif error_msg:
                assertion_detail = error_msg.strip()
            else:
                assertion_detail = "Assertion failed"
            return (
                "ASSERTION_FAILURE",
                assertion_detail,
                DefectSeverity.HIGH,
            )

        # Fallback if diagnostic message is missing or unclassified
        diag = error_msg.strip() if error_msg else "Test execution failed without detailed diagnostic message."
        return (
            "ASSERTION_FAILURE",
            diag,
            DefectSeverity.HIGH,
        )

    def _extract_expected_and_actual(
        self,
        error_msg: str,
        stack_trace: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Extracts expected and actual values when reliably present in pytest assertion output.
        Avoids guessing or fabricating values.
        """
        combined = f"{error_msg}\n{stack_trace}"

        # Prioritize evaluated pytest failure line: "E       assert <actual> == <expected>"
        e_match = re.search(r"E\s+assert\s+(.+?)\s*==\s*([^\n\r]+)", combined)
        if e_match:
            actual = e_match.group(1).strip()
            expected = e_match.group(2).strip()
            return (expected, actual)

        # Fallback to general assertion line
        match = re.search(r"assert\s+(.+?)\s*==\s*([^\n\r]+)", combined)
        if match:
            actual = match.group(1).strip()
            expected = match.group(2).strip()
            return (expected, actual)

        # Pytest detailed diff pattern (- expected, + actual)
        diff_match = re.search(r"-\s*([^\n\r]+)\s*[\r\n]+\+\s*([^\n\r]+)", combined)
        if diff_match:
            expected = diff_match.group(1).strip()
            actual = diff_match.group(2).strip()
            return (expected, actual)

        return (None, None)


    def _extract_localized_line_number(
        self,
        stack_trace: str,
        affected_filename: str,
    ) -> Optional[int]:
        """
        Extracts source line number strictly if explicitly cited in the traceback
        for the submitted source code file. Does NOT guess or invent line numbers.
        """
        if not stack_trace or not affected_filename:
            return None

        base_name = affected_filename.replace("\\", "/").split("/")[-1]
        candidate_names = [base_name]
        if base_name != "solution.py":
            candidate_names.append("solution.py")

        for name in candidate_names:
            esc = re.escape(name)
            # Short format: solution.py:12:
            short_matches = re.findall(rf"{esc}:(\d+):", stack_trace, re.IGNORECASE)
            if short_matches:
                try:
                    return int(short_matches[-1])
                except ValueError:
                    pass

            # Standard format: "solution.py", line 12
            std_matches = re.findall(rf'{esc}", line (\d+)', stack_trace, re.IGNORECASE)
            if std_matches:
                try:
                    return int(std_matches[-1])
                except ValueError:
                    pass

        return None


    def _extract_traceback_excerpt(
        self,
        stack_trace: str,
        error_msg: str,
    ) -> Optional[str]:
        """Returns a relevant, clean excerpt of the diagnostic traceback."""
        if stack_trace and stack_trace.strip():
            lines = [line.rstrip() for line in stack_trace.strip().split("\n")]
            # Retain up to the most relevant 20 lines without clutter
            if len(lines) > 20:
                excerpt_lines = lines[-20:]
            else:
                excerpt_lines = lines
            return "\n".join(excerpt_lines)

        if error_msg and error_msg.strip():
            return error_msg.strip()

        return None

    def prepare_technical_feedback(
        self,
        run_id: str,
        submission_id: str,
        defect_reports: List[DefectReport],
        test_results: List[TestResult],
    ) -> TechnicalFeedbackPayload:
        """
        Prepares the internal structured technical feedback representation for Component 3.
        Does NOT transmit data or call external APIs; purely constructs the validated model.
        """
        failed_assertions = [
            d.assertion_or_exception
            for d in defect_reports
            if d.assertion_or_exception
        ]
        error_logs = [
            d.traceback_excerpt
            for d in defect_reports
            if d.traceback_excerpt
        ]
        affected_files = list({
            d.file_path for d in defect_reports if d.file_path
        })
        test_failure_details = [
            {
                "test_id": t.test_id,
                "name": t.name or t.test_name,
                "status": t.status.value,
                "duration_ms": t.duration_ms,
                "error_message": t.error_message,
            }
            for t in test_results
            if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
        ]

        failed_tests = [
            d.failed_test for d in defect_reports if d.failed_test
        ]
        defect_ids = [d.defect_id for d in defect_reports]
        feedback_id = f"fb-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run_id}:{len(defect_reports)}').hex[:12]}"

        return TechnicalFeedbackPayload(
            feedback_id=feedback_id,
            verification_run_id=run_id,
            submission_id=submission_id,
            failed_tests=failed_tests,
            failed_assertions=failed_assertions,
            error_logs=error_logs,
            affected_files=affected_files,
            defect_ids=defect_ids,
            test_failure_details=test_failure_details,
            generated_at=datetime.now(timezone.utc),
        )

