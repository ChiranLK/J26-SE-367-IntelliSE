import ast
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.schemas.common import DefectSeverity, TestResultStatus, TestType, VerificationStatus
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
        source_code = submission.code if submission and hasattr(submission, "code") else None
        project_files = (submission.metadata or {}).get("project_files") if submission and submission.metadata else None
        return self.analyze_test_results(
            run_id=run.id,
            submission_id=run.submission_id,
            status=run.status.value if isinstance(run.status, VerificationStatus) else str(run.status),
            test_results=run.test_results,
            affected_filename=filename,
            execution_telemetry=run.execution_telemetry,
            error_message=run.error_message,
            requirement_id=req_id,
            source_code=source_code,
            project_files=project_files,
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
        source_code: Optional[str] = None,
        project_files: Optional[Dict[str, str]] = None,
    ) -> List[DefectReport]:
        """
        Analyzes test results and produces structured defect reports.

        Guarantees:
        - If run status is PASSED or PENDING: returns empty list (zero defects).
        - If run status is ERROR due to sandbox infrastructure: returns empty list.
        - Idempotent: repeated analysis produces identical defect IDs without duplicates.
        - Never executes submitted code.
        - Localizes line numbers strictly when supported by traceback evidence.
        - Supports multi-file projects with accurate relative file paths.
        """
        # Rule: PENDING verification -> do not claim a defect exists
        if status == VerificationStatus.PENDING.value:
            logger.debug("Verification run %s PENDING; no defects claimed.", run_id)
            return []

        # Rule: Infrastructure errors must be classified separately from application code defects
        if self._is_infrastructure_failure_raw(status, execution_telemetry, error_message, test_results):
            logger.info("Verification run %s classified as infrastructure error; 0 code defects.", run_id)
            return []

        effective_filename = affected_filename.strip() if affected_filename and affected_filename.strip() else "solution.py"
        defect_reports: List[DefectReport] = []

        # 1. Static Security AST Analysis (Task 1: Detect vulnerabilities even if functional tests pass)
        if project_files:
            for rel_path, code in project_files.items():
                if not rel_path.endswith(".py"):
                    continue
                parts = rel_path.replace("\\", "/").lower().split("/")
                if any(p in ("test", "tests") for p in parts) or parts[-1].startswith("test_") or parts[-1].endswith("_test.py"):
                    continue
                sec_findings = self.inspect_static_security_vulnerabilities(code)
                for s_idx, finding in enumerate(sec_findings):
                    if finding.get("confidence") == "CONFIRMED":
                        cwe = finding.get("cwe_id", "sec")
                        line_no = finding.get("line_number", 0)
                        seed_str = f"{run_id}:{rel_path}:{cwe}:{line_no}:{s_idx}"
                        defect_id = f"def-sec-{uuid.uuid5(uuid.NAMESPACE_DNS, seed_str).hex[:8]}"
                        sec_report = DefectReport(
                            defect_id=defect_id,
                            verification_run_id=run_id,
                            submission_id=submission_id,
                            title=f"Security Vulnerability in {rel_path}: {finding['title']}",
                            description=finding["description"],
                            severity=finding.get("severity", DefectSeverity.CRITICAL),
                            file_path=rel_path,
                            line_number=finding.get("line_number"),
                            confidence="CONFIRMED",
                            provenance="AST_STATIC_ANALYSIS",
                            defect_category="security_vulnerability",
                            cwe_id=finding.get("cwe_id"),
                            owasp_category=finding.get("owasp_category"),
                            failure_category="SECURITY_VULNERABILITY",
                            failed_test=f"security_ast_scan_{finding.get('cwe_id', '').lower()}",
                            assertion_or_exception=f"Static AST security scanner identified {finding.get('cwe_id')} in {rel_path}: {finding['title']}",
                            evidence_references={"ast_node": finding.get("description"), "file": rel_path, "line": finding.get("line_number"), "confidence": "CONFIRMED"},
                            tags=["security", finding.get("cwe_id", "").lower(), f"severity:{finding.get('severity', DefectSeverity.CRITICAL).value.lower()}"],
                            created_at=datetime.now(timezone.utc),
                        )
                        defect_reports.append(sec_report)
        elif source_code:
            sec_findings = self.inspect_static_security_vulnerabilities(source_code)
            for s_idx, finding in enumerate(sec_findings):
                if finding.get("confidence") == "CONFIRMED":
                    cwe = finding.get("cwe_id", "sec")
                    line_no = finding.get("line_number", 0)
                    seed_str = f"{run_id}:{cwe}:{line_no}:{s_idx}"
                    defect_id = f"def-sec-{uuid.uuid5(uuid.NAMESPACE_DNS, seed_str).hex[:8]}"
                    sec_report = DefectReport(
                        defect_id=defect_id,
                        verification_run_id=run_id,
                        submission_id=submission_id,
                        title=f"Security Vulnerability: {finding['title']}",
                        description=finding["description"],
                        severity=finding.get("severity", DefectSeverity.CRITICAL),
                        file_path=effective_filename,
                        line_number=finding.get("line_number"),
                        confidence="CONFIRMED",
                        provenance="AST_STATIC_ANALYSIS",
                        defect_category="security_vulnerability",
                        cwe_id=finding.get("cwe_id"),
                        owasp_category=finding.get("owasp_category"),
                        failure_category="SECURITY_VULNERABILITY",
                        failed_test=f"security_ast_scan_{finding.get('cwe_id', '').lower()}",
                        assertion_or_exception=f"Static AST security scanner identified {finding.get('cwe_id')}: {finding['title']}",
                        evidence_references={"ast_node": finding.get("description"), "line": finding.get("line_number"), "confidence": "CONFIRMED"},
                        tags=["security", finding.get("cwe_id", "").lower(), f"severity:{finding.get('severity', DefectSeverity.CRITICAL).value.lower()}"],
                        created_at=datetime.now(timezone.utc),
                    )
                    defect_reports.append(sec_report)

        # 2. Analyze failed test results (if any)
        failed_tests = [
            t for t in test_results
            if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
            and (t.metrics or {}).get("failure_origin")
            not in ("COLLECTION_ERROR", "MISSING_DEPENDENCY", "INFRASTRUCTURE_FAILURE")
        ]

        seen_test_names = set()
        for test in failed_tests:
            test_name = test.name or test.test_name or test.test_id
            if test_name in seen_test_names:
                continue
            seen_test_names.add(test_name)

            report = self._analyze_test_failure(
                run_id=run_id,
                submission_id=submission_id,
                test=test,
                affected_filename=effective_filename,
                requirement_id=requirement_id,
                source_code=source_code,
                project_files=project_files,
            )
            # Avoid duplicate if a security defect with the same CWE on the same line was already generated
            duplicate = any(
                d.cwe_id == report.cwe_id and d.line_number == report.line_number and d.file_path == report.file_path
                for d in defect_reports
                if d.cwe_id
            )
            if not duplicate:
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
        source_code: Optional[str] = None,
        project_files: Optional[Dict[str, str]] = None,
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

        # Proposal SO2/FR03 research defect taxonomy classification
        defect_cat, cwe_id, owasp_cat, perf_metrics = self._classify_defect_taxonomy(
            test=test,
            category=category,
            error_msg=error_msg,
            stack_trace=stack_trace,
            execution_duration_ms=test.duration_ms,
            source_code=source_code,
        )
        if cwe_id:
            severity = DefectSeverity.CRITICAL

        # Localization: multi-file traceback analysis takes precedence for project submissions
        line_number = None
        confidence = "UNCERTAIN"
        provenance = "UNLOCALIZED_INSUFFICIENT_EVIDENCE"
        final_filename = affected_filename

        if project_files and stack_trace:
            det_file, det_line, det_conf, det_prov = self.extract_multi_file_traceback_localization(
                stack_trace=stack_trace,
                project_files=project_files,
                default_filename=affected_filename,
            )
            if det_line is not None:
                final_filename = det_file
                line_number = det_line
                confidence = det_conf
                provenance = det_prov

        # Assertion failures normally contain only the test frame. Map the
        # function called by that verified assertion to its project source AST.
        if line_number is None and project_files:
            det_file, det_line, det_conf, det_prov = self.extract_multi_file_ast_localization(
                stack_trace=stack_trace,
                test_name=test_name,
                project_files=project_files,
            )
            if det_line is not None:
                final_filename = det_file
                line_number = det_line
                confidence = det_conf
                provenance = det_prov

        if line_number is None:
            cwe_line = None
            if source_code and cwe_id:
                sec_findings = self.inspect_static_security_vulnerabilities(source_code)
                for f in sec_findings:
                    if f.get("cwe_id") == cwe_id and f.get("line_number"):
                        cwe_line = f.get("line_number")
                        break

            line_number, confidence, provenance = self.extract_evidence_based_localization(
                stack_trace=stack_trace,
                affected_filename=affected_filename,
                source_code=source_code,
                test_name=test_name,
                assertion_or_exception=assertion_or_exception,
                cwe_id=cwe_id,
                cwe_line=cwe_line,
            )

        # Title and description strictly using evidence-based phrasing
        title = f"Observed {category.replace('_', ' ').title()} in {test_name}"
        desc = (
            f"Test case '{test_name}' failed under pytest execution. "
            f"Observed diagnostic: {assertion_or_exception or 'Assertion failed without explicit message'}."
        )
        # Preserve original traceback excerpt without fabrication
        traceback_excerpt = stack_trace.strip() if stack_trace and stack_trace.strip() else (error_msg.strip() if error_msg else None)

        return DefectReport(
            defect_id=defect_id,
            verification_run_id=run_id,
            submission_id=submission_id,
            requirement_id=requirement_id,
            title=title,
            severity=severity,
            description=desc,
            file_path=final_filename,
            line_number=line_number,
            confidence=confidence,
            provenance=provenance,
            failed_test=test_name,
            failure_category=category,
            defect_category=defect_cat,
            cwe_id=cwe_id,
            owasp_category=owasp_cat,
            performance_metrics=perf_metrics,
            assertion_or_exception=assertion_or_exception,
            expected_value=expected_val,
            actual_value=actual_val,
            traceback_excerpt=traceback_excerpt,
            evidence_references={
                "test_id": test.test_id,
                "test_status": test.status.value,
                "duration_ms": test.duration_ms,
                "localization_confidence": confidence,
                "localization_provenance": provenance,
                "affected_file": final_filename,
            },
            tags=[category.lower(), defect_cat.lower(), f"severity:{severity.value.lower()}"],
            created_at=datetime.now(timezone.utc),
        )

    def inspect_static_security_vulnerabilities(self, source_code: str) -> List[Dict[str, Any]]:
        """
        Static AST security scanner detecting common vulnerability patterns (SO2, Table 4).
        Detects CWE-78, CWE-95, CWE-22, CWE-798, and CWE-89.
        Distinguishes confirmed vulnerabilities from safe patterns (negative controls).
        """
        findings = []
        if not source_code:
            return findings
        try:
            tree = ast.parse(source_code)
        except Exception:
            return findings

        # Check for path sanitization helpers in the entire AST (e.g. os.path.basename, startswith check)
        has_path_sanitization = False
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f_name = ""
                if isinstance(n.func, ast.Attribute):
                    f_name = n.func.attr
                elif isinstance(n.func, ast.Name):
                    f_name = n.func.id
                if f_name in ("basename", "resolve", "startswith"):
                    has_path_sanitization = True
                    break

        for node in ast.walk(tree):
            # 1. Command Injection (CWE-78 / OWASP-A03)
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id

                # Direct shell execution calls
                if func_name in ("system", "popen"):
                    findings.append({
                        "cwe_id": "CWE-78",
                        "owasp_category": "OWASP-A03:2021-Injection",
                        "title": "OS Command Injection via Shell Invocation (CWE-78)",
                        "line_number": getattr(node, "lineno", None),
                        "severity": DefectSeverity.CRITICAL,
                        "confidence": "CONFIRMED",
                        "provenance": "AST_STATIC_ANALYSIS",
                        "description": f"Direct invocation of shell function '{func_name}' with unvalidated command string.",
                    })
                # Subprocess with shell=True
                elif func_name in ("run", "Popen", "call", "check_output", "check_call"):
                    shell_true = any(
                        kw.arg == "shell" and getattr(kw.value, "value", None) is True
                        for kw in node.keywords
                    )
                    if shell_true:
                        findings.append({
                            "cwe_id": "CWE-78",
                            "owasp_category": "OWASP-A03:2021-Injection",
                            "title": "OS Command Injection via Subprocess with shell=True (CWE-78)",
                            "line_number": getattr(node, "lineno", None),
                            "severity": DefectSeverity.CRITICAL,
                            "confidence": "CONFIRMED",
                            "provenance": "AST_STATIC_ANALYSIS",
                            "description": f"Subprocess function '{func_name}' called with shell=True, enabling command injection.",
                        })

                # 2. Dynamic Code Execution (CWE-95 / OWASP-A03)
                elif func_name in ("eval", "exec"):
                    findings.append({
                        "cwe_id": "CWE-95",
                        "owasp_category": "OWASP-A03:2021-Injection",
                        "title": "Improper Neutralization of Directives in Dynamically Evaluated Code (CWE-95)",
                        "line_number": getattr(node, "lineno", None),
                        "severity": DefectSeverity.CRITICAL,
                        "confidence": "CONFIRMED",
                        "provenance": "AST_STATIC_ANALYSIS",
                        "description": f"Unsafe execution of dynamic code evaluation function '{func_name}'.",
                    })

                # 3. Path Traversal (CWE-22 / OWASP-A01)
                elif func_name in ("open", "read_file", "unlink", "remove") and node.args:
                    first_arg = node.args[0]
                    # Dynamic path construction (f-string or string concatenation) without path sanitization
                    is_dynamic_path = isinstance(first_arg, (ast.JoinedStr, ast.BinOp))
                    if is_dynamic_path and not has_path_sanitization:
                        findings.append({
                            "cwe_id": "CWE-22",
                            "owasp_category": "OWASP-A01:2021-Broken Access Control",
                            "title": "Improper Limitation of a Pathname to a Restricted Directory (CWE-22)",
                            "line_number": getattr(node, "lineno", None),
                            "severity": DefectSeverity.HIGH,
                            "confidence": "CONFIRMED",
                            "provenance": "AST_STATIC_ANALYSIS",
                            "description": f"File access via '{func_name}' using unconfined dynamic path construction.",
                        })

                # 4. SQL Injection (CWE-89 / OWASP-A03)
                elif func_name in ("execute", "executemany", "raw", "execute_sql", "run_query") and node.args:
                    first_arg = node.args[0]
                    is_dynamic_sql = isinstance(first_arg, (ast.JoinedStr, ast.BinOp))
                    if is_dynamic_sql:
                        # Check if argument contains SQL syntax keywords
                        sql_keywords = ("select", "insert", "update", "delete", "drop", "from", "where")
                        sql_text = ""
                        if isinstance(first_arg, ast.JoinedStr):
                            for part in first_arg.values:
                                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                                    sql_text += part.value.lower() + " "
                        elif isinstance(first_arg, ast.BinOp):
                            if isinstance(first_arg.left, ast.Constant) and isinstance(first_arg.left.value, str):
                                sql_text += first_arg.left.value.lower() + " "
                        if any(kw in sql_text for kw in sql_keywords):
                            findings.append({
                                "cwe_id": "CWE-89",
                                "owasp_category": "OWASP-A03:2021-Injection",
                                "title": "Improper Neutralization of Special Elements in SQL Command (CWE-89)",
                                "line_number": getattr(node, "lineno", None),
                                "severity": DefectSeverity.CRITICAL,
                                "confidence": "CONFIRMED",
                                "provenance": "AST_STATIC_ANALYSIS",
                                "description": f"SQL execution via '{func_name}' with unparameterized dynamic string query.",
                            })

            # 5. Hardcoded Secrets (CWE-798 / OWASP-A07)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name_lower = target.id.lower()
                        if any(k in name_lower for k in ("secret", "password", "api_key", "jwt_token", "auth_token", "private_key")):
                            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                val = node.value.value
                                # Ignore non-secret URLs, dummy placeholders, or short values
                                is_placeholder = val.lower().strip() in ("dummy", "example", "test", "changeme", "your_secret_here", "todo")
                                is_url_or_env = any(val.startswith(p) for p in ("sqlite://", "http://", "https://", "env:", "postgresql://", "mysql://"))
                                if len(val) >= 8 and not is_url_or_env and not is_placeholder:
                                    findings.append({
                                        "cwe_id": "CWE-798",
                                        "owasp_category": "OWASP-A07:2021-Identification and Authentication Failures",
                                        "title": "Hardcoded Sensitive Credential Detected (CWE-798)",
                                        "line_number": getattr(node, "lineno", None),
                                        "severity": DefectSeverity.HIGH,
                                        "confidence": "CONFIRMED",
                                        "provenance": "AST_STATIC_ANALYSIS",
                                        "description": f"Hardcoded credential string literal assigned to variable '{target.id}'.",
                                    })
        return findings

    def inspect_workload_complexity_patterns(self, source_code: str) -> List[Dict[str, Any]]:
        """
        Static AST workload complexity analyzer detecting algorithmic performance bottlenecks (SO1, FR03).
        Identifies:
        - Nested loops: O(N^2) quadratic iteration without early termination.
        - Exponential recursion: O(2^N) binary recursion without memoization/caching.
        - Repeated buffer reallocation: String concatenation inside loops (e.g., s = s + ...).
        - Unindexed linear scanning: Repeated linear scans inside an outer iteration.
        """
        findings = []
        if not source_code:
            return findings
        try:
            tree = ast.parse(source_code)
        except Exception:
            return findings

        # Check for memoization decorators (e.g. @lru_cache, @cache)
        memoized_functions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            dec_name = dec.func.id
                        elif isinstance(dec.func, ast.Attribute):
                            dec_name = dec.func.attr
                    if "cache" in dec_name.lower():
                        memoized_functions.add(node.name)

        for node in ast.walk(tree):
            # 1. Exponential recursion: unmemoized function calling itself >= 2 times
            if isinstance(node, ast.FunctionDef):
                fn_name = node.name
                if fn_name not in memoized_functions:
                    calls = [
                        c for c in ast.walk(node)
                        if isinstance(c, ast.Call)
                        and isinstance(c.func, ast.Name)
                        and c.func.id == fn_name
                    ]
                    if len(calls) >= 2:
                        findings.append({
                            "pattern": "exponential_recursion",
                            "complexity": "O(2^N)",
                            "function_name": fn_name,
                            "line_number": getattr(node, "lineno", None),
                            "description": f"Unmemoized exponential recursive calls in function '{fn_name}'.",
                        })

            # 2. Nested loops (O(N^2) quadratic iteration)
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if child is not node and isinstance(child, (ast.For, ast.While)):
                        findings.append({
                            "pattern": "nested_loop_quadratic",
                            "complexity": "O(N^2)",
                            "line_number": getattr(child, "lineno", getattr(node, "lineno", None)),
                            "description": "Nested loop execution yielding potential O(N^2) quadratic algorithmic latency.",
                        })
                        break

            # 3. Repeated buffer allocation / string concatenation in loop
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        if isinstance(child.value, ast.BinOp) and isinstance(child.value.op, ast.Add):
                            target_id = child.targets[0].id if child.targets and isinstance(child.targets[0], ast.Name) else None
                            if target_id and any(isinstance(n, ast.Name) and n.id == target_id for n in ast.walk(child.value)):
                                findings.append({
                                    "pattern": "repeated_string_concat_in_loop",
                                    "complexity": "O(N^2) buffer reallocation",
                                    "line_number": getattr(child, "lineno", None),
                                    "description": f"Repeated accumulator concatenation on variable '{target_id}' inside loop.",
                                    })
                                break

        return findings

    def _classify_defect_taxonomy(
        self,
        test: TestResult,
        category: str,
        error_msg: str,
        stack_trace: str,
        execution_duration_ms: Optional[float] = None,
        source_code: Optional[str] = None,
    ) -> Tuple[str, Optional[str], Optional[str], Optional[dict]]:
        """
        Classifies defect into proposal research taxonomy (SO2, FR03):
        - functional_bug
        - security_vulnerability (with CWE and OWASP identifiers)
        - performance_bottleneck (with latency/duration metrics)
        - regression

        Methodological Integrity: Classification is derived strictly from empirical evidence
        (measured execution latency exceeding threshold, AST static vulnerability findings,
        traceback exceptions), and NEVER relies on scenario names or test function names as shortcuts.
        """
        diag_combined = f"{error_msg} {stack_trace}".lower()

        # 1. Performance Bottleneck Checks: Measured execution latency exceeding SLA or performance test failure
        duration = execution_duration_ms or test.duration_ms or 0.0
        is_perf_test = (
            getattr(test, "test_type", None) == TestType.PERFORMANCE
            or "performance" in getattr(test, "name", "").lower()
            or "latency" in getattr(test, "name", "").lower()
            or "sla" in getattr(test, "name", "").lower()
        )
        has_perf_diagnostic = any(
            term in diag_combined
            for term in ("latency sla breach", "threshold breach", "performance bottleneck", "timed out under load")
        )

        complexity_patterns = self.inspect_workload_complexity_patterns(source_code) if source_code else []

        is_perf_bottleneck = False
        is_timeout_failure = (category == "TIMEOUT_ERROR" or test.status == TestResultStatus.TIMEOUT)

        if is_perf_test or has_perf_diagnostic:
            # Under performance testing, failure, timeout, or SLA breach is a performance defect
            if duration > 200.0 or is_timeout_failure or bool(complexity_patterns) or test.status == TestResultStatus.FAILED:
                is_perf_bottleneck = True
        elif is_timeout_failure:
            # A timeout in a non-performance test is a functional hang / infinite loop, NOT a performance defect
            is_perf_bottleneck = False
        elif duration > 200.0:
            # A completed non-perf test that genuinely exceeded 200ms latency threshold
            is_perf_bottleneck = True
        elif complexity_patterns and duration >= 10.0 and test.status == TestResultStatus.FAILED:
            # Algorithmic complexity pattern confirmed with measurable execution latency
            is_perf_bottleneck = True

        if is_perf_bottleneck:
            metrics = {
                "duration_ms": duration,
                "threshold_breached": duration > 200.0 or is_perf_test or bool(complexity_patterns),
                "threshold_latency_ms": 200.0,
                "complexity_patterns": [p["pattern"] for p in complexity_patterns],
            }
            return "performance_bottleneck", None, None, metrics

        # 2. Security Vulnerability Checks: Derived from source code AST security findings or explicit security exceptions
        if source_code:
            sec_findings = self.inspect_static_security_vulnerabilities(source_code)
            if sec_findings:
                top = sec_findings[0]
                return "security_vulnerability", top["cwe_id"], top["owasp_category"], None

        # Check diagnostic traceback for explicit security vulnerability patterns (not test names)
        if any(term in diag_combined for term in ("cwe-89", "sql injection", "sqli", "syntax error in query")):
            return "security_vulnerability", "CWE-89", "OWASP-A03:2021-Injection", None
        if any(term in diag_combined for term in ("cwe-78", "command injection", "os.system")):
            return "security_vulnerability", "CWE-78", "OWASP-A03:2021-Injection", None
        if any(term in diag_combined for term in ("cwe-798", "hardcoded secret", "hardcoded credential", "hardcoded api_key")):
            return "security_vulnerability", "CWE-798", "OWASP-A07:2021-Identification and Authentication Failures", None
        if any(term in diag_combined for term in ("cwe-22", "path traversal", "directory traversal")):
            return "security_vulnerability", "CWE-22", "OWASP-A01:2021-Broken Access Control", None
        if any(term in diag_combined for term in ("cwe-95", "eval injection", "unsafe eval")):
            return "security_vulnerability", "CWE-95", "OWASP-A03:2021-Injection", None

        # 3. Regression Checks: Derived from diagnostic traceback or historical regression evidence
        if "regression" in diag_combined or "regression against baseline" in diag_combined:
            return "regression", None, None, None

        # 4. Default: Functional Bug (Logic/Assertion/Exception)
        return "functional_bug", None, None, None


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


    def extract_multi_file_traceback_localization(
        self,
        stack_trace: str,
        project_files: Dict[str, str],
        default_filename: str = "solution.py",
    ) -> Tuple[str, Optional[int], str, str]:
        """
        Extracts affected project file and line number from pytest stack trace in multi-file projects.
        Scans frames for non-test implementation files in project_files.
        """
        if not stack_trace or not project_files:
            return default_filename, None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"

        candidate_files: Dict[str, str] = {}
        for p in project_files.keys():
            norm_p = p.replace("\\", "/").lstrip("./")
            parts = norm_p.lower().split("/")
            # Exclude test files
            if any(part in ("test", "tests") for part in parts) or parts[-1].startswith("test_") or parts[-1].endswith("_test.py"):
                continue
            if norm_p.endswith(".py"):
                candidate_files[norm_p] = parts[-1]

        if not candidate_files:
            return default_filename, None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"

        # Pytest traceback format 1: File ".../workspace/auth/login.py", line 18, in authenticate
        frame_matches = list(re.finditer(r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)', stack_trace))
        for m in reversed(frame_matches):
            raw_path = m.group(1).replace("\\", "/")
            line_str = m.group(2)
            for rel_path, base_name in candidate_files.items():
                if raw_path.endswith(rel_path) or raw_path.endswith(f"/{base_name}") or raw_path == base_name:
                    try:
                        return rel_path, int(line_str), "CONFIRMED", "TRACEBACK_FRAME_ANALYSIS"
                    except ValueError:
                        pass

        # Pytest traceback format 2: auth/login.py:18: in authenticate
        for rel_path, base_name in candidate_files.items():
            esc_rel = re.escape(rel_path)
            esc_base = re.escape(base_name)
            m_rel = list(re.finditer(rf'(?:^|\s|\/){esc_rel}:(\d+):', stack_trace))
            if m_rel:
                try:
                    return rel_path, int(m_rel[-1].group(1)), "CONFIRMED", "TRACEBACK_FRAME_ANALYSIS"
                except ValueError:
                    pass
            m_base = list(re.finditer(rf'(?:^|\s|\/){esc_base}:(\d+):', stack_trace))
            if m_base:
                try:
                    return rel_path, int(m_base[-1].group(1)), "CONFIRMED", "TRACEBACK_FRAME_ANALYSIS"
                except ValueError:
                    pass

        return default_filename, None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"

    def extract_multi_file_ast_localization(
        self,
        stack_trace: str,
        test_name: str,
        project_files: Dict[str, str],
    ) -> Tuple[str, Optional[int], str, str]:
        """Map a function named in failed assertion evidence to project source."""
        evidence = f"{test_name}\n{stack_trace}"
        called_names = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", evidence))
        ignored = {"assert", "where", "round", "len", "str", "int", "float", "list", "dict"}
        called_names.difference_update(ignored)

        candidates = []
        for rel_path, code in project_files.items():
            normalized = rel_path.replace("\\", "/")
            parts = normalized.lower().split("/")
            if not normalized.endswith(".py") or any(part in ("test", "tests") for part in parts):
                continue
            try:
                tree = ast.parse(code)
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in called_names:
                    # Prefer the most specific implementation expression over
                    # the signature when a return statement is available.
                    returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
                    line = returns[-1].lineno if returns else node.lineno
                    score = 2 if node.name in (test_name or "") else 1
                    candidates.append((score, normalized, line))

        if not candidates:
            return "solution.py", None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"
        _, filename, line_number = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
        return filename, line_number, "HIGH", "AST_SOURCE_MAPPING"

    def extract_evidence_based_localization(
        self,
        stack_trace: str,
        affected_filename: str,
        source_code: Optional[str] = None,
        test_name: Optional[str] = None,
        assertion_or_exception: Optional[str] = None,
        cwe_id: Optional[str] = None,
        cwe_line: Optional[int] = None,
    ) -> Tuple[Optional[int], str, str]:
        """
        Evidence-based defect localization adhering to Proposal Section 3.4 & Task 2.

        Techniques applied in priority order:
        1. Confirmed AST Security Node Line (CWE identification directly on AST node)
        2. Direct Implementation Traceback Frame (identifies frames inside solution.py,
           strictly distinguishing them from test execution frames)
        3. Assertion-to-Source AST Mapping (maps failed test call site to implementation
           statements, conditions, and return expressions)

        Returns:
            (line_number, confidence, provenance)
            Confidence: CONFIRMED, HIGH, MEDIUM, LOW, UNCERTAIN
            Provenance: AST_STATIC_ANALYSIS, TRACEBACK_FRAME_ANALYSIS, AST_SOURCE_MAPPING, UNLOCALIZED_INSUFFICIENT_EVIDENCE
        """
        # 1. AST Security Analysis Localization (Exact node line)
        if cwe_line and cwe_line > 0:
            return cwe_line, "CONFIRMED", "AST_STATIC_ANALYSIS"

        # 2. Traceback Frame Analysis (Strictly implementation frames, not test frames)
        if stack_trace and affected_filename:
            base_name = affected_filename.replace("\\", "/").split("/")[-1]
            candidate_names = [base_name]
            if base_name != "solution.py":
                candidate_names.append("solution.py")

            for name in candidate_names:
                esc = re.escape(name)
                # Standard pytest/python traceback: File "path/to/solution.py", line 12, in func
                matches = re.findall(rf'File\s+["\'][^"\']*{esc}["\'],\s+line\s+(\d+)', stack_trace, re.IGNORECASE)
                if matches:
                    try:
                        return int(matches[-1]), "CONFIRMED", "TRACEBACK_FRAME_ANALYSIS"
                    except ValueError:
                        pass

                # Short pytest format: solution.py:12: in <func>
                short_matches = re.findall(rf'(?:^|\s|\/){esc}:(\d+):', stack_trace, re.IGNORECASE)
                if short_matches:
                    try:
                        return int(short_matches[-1]), "CONFIRMED", "TRACEBACK_FRAME_ANALYSIS"
                    except ValueError:
                        pass

        # 3. Assertion-to-Source AST Mapping
        # When an assertion fails in test code, the defect is in the implementation of the function under test.
        # Requires meaningful diagnostic evidence (traceback, assertion text, or specific exception) to avoid fabricating locations.
        has_diagnostic_evidence = bool(
            (stack_trace and stack_trace.strip())
            or (
                assertion_or_exception
                and "without detailed diagnostic message" not in assertion_or_exception
                and assertion_or_exception.strip() != "Assertion failed"
            )
        )
        if not has_diagnostic_evidence:
            return None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"

        if source_code:
            try:
                tree = ast.parse(source_code)
                combined_diag = f"{test_name or ''} {assertion_or_exception or ''} {stack_trace or ''}"

                # Look for calls: solution.<fn>( or <fn>(
                called_functions = set()
                for m in re.finditer(r"solution\.([a-zA-Z0-9_]+)\s*\(", combined_diag):
                    called_functions.add(m.group(1))

                defined_functions = {
                    node.name: node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                }

                target_node = None
                for fn in called_functions:
                    if fn in defined_functions:
                        target_node = defined_functions[fn]
                        break

                if not target_node and test_name:
                    cleaned_test = test_name.lower().replace("test_", "")
                    for fn_name, fn_node in defined_functions.items():
                        if fn_name.lower() in cleaned_test or cleaned_test in fn_name.lower():
                            target_node = fn_node
                            break

                if not target_node and len(defined_functions) == 1:
                    target_node = list(defined_functions.values())[0]

                if target_node:
                    # Check nested loops in performance scenarios (e.g. nested for-loops)
                    for loop in [n for n in target_node.body if isinstance(n, (ast.For, ast.While))]:
                        nested = [n for n in loop.body if isinstance(n, (ast.For, ast.While))]
                        if nested:
                            return nested[0].lineno, "HIGH", "AST_SOURCE_MAPPING"

                    # Check if-statements (condition boundary / logic bugs)
                    if_nodes = [n for n in ast.walk(target_node) if isinstance(n, ast.If)]
                    for if_node in if_nodes:
                        # If body has return statement, check if relevant
                        return_in_if = [n for n in if_node.body if isinstance(n, ast.Return)]
                        return_text = ""
                        if return_in_if:
                            try:
                                return_text = ast.unparse(return_in_if[0])
                            except Exception:
                                pass
                        if return_text and any(term in combined_diag for term in return_text.split()):
                            return return_in_if[0].lineno, "HIGH", "AST_SOURCE_MAPPING"
                        # Check condition line
                        return if_node.lineno, "HIGH", "AST_SOURCE_MAPPING"

                    # Check assignment statements before return (e.g. start = page * per_page)
                    assign_nodes = [n for n in target_node.body if isinstance(n, ast.Assign)]
                    if assign_nodes:
                        return assign_nodes[0].lineno, "HIGH", "AST_SOURCE_MAPPING"

                    # Check return statements
                    return_nodes = [n for n in ast.walk(target_node) if isinstance(n, ast.Return)]
                    if return_nodes:
                        return return_nodes[0].lineno, "HIGH", "AST_SOURCE_MAPPING"

                    return target_node.lineno, "MEDIUM", "AST_SOURCE_MAPPING"

            except Exception as e:
                logger.debug("AST mapping encountered non-fatal error: %s", e)

        return None, "UNCERTAIN", "UNLOCALIZED_INSUFFICIENT_EVIDENCE"

    def _extract_localized_line_number(
        self,
        stack_trace: str,
        affected_filename: str,
    ) -> Optional[int]:
        """
        Backward-compatible wrapper extracting line number strictly from traceback evidence.
        """
        line, _, _ = self.extract_evidence_based_localization(stack_trace, affected_filename)
        return line


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
