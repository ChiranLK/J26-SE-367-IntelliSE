import ast
import asyncio
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import logger
from app.schemas.common import TestResultStatus, TestType, VerificationStatus
from app.schemas.test_result import TestResult


@dataclass
class SandboxExecutionResult:
    """Raw execution result from the Docker test runner sandbox."""

    status: str  # PASSED, FAILED, SKIPPED, ERROR, TIMEOUT
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None
    test_results: List[TestResult] = field(default_factory=list)
    is_timeout: bool = False
    no_oracle: bool = False
    telemetry: Dict[str, Any] = field(default_factory=dict)


class DockerTestRunner:
    """
    Isolated Docker-based test runner for Component 4.

    ARCHITECTURAL & SECURITY CONSTRAINTS:
    - Never executes untrusted submitted code on the host.
    - All tests run in short-lived, unprivileged containers.
    - Container constraints:
        * --network none (Zero network access)
        * --user 1000:1000 (Non-root user sandbox)
        * --read-only (Read-only root filesystem)
        * --tmpfs /tmp:rw,noexec,nosuid,size=64m (Bounded ephemeral scratch storage)
        * --cpus, --memory, --pids-limit resource boundaries
        * --cap-drop ALL, --security-opt no-new-privileges:true
        * Strict timeout with guaranteed container termination and cleanup
    - Host mounts are restricted strictly to a dedicated, ephemeral temp workspace mounted :ro.
    - No Docker socket or sensitive host paths mounted.
    - Fail-closed: If Docker is unavailable, returns ERROR. Never falls back to host execution.
    - Never treats submitted code's internal tests as trusted test oracles.
    - Clearly distinguishes PASSED, FAILED, SKIPPED, ERROR, and TIMEOUT outcomes.
    """

    def __init__(
        self,
        image_name: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.image_name = image_name or settings.DOCKER_RUNNER_IMAGE
        self.timeout_seconds = timeout_seconds or settings.DOCKER_TIMEOUT_SECONDS

    @staticmethod
    def _resolve_project_layout(project_files: Dict[str, str]) -> Tuple[str, List[str]]:
        """Return the effective ZIP project root and its import search paths.

        ZIP producers commonly wrap a project in one directory.  Mounting the
        extraction directory at ``/workspace`` does not make packages below that
        wrapper importable, so pytest collection used to fail before any test ran.
        The returned paths are container paths and never escape ``/workspace``.
        """
        normalized = [
            posixpath.normpath(path.replace("\\", "/")).lstrip("/")
            for path in project_files
            if path and posixpath.normpath(path.replace("\\", "/")) not in (".", "")
        ]
        top_levels = {path.split("/", 1)[0] for path in normalized}
        has_root_file = any("/" not in path for path in normalized)
        wrapper = next(iter(top_levels)) if len(top_levels) == 1 and not has_root_file else ""
        project_root = f"/workspace/{wrapper}" if wrapper else "/workspace"

        import_paths = [project_root]
        relative_paths = [
            path[len(wrapper) + 1 :] if wrapper and path.startswith(f"{wrapper}/") else path
            for path in normalized
        ]
        if any(path.startswith("src/") for path in relative_paths):
            import_paths.append(f"{project_root}/src")
        return project_root, import_paths

    @staticmethod
    def _embedded_test_paths(project_files: Dict[str, str]) -> List[str]:
        paths: List[str] = []
        for path in project_files:
            normalized = path.replace("\\", "/")
            basename = posixpath.basename(normalized)
            if normalized.endswith(".py") and (
                basename.startswith("test_")
                or basename.endswith("_test.py")
                or "/tests/" in f"/{normalized}"
            ):
                paths.append(normalized)
        return sorted(paths)

    def check_docker_available(self) -> Tuple[bool, str]:
        """
        Verifies that Docker engine is installed, running, and accessible.
        Fails closed if Docker is not operational.
        """
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                return True, "Docker daemon available"
            return False, f"Docker daemon unavailable (exit {res.returncode}): {res.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return False, "Docker availability check timed out"
        except FileNotFoundError:
            return False, "Docker CLI command not found in system PATH"
        except Exception as e:
            return False, f"Docker check error: {str(e)}"

    def ensure_runner_image(self) -> Tuple[bool, str]:
        """
        Ensures the dedicated runner image exists locally.
        If missing, attempts to build it from Dockerfile.python-runner.
        """
        try:
            inspect_res = subprocess.run(
                ["docker", "image", "inspect", self.image_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if inspect_res.returncode == 0:
                return True, f"Image {self.image_name} ready"

            # Image not found, attempt to build
            logger.info("Runner image %s not found. Building from Dockerfile...", self.image_name)
            dockerfile_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "docker",
                    "Dockerfile.python-runner",
                )
            )
            docker_context = os.path.dirname(dockerfile_path)

            if not os.path.isfile(dockerfile_path):
                return False, f"Dockerfile for runner not found at {dockerfile_path}"

            build_res = subprocess.run(
                ["docker", "build", "-t", self.image_name, "-f", dockerfile_path, docker_context],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if build_res.returncode == 0:
                logger.info("Successfully built runner image %s", self.image_name)
                return True, f"Image {self.image_name} built successfully"
            return False, f"Failed to build runner image: {build_res.stderr.strip()[:300]}"
        except Exception as e:
            return False, f"Error verifying runner image: {str(e)}"

    async def execute_verification(
        self,
        source_code: str,
        trusted_test_cases: Optional[str] = None,
        filename: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        project_files: Optional[Dict[str, str]] = None,
    ) -> SandboxExecutionResult:
        """
        Orchestrates safe syntax validation and containerized execution of trusted test cases.
        Supports both single-file modules and multi-file projects with relative directory structures.
        """
        effective_timeout = timeout_seconds or self.timeout_seconds
        start_time = time.perf_counter()

        # Step 1: Host-side static AST parsing (syntax safety check)
        if project_files:
            for p_path, p_code in project_files.items():
                if p_path.endswith(".py"):
                    try:
                        ast.parse(p_code)
                    except SyntaxError as syn_err:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        error_msg = f"SyntaxError in {p_path} (line {syn_err.lineno}): {syn_err.msg}"
                        logger.warning("Project file %s failed static AST parsing: line %s, %s", p_path, syn_err.lineno, syn_err.msg)
                        return SandboxExecutionResult(
                            status=TestResultStatus.ERROR.value,
                            duration_ms=duration_ms,
                            error_message=error_msg,
                            test_results=[
                                TestResult(
                                    test_id="ast_syntax_check",
                                    name=f"Python AST Syntax Validation ({p_path})",
                                    test_type=TestType.UNIT,
                                    status=TestResultStatus.ERROR,
                                    duration_ms=duration_ms,
                                    error_message=error_msg,
                                )
                            ],
                            telemetry={"syntax_valid": False, "error_type": "SyntaxError", "affected_file": p_path},
                        )
        else:
            try:
                ast.parse(source_code)
            except SyntaxError as syn_err:
                duration_ms = (time.perf_counter() - start_time) * 1000
                error_msg = f"SyntaxError in submitted source code (line {syn_err.lineno}): {syn_err.msg}"
                logger.warning("Submitted code failed static AST parsing: line %s, %s", syn_err.lineno, syn_err.msg)
                return SandboxExecutionResult(
                    status=TestResultStatus.ERROR.value,
                    duration_ms=duration_ms,
                    error_message=error_msg,
                    test_results=[
                        TestResult(
                            test_id="ast_syntax_check",
                            name="Python AST Syntax Validation",
                            test_type=TestType.UNIT,
                            status=TestResultStatus.ERROR,
                            duration_ms=duration_ms,
                            error_message=error_msg,
                        )
                    ],
                    telemetry={"syntax_valid": False, "error_type": "SyntaxError"},
                )

        # Step 2: Test Oracle Check
        cleaned_test_code = (trusted_test_cases or "").strip()
        has_project_tests = False
        if project_files:
            has_project_tests = any(
                f.endswith(".py") and (os.path.basename(f).startswith("test_") or "/tests/" in f"/{f}" or "/test/" in f"/{f}")
                for f in project_files.keys()
            )

        if not cleaned_test_code and not has_project_tests:
            duration_ms = (time.perf_counter() - start_time) * 1000
            msg = (
                "No authorized test oracle or test suite provided. "
                "Syntax check succeeded, but functional correctness cannot be verified without a trusted test oracle."
            )
            logger.info("Verification run invoked without trusted test cases; skipping execution.")
            return SandboxExecutionResult(
                status=TestResultStatus.SKIPPED.value,
                duration_ms=duration_ms,
                error_message=None,
                no_oracle=True,
                test_results=[
                    TestResult(
                        test_id="ast_syntax_check",
                        name="Python AST Syntax Validation",
                        test_type=TestType.UNIT,
                        status=TestResultStatus.PASSED,
                        duration_ms=duration_ms,
                        error_message=None,
                    )
                ],
                telemetry={
                    "syntax_valid": True,
                    "has_test_oracle": False,
                    "notice": msg,
                },
            )

        # Check explicit test code syntax if supplied
        if cleaned_test_code:
            try:
                ast.parse(cleaned_test_code)
            except SyntaxError as test_syn_err:
                duration_ms = (time.perf_counter() - start_time) * 1000
                error_msg = f"SyntaxError in authorized test specification (line {test_syn_err.lineno}): {test_syn_err.msg}"
                logger.warning("Trusted test code failed AST parsing: line %s, %s", test_syn_err.lineno, test_syn_err.msg)
                return SandboxExecutionResult(
                    status=TestResultStatus.ERROR.value,
                    duration_ms=duration_ms,
                    error_message=error_msg,
                    test_results=[
                        TestResult(
                            test_id="test_suite_syntax_check",
                            name="Trusted Test Suite Syntax Check",
                            test_type=TestType.UNIT,
                            status=TestResultStatus.ERROR,
                            duration_ms=duration_ms,
                            error_message=error_msg,
                        )
                    ],
                    telemetry={"test_syntax_valid": False, "error_type": "TestSyntaxError"},
                )

        # Step 3: Docker availability and image readiness (Fail-closed)
        docker_ok, docker_msg = self.check_docker_available()
        if not docker_ok:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Fail-closed: Docker unavailable for sandbox execution: %s", docker_msg)
            return SandboxExecutionResult(
                status=TestResultStatus.ERROR.value,
                duration_ms=duration_ms,
                error_message=f"Infrastructure isolation failure: {docker_msg}",
                test_results=[],
                telemetry={"docker_available": False, "error": docker_msg},
            )

        image_ok, image_msg = self.ensure_runner_image()
        if not image_ok:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Fail-closed: Runner image unavailable: %s", image_msg)
            return SandboxExecutionResult(
                status=TestResultStatus.ERROR.value,
                duration_ms=duration_ms,
                error_message=f"Sandbox image failure: {image_msg}",
                test_results=[],
                telemetry={"image_ready": False, "error": image_msg},
            )

        # Step 4: Prepare isolated ephemeral workspace directory
        temp_dir = tempfile.mkdtemp(prefix="intelise_sandbox_")
        container_id = f"intelise_run_{uuid.uuid4().hex[:12]}"

        try:
            # Write project files or single solution file
            if project_files:
                for rel_path, file_content in project_files.items():
                    target_file = os.path.join(temp_dir, rel_path.replace("/", os.sep))
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(file_content)

                project_root, python_paths = self._resolve_project_layout(project_files)
                embedded_tests = self._embedded_test_paths(project_files)
                matching_embedded_tests = [
                    path for path in embedded_tests
                    if project_files[path].strip() == cleaned_test_code
                ]

                # Prefer the submitted test files at their genuine paths.  Upload
                # ingestion stores the primary embedded suite in test_code too;
                # copying it to /workspace/test_verification.py loses ZIP-root
                # import semantics and duplicates project tests.
                if matching_embedded_tests:
                    test_target = " ".join(
                        shlex.quote(f"/{posixpath.join('workspace', path)}") for path in embedded_tests
                    )
                elif cleaned_test_code:
                    relative_root = project_root.removeprefix("/workspace/")
                    host_root = os.path.join(temp_dir, relative_root.replace("/", os.sep)) if relative_root else temp_dir
                    test_file_path = os.path.join(host_root, "test_verification.py")
                    with open(test_file_path, "w", encoding="utf-8") as f:
                        f.write(cleaned_test_code)
                    test_target = shlex.quote(f"{project_root}/test_verification.py")
                else:
                    test_target = " ".join(
                        shlex.quote(f"/{posixpath.join('workspace', path)}") for path in embedded_tests
                    ) or shlex.quote(project_root)
            else:
                solution_filename = "solution.py"
                if filename and filename.endswith(".py") and not filename.startswith("test_") and filename != "conftest.py":
                    clean_name = os.path.basename(filename)
                    with open(os.path.join(temp_dir, clean_name), "w", encoding="utf-8") as f:
                        f.write(source_code)

                # Always write solution.py as standard entry module
                with open(os.path.join(temp_dir, solution_filename), "w", encoding="utf-8") as f:
                    f.write(source_code)

                # Write trusted test suite
                test_filename = "test_verification.py"
                with open(os.path.join(temp_dir, test_filename), "w", encoding="utf-8") as f:
                    f.write(cleaned_test_code)

                test_target = shlex.quote(f"/workspace/{test_filename}")
                project_root = "/workspace"
                python_paths = [project_root]

                # Write neutral pytest.ini to avoid root or environmental interference
                with open(os.path.join(temp_dir, "pytest.ini"), "w", encoding="utf-8") as f:
                    f.write("[pytest]\npython_files = test_*.py\naddopts = -s\n")

            # Step 5: Execute containerized pytest with strict containment
            xml_report_marker = "__INTELISE_XML_REPORT_START__"
            docker_cmd = [
                "docker",
                "run",
                "--name",
                container_id,
                "--network",
                "none",
                "--user",
                "1000:1000",
                "--read-only",
                f"--tmpfs",
                f"/tmp:rw,noexec,nosuid,size={settings.DOCKER_TMPFS_SIZE}",
                f"--cpus={settings.DOCKER_CPU_LIMIT}",
                f"--memory={settings.DOCKER_MEMORY_LIMIT}",
                f"--pids-limit={settings.DOCKER_PIDS_LIMIT}",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                f"{temp_dir}:/workspace:ro",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                f"PYTHONPATH={':'.join(python_paths)}",
                "-w",
                project_root,
                self.image_name,
                "sh",
                "-c",
                (
                    f"pytest -v --tb=short -rA --junitxml=/tmp/report.xml {test_target}; "
                    f"exit_code=$?; "
                    f"echo '{xml_report_marker}'; "
                    f"cat /tmp/report.xml 2>/dev/null; "
                    f"exit $exit_code"
                ),
            ]

            logger.info("Launching isolated sandbox container %s (timeout: %ds)", container_id, effective_timeout)

            # Run container asynchronously in a thread pool to avoid blocking the event loop
            exec_res = await asyncio.to_thread(
                self._run_docker_process,
                docker_cmd,
                container_id,
                effective_timeout,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Step 6: Parse results
            return self._parse_sandbox_output(
                exec_res=exec_res,
                duration_ms=duration_ms,
                xml_marker=xml_report_marker,
            )

        finally:
            # Step 7: Guaranteed container and workspace cleanup
            self._cleanup_container(container_id)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _run_docker_process(
        self,
        cmd: List[str],
        container_id: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Runs the Docker process with timeout enforcement and process tracking."""
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            duration = (time.perf_counter() - start) * 1000
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "duration_ms": duration,
                "timeout": False,
            }
        except subprocess.TimeoutExpired as te:
            logger.warning("Sandbox container %s timed out after %ds", container_id, timeout)
            # Explicitly force kill container
            self._cleanup_container(container_id)
            duration = (time.perf_counter() - start) * 1000
            stdout = te.stdout if isinstance(te.stdout, str) else (te.stdout.decode("utf-8", "ignore") if te.stdout else "")
            stderr = te.stderr if isinstance(te.stderr, str) else (te.stderr.decode("utf-8", "ignore") if te.stderr else "")
            return {
                "exit_code": -1,
                "stdout": stdout,
                "stderr": f"Execution exceeded maximum timeout limit of {timeout}s.\n{stderr}",
                "duration_ms": duration,
                "timeout": True,
            }
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Subprocess launch error: {str(e)}",
                "duration_ms": duration,
                "timeout": False,
            }

    def _cleanup_container(self, container_id: str) -> None:
        """Forcefully kills and removes container if still existing."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass

    def _parse_sandbox_output(
        self,
        exec_res: Dict[str, Any],
        duration_ms: float,
        xml_marker: str,
    ) -> SandboxExecutionResult:
        """Parses stdout, stderr, exit code, and JUnit XML report into structured TestResult items."""
        full_stdout = exec_res.get("stdout", "")
        stderr = exec_res.get("stderr", "")
        exit_code = exec_res.get("exit_code")
        is_timeout = exec_res.get("timeout", False)

        # Separate human-readable pytest stdout from embedded XML report
        pytest_stdout = full_stdout
        xml_content = ""
        if xml_marker in full_stdout:
            parts = full_stdout.split(xml_marker, 1)
            pytest_stdout = parts[0].strip()
            xml_content = parts[1].strip()

        # Handle Timeout outcome
        if is_timeout:
            return SandboxExecutionResult(
                status=TestResultStatus.TIMEOUT.value,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout=pytest_stdout,
                stderr=stderr,
                error_message="Sandbox container execution timed out. Process killed.",
                is_timeout=True,
                test_results=[
                    TestResult(
                        test_id="timeout_execution",
                        name="Execution Timeout Monitor",
                        test_type=TestType.UNIT,
                        status=TestResultStatus.TIMEOUT,
                        duration_ms=duration_ms,
                        error_message="Test runner exceeded timeout limit.",
                        stack_trace=stderr,
                        stdout=pytest_stdout,
                        stderr=stderr,
                    )
                ],
                telemetry={"timeout": True, "exit_code": exit_code},
            )

        # Parse test results from JUnit XML if available
        test_results: List[TestResult] = []
        if xml_content and "<testsuite" in xml_content:
            test_results = self._parse_junit_xml(xml_content)

        # Fallback to parsing pytest text stdout if XML was empty or malformed
        if not test_results and pytest_stdout:
            test_results = self._parse_pytest_text(pytest_stdout)

        # Determine overall verification status
        # Exit code 0 = all tests passed
        # Exit code 1 = tests failed
        # Exit code 2 = pytest usage error / collection failure
        # Exit code 3 = internal error
        # Exit code 4 = command line usage error
        # Exit code 5 = no tests collected
        collection_traceback = ""
        if exit_code == 2:
            collection_traceback = "\n".join(
                trace.strip()
                for trace in [
                    *(t.stack_trace or "" for t in test_results if t.status == TestResultStatus.ERROR),
                    stderr,
                ]
                if trace and trace.strip()
            )

        if exit_code == 0:
            overall_status = VerificationStatus.PASSED.value
            error_msg = None
        elif exit_code == 1:
            overall_status = VerificationStatus.FAILED.value
            failed_count = sum(1 for t in test_results if t.status == TestResultStatus.FAILED)
            error_msg = f"{failed_count} test assertion(s) failed."
        elif exit_code == 5:
            # No tests collected
            overall_status = VerificationStatus.ERROR.value
            error_msg = "No test cases were discovered in the authorized test suite."
        elif exit_code == 2:
            overall_status = VerificationStatus.ERROR.value
            error_msg = collection_traceback or pytest_stdout or "Pytest collection failed."
        else:
            overall_status = VerificationStatus.ERROR.value
            error_msg = f"Test runner exited with error code {exit_code}: {stderr or pytest_stdout}"

        error_category = None
        diagnostic_text = f"{collection_traceback}\n{pytest_stdout}\n{stderr}"
        if exit_code == 2:
            missing_match = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)", diagnostic_text)
            error_category = "MISSING_DEPENDENCY" if missing_match else "COLLECTION_ERROR"
            for test_result in test_results:
                if test_result.status == TestResultStatus.ERROR:
                    test_result.metrics = {
                        **(test_result.metrics or {}),
                        "failure_origin": error_category,
                        "pytest_exit_code": exit_code,
                    }

        return SandboxExecutionResult(
            status=overall_status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout=pytest_stdout,
            stderr=stderr,
            error_message=error_msg,
            test_results=test_results,
            is_timeout=False,
            telemetry={
                "exit_code": exit_code,
                "total_tests": len(test_results),
                "passed_tests": sum(1 for t in test_results if t.status == TestResultStatus.PASSED),
                "failed_tests": sum(1 for t in test_results if t.status == TestResultStatus.FAILED),
                "error_category": error_category,
                "collection_traceback": collection_traceback or None,
            },
        )

    def _parse_junit_xml(self, xml_text: str) -> List[TestResult]:
        """Extracts individual test outcomes from JUnit XML."""
        results: List[TestResult] = []
        try:
            # Trim any trailing text after </testsuite> or </testsuites>
            end_tag = "</testsuites>" if "</testsuites>" in xml_text else "</testsuite>"
            if end_tag in xml_text:
                xml_text = xml_text[: xml_text.rfind(end_tag) + len(end_tag)]

            root = ET.fromstring(xml_text)
            testcases = root.findall(".//testcase")
            now = datetime.now(timezone.utc)

            for tc in testcases:
                test_name = tc.get("name", "test_unknown")
                time_str = tc.get("time", "0")
                try:
                    duration_ms = float(time_str) * 1000
                except ValueError:
                    duration_ms = 0.0

                failure = tc.find("failure")
                error = tc.find("error")
                skipped = tc.find("skipped")

                if failure is not None:
                    status = TestResultStatus.FAILED
                    err_msg = failure.get("message") or "Assertion failed"
                    stack_trace = failure.text or ""
                elif error is not None:
                    status = TestResultStatus.ERROR
                    err_msg = error.get("message") or "Execution error"
                    stack_trace = error.text or ""
                elif skipped is not None:
                    status = TestResultStatus.SKIPPED
                    err_msg = skipped.get("message") or "Test skipped"
                    stack_trace = None
                else:
                    status = TestResultStatus.PASSED
                    err_msg = None
                    stack_trace = None

                results.append(
                    TestResult(
                        test_id=f"test_{test_name.lower().replace(' ', '_')}",
                        name=test_name,
                        test_name=test_name,
                        test_type=TestType.UNIT,
                        status=status,
                        duration_ms=duration_ms,
                        error_message=err_msg,
                        stack_trace=stack_trace,
                        timestamp=now,
                    )
                )
        except Exception as e:
            logger.warning("Failed to parse JUnit XML report: %s", e)
        return results

    def _parse_pytest_text(self, text: str) -> List[TestResult]:
        """Regex fallback to parse pytest -v standard output."""
        results: List[TestResult] = []
        pattern = re.compile(r"::([a-zA-Z0-9_]+)\s+(PASSED|FAILED|SKIPPED|ERROR)")
        now = datetime.now(timezone.utc)

        for match in pattern.finditer(text):
            test_name = match.group(1)
            raw_status = match.group(2)

            status_map = {
                "PASSED": TestResultStatus.PASSED,
                "FAILED": TestResultStatus.FAILED,
                "SKIPPED": TestResultStatus.SKIPPED,
                "ERROR": TestResultStatus.ERROR,
            }
            status = status_map.get(raw_status, TestResultStatus.ERROR)

            results.append(
                TestResult(
                    test_id=f"test_{test_name.lower()}",
                    name=test_name,
                    test_name=test_name,
                    test_type=TestType.UNIT,
                    status=status,
                    duration_ms=None,
                    timestamp=now,
                )
            )
        return results
