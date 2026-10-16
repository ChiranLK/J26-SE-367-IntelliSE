import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import logger
from app.schemas.common import DefectCategory, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.research_reports import TraceabilityScopedXaiPayload
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.verification import VerificationRunResponse
from app.schemas.xai import (
    CorrectionRecommendation,
    EvidenceItem,
    InferenceProvenance,
    XaiExplanationResponse,
)
from app.services.ollama_client import OllamaClient, OllamaInferenceException



class BaseExplanationProvider(ABC):
    """
    Abstract interface for Explainable AI (XAI) explanation providers.
    Allows future pluggable integration of local open-weights LLMs (e.g. Ollama/Qwen)
    without altering existing API routes, schemas, or frontend components.
    """

    @abstractmethod
    def generate(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        """Synthesizes human-facing XAI explanation from empirical execution artifacts."""
        pass


class DeterministicEvidenceExplanationProvider(BaseExplanationProvider):
    """
    Deterministic, evidence-grounded explanation generator.
    Strictly derives explanations from persisted pytest results, defect reports,
    and submission metadata without external LLM dependencies or fabricated root causes.
    """

    PROVIDER_NAME = "deterministic_evidence_v1"
    SCHEMA_VERSION = "1.0"
    MAX_EXCERPT_CHARS = 1000

    def generate(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        status = run.status

        # 1. PENDING or RUNNING
        if status in (VerificationStatus.PENDING, VerificationStatus.RUNNING):
            return self._handle_pending_or_running(run)

        # 2. Infrastructure failure check
        if self._is_infrastructure_failure(run):
            return self._handle_infrastructure_failure(run)

        # 3. PASSED verification
        if status == VerificationStatus.PASSED:
            return self._handle_passed(run)

        # 4. FAILED verification with application-code defects
        return self._handle_failed_with_defects(run, submission)

    def _is_infrastructure_failure(self, run: VerificationRunResponse) -> bool:
        telemetry = run.execution_telemetry or {}
        if telemetry.get("sandbox_infrastructure_failure") is True:
            return True
        error_msg = (run.error_message or "").lower()
        infra_indicators = (
            "infrastructure isolation failure",
            "docker isolation unavailable",
            "sandbox runner image unavailable",
            "sandbox image failure",
            "docker daemon connection error",
        )
        if any(ind in error_msg for ind in infra_indicators):
            return True
        if run.status == VerificationStatus.ERROR and not run.test_results:
            return True
        return False

    def _handle_pending_or_running(self, run: VerificationRunResponse) -> XaiExplanationResponse:
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:pending').hex[:12]}"
        status_name = run.status.value

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status=status_name,
            eligible=False,
            eligibility_reason=f"Verification run is currently {status_name}; execution evidence is not yet available.",
            summary=(
                f"Verification run {run.id} is currently in state '{status_name}'. "
                "Execution within the isolated Docker sandbox is either pending dispatch or actively processing."
            ),
            what_failed=[],
            confirmed_observations=[],
            evidence_based_interpretation=(
                "No empirical test outcomes or defect reports have been synthesized yet because sandbox execution "
                "has not reached terminal state. A grounded explanation can only be generated once real pytest telemetry is recorded."
            ),
            recommendation=CorrectionRecommendation(
                action="AWAIT_EXECUTION",
                recommended=False,
                reason="Verification pipeline has not completed. Await execution results before evaluating corrective actions.",
                target_audience="Human Engineer / Reviewer",
            ),
            suggested_investigations=[
                "Monitor verification run status until terminal status (PASSED, FAILED, or ERROR) is achieved.",
                "Review Docker container execution telemetry once test runner terminates.",
            ],
            evidence_references={
                "status": status_name,
                "total_tests": 0,
            },
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="Execution in progress; LLM explanation pending completion",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    def _handle_infrastructure_failure(self, run: VerificationRunResponse) -> XaiExplanationResponse:
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:infra').hex[:12]}"
        err_msg = run.error_message or "Docker sandbox container isolation failure"

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status=run.status.value,
            eligible=False,
            eligibility_reason="Run encountered a container sandbox infrastructure isolation error; ineligible for application-code defect explanation.",
            summary=(
                f"Verification run {run.id} failed due to an environmental or container sandbox failure. "
                "This is an infrastructure-level issue and does NOT indicate defective application source code."
            ),
            what_failed=[f"Sandbox Environment Error: {err_msg}"],
            confirmed_observations=[],
            evidence_based_interpretation=(
                "The verification orchestrator failed to complete pytest execution inside the unprivileged Docker container. "
                "Because the failure occurred at the container runtime or image boundary, test oracles could not be evaluated. "
                "Attributing this failure to the submitted code would be inaccurate."
            ),
            recommendation=CorrectionRecommendation(
                action="RETRY_INFRASTRUCTURE",
                recommended=False,
                reason=(
                    "Do not request code modifications from Component 3 for infrastructure anomalies. "
                    "Verify Docker daemon connectivity, image availability, and host resource boundaries, then re-execute the run."
                ),
                target_audience="Human Engineer / Reviewer",
            ),
            suggested_investigations=[
                "Inspect Docker daemon status and verify local image 'intelise-sandbox-runner:py312' is built.",
                "Check Docker host resource limits (memory, CPU shares) and container timeout configurations.",
                "Inspect backend system logs for container spawn or workspace volume mounting failures.",
                "Re-trigger verification execution once container infrastructure is confirmed healthy.",
            ],
            evidence_references={
                "error_message": err_msg,
                "sandbox_failure": True,
            },
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="Infrastructure error; LLM explanation bypassed to avoid inaccurate code attribution",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    def _handle_passed(self, run: VerificationRunResponse) -> XaiExplanationResponse:
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:passed').hex[:12]}"
        total_tests = len(run.test_results or [])

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status="PASSED",
            eligible=False,
            eligibility_reason="Verification run passed successfully; zero defects detected, so corrective feedback is not applicable.",
            summary=(
                f"All {total_tests} executed test case(s) in the authorized test suite passed successfully. "
                "The submitted code meets all evaluated test oracle specifications."
            ),
            what_failed=[],
            confirmed_observations=[],
            evidence_based_interpretation=(
                f"The implementation produced outputs matching all expected values across {total_tests} executed test case(s). "
                "Scope qualification: While passing the authorized test suite confirms compliance with specified test oracles, "
                "it does not constitute an exhaustive mathematical proof of absence of all possible defects under untested conditions."
            ),
            recommendation=CorrectionRecommendation(
                action="ACCEPT_VERIFICATION",
                recommended=False,
                reason="All authorized test cases passed without failure. No corrective cycle with Component 3 is required.",
                target_audience="Human Engineer / Reviewer",
            ),
            suggested_investigations=[
                "Review test suite coverage to confirm edge cases, boundary values, and negative test paths were adequately verified.",
                "Proceed with downstream artifact promotion or deployment pipelines if verification criteria are met.",
            ],
            evidence_references={
                "total_tests": total_tests,
                "passed_tests": total_tests,
                "defects_count": 0,
            },
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="All tests passed; defect explanation not applicable",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    def _handle_failed_with_defects(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        defects: List[DefectReport] = run.defect_reports or []
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:{len(defects)}').hex[:12]}"

        # 1. What failed?
        what_failed: List[str] = []
        confirmed_observations: List[EvidenceItem] = []
        has_partial_diagnostics = False

        fallback_file = submission.filename if submission and submission.filename else "solution.py"

        for d in defects:
            test_name = d.failed_test or d.title or "unnamed_test"
            file_ref = d.file_path or fallback_file
            line_str = f":{d.line_number}" if d.line_number else ""

            # Check if diagnostics are missing
            if not d.expected_value or not d.actual_value:
                has_partial_diagnostics = True

            failure_desc = f"Test '{test_name}' failed at {file_ref}{line_str}"
            if d.assertion_or_exception:
                failure_desc += f" -> {d.assertion_or_exception}"
            what_failed.append(failure_desc)

            # Build confirmed observation
            excerpt = d.traceback_excerpt or ""
            if len(excerpt) > self.MAX_EXCERPT_CHARS:
                excerpt = excerpt[:self.MAX_EXCERPT_CHARS] + " ... [truncated]"

            obs = EvidenceItem(
                test_name=test_name,
                defect_id=d.defect_id,
                failure_category=d.failure_category or "ASSERTION_FAILURE",
                assertion_or_exception=d.assertion_or_exception,
                expected_value=d.expected_value,
                observed_value=d.actual_value,
                file_path=file_ref,
                line_number=d.line_number,
                traceback_excerpt=excerpt if excerpt else None,
            )
            confirmed_observations.append(obs)

        # 2. Evidence-based interpretation
        interpretations: List[str] = []
        for obs in confirmed_observations:
            if obs.expected_value is not None and obs.observed_value is not None:
                diff_text = (
                    f"In test '{obs.test_name}', the authorized test oracle expected value '{obs.expected_value}', "
                    f"but the submitted code returned '{obs.observed_value}'. "
                )
                # Specific domain heuristics for common patterns if present
                if obs.test_name == "test_total_with_tax" and obs.observed_value == "8.0" and obs.expected_value == "108.0":
                    diff_text += (
                        "Observation analysis: The observed value (8.0) corresponds to the tax amount alone (100.0 * 0.08), "
                        "indicating that the calculation returned only the tax without adding the base subtotal."
                    )
                elif obs.test_name == "test_total_without_tax" and obs.observed_value == "0.0" and obs.expected_value == "100.0":
                    diff_text += (
                        "Observation analysis: The observed value (0.0) indicates that when tax_rate is zero, "
                        "the function produced zero rather than returning the untaxed subtotal."
                    )
                else:
                    diff_text += (
                        f"This divergence demonstrates that the evaluated expression in '{obs.file_path}' "
                        "did not compute the required output for the provided test input arguments."
                    )
                interpretations.append(diff_text)
            elif obs.assertion_or_exception:
                interpretations.append(
                    f"Test '{obs.test_name}' triggered '{obs.assertion_or_exception}' in '{obs.file_path}'. "
                    "The failure demonstrates a divergence between the program's runtime state and the test assertion."
                )

        if has_partial_diagnostics:
            interpretations.append(
                "Diagnostic limitation note: One or more failures did not provide complete structured expected/observed "
                "diff values in pytest stdout. The explanation is strictly bounded to confirmed traceback excerpts "
                "without conjecturing missing values."
            )

        interpretations.append(
            "Causal attribution caveat: While the recorded test failures conclusively prove that the returned output "
            "violates the authorized test specification, the assertion diff identifies the symptom of divergence rather "
            "than an authoritative proof of the author's internal algorithmic intent."
        )

        evidence_based_interpretation = "\n\n".join(interpretations)

        # 3. Component 4 recommendation
        defect_count = len(defects)
        recommendation_reason = (
            f"The submitted implementation failed {defect_count} verified test assertion(s). "
            "Component 4 cannot certify or approve software artifacts that fail authorized test specifications. "
            "Because Component 4 operates as an autonomous verification agent and intentionally does not modify user code directly, "
            "it recommends human approval to return the structured technical feedback payload to Component 3 for automated code repair."
        )

        recommendation = CorrectionRecommendation(
            action="RETURN_TO_COMPONENT_3",
            recommended=True,
            reason=recommendation_reason,
            target_audience="Human Engineer / Reviewer",
        )

        # 4. Suggested investigations
        suggested_investigations: List[str] = []
        for obs in confirmed_observations:
            line_hint = f"around line {obs.line_number}" if obs.line_number else "in the corresponding function definition"
            if obs.expected_value is not None and obs.observed_value is not None:
                suggested_investigations.append(
                    f"Review '{obs.file_path}' ({line_hint}) for '{obs.test_name}': "
                    f"investigate why output was '{obs.observed_value}' instead of expected '{obs.expected_value}'."
                )
            else:
                suggested_investigations.append(
                    f"Inspect execution flow in '{obs.file_path}' ({line_hint}) for '{obs.test_name}' to resolve '{obs.assertion_or_exception or 'assertion failure'}'."
                )

        suggested_investigations.append(
            "Verify that calculation formulas properly combine intermediate terms (e.g. subtotal + tax) rather than returning partial intermediate terms."
        )
        suggested_investigations.append(
            "Re-run the authorized pytest test suite in the Docker sandbox after code adjustments to verify all assertions pass cleanly."
        )

        # 5. Executive summary
        summary = (
            f"Verification run {run.id} FAILED with {defect_count} confirmed application-code defect(s) "
            f"across {len(set(d.file_path or fallback_file for d in defects))} file(s). "
            f"{defect_count} assertion(s) in the authorized test suite were violated. "
            "Component 4 recommends human review to approve routing the technical feedback package to Component 3 for automated correction."
        )

        raw_telemetry = run.execution_telemetry or {}
        evidence_references = {
            "defect_ids": [d.defect_id for d in defects],
            "failed_tests": [d.failed_test for d in defects if d.failed_test],
            "total_defects": defect_count,
            "exit_code": raw_telemetry.get("exit_code", 1),
            "duration_ms": raw_telemetry.get("duration_ms"),
        }

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status="FAILED",
            eligible=True,
            eligibility_reason=f"Verification run failed with {defect_count} confirmed application-code defect report(s).",
            summary=summary,
            what_failed=what_failed,
            confirmed_observations=confirmed_observations,
            evidence_based_interpretation=evidence_based_interpretation,
            recommendation=recommendation,
            suggested_investigations=suggested_investigations,
            evidence_references=evidence_references,
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="Deterministic evidence provider executed directly",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )


class OllamaExplanationProvider(BaseExplanationProvider):
    """
    Evidence-grounded XAI explanation provider utilizing local Ollama LLM inference.
    Conditions model generation strictly on verified test execution telemetry.
    Fails closed to DeterministicEvidenceExplanationProvider if Ollama is unavailable or unconfigured.
    """

    PROVIDER_NAME = "ollama_inference_v1"
    SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        fallback_provider: Optional[BaseExplanationProvider] = None,
    ):
        self.client = client or OllamaClient()
        self.fallback = fallback_provider or DeterministicEvidenceExplanationProvider()

    def generate(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        # Non-FAILED or infrastructure failures delegate directly to deterministic handler
        if run.status != VerificationStatus.FAILED or not run.defect_reports:
            return self.fallback.generate(run, submission)

        if not getattr(self.client, "enabled", False):
            fallback_res = self.fallback.generate(run, submission)
            fallback_res.inference_provenance = InferenceProvenance(
                provider="deterministic",
                model=getattr(self.client, "model_name", "qwen2.5-coder:3b"),
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="Ollama disabled by configuration (OLLAMA_ENABLED=False)",
                duration_ms=None,
            )
            return fallback_res

        telemetry = run.execution_telemetry or {}
        if telemetry.get("sandbox_infrastructure_failure") is True:
            return self.fallback.generate(run, submission)

        source_code = submission.code if submission else ""
        filename = submission.filename if submission else "solution.py"

        telemetry_dict = {
            "run_id": run.id,
            "status": run.status.value,
            "total_tests": len(run.test_results),
            "passed_tests": [t.name for t in run.test_results if t.status.value == "PASSED"],
            "failed_tests": [t.name for t in run.test_results if t.status.value in ("FAILED", "ERROR", "TIMEOUT")],
            "exit_code": telemetry.get("exit_code", 1),
            "duration_ms": telemetry.get("duration_ms"),
        }
        defects_dict = [
            {
                "defect_id": d.defect_id,
                "title": d.title,
                "failed_test": d.failed_test,
                "file_path": d.file_path or filename,
                "line_number": d.line_number,
                "category": d.defect_category or d.failure_category,
                "cwe_id": d.cwe_id,
                "diagnostic": d.assertion_or_exception,
                "expected_value": d.expected_value,
                "observed_value": d.actual_value,
                "traceback_excerpt": d.traceback_excerpt,
            }
            for d in run.defect_reports
        ]

        try:
            res = self.client.generate_structured_explanation_sync(
                telemetry=telemetry_dict,
                defects=defects_dict,
                source_code=source_code,
                filename=filename,
            )

            # Validate generated model outputs against empirical evidence
            summary = res.get("summary")
            if not summary or not isinstance(summary, str) or not summary.strip():
                raise OllamaInferenceException("Ollama returned empty or invalid summary")

            evidence_interpretation = res.get("evidence_based_interpretation")
            if not evidence_interpretation or not isinstance(evidence_interpretation, str):
                raise OllamaInferenceException("Ollama returned empty evidence_based_interpretation")

            provenance = res.get("_provenance", {})
            model_used = provenance.get("model", self.client.model_name)
            duration_ms = provenance.get("duration_ms")

            # Clearly distinguish model reasoning from verified empirical facts
            attribution_note = (
                f"\n\n[Model Reasoning Attribution — {model_used}]: The above causal interpretation is synthesized "
                "by local AI inference based on verified pytest telemetry and source code AST. "
                "Empirical observations listed above are deterministic facts; causal explanation represents "
                "the model's algorithmic reasoning."
            )
            distinguished_interpretation = f"{evidence_interpretation.strip()}{attribution_note}"

            explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:ollama').hex[:12]}"

            confirmed_observations: List[EvidenceItem] = []
            for d in run.defect_reports:
                confirmed_observations.append(
                    EvidenceItem(
                        test_name=d.failed_test or d.title or "unnamed_test",
                        defect_id=d.defect_id,
                        failure_category=d.failure_category or "ASSERTION_FAILURE",
                        assertion_or_exception=d.assertion_or_exception,
                        expected_value=d.expected_value,
                        observed_value=d.actual_value,
                        file_path=d.file_path,
                        line_number=d.line_number,
                        traceback_excerpt=d.traceback_excerpt,
                    )
                )

            # Ensure what_failed is non-empty and grounded
            what_failed = res.get("what_failed")
            if not what_failed or not isinstance(what_failed, list):
                what_failed = [d.failed_test for d in run.defect_reports if d.failed_test]

            inference_prov = InferenceProvenance(
                provider="ollama",
                model=model_used,
                genuine_inference=True,
                fallback_used=False,
                fallback_reason=None,
                duration_ms=duration_ms,
            )

            rec_reason = res.get("recommendation_action", "Review model-generated fix suggestions.")
            recommendation = CorrectionRecommendation(
                action="HUMAN_REVIEW_RECOMMENDED",
                recommended=True,
                reason=rec_reason,
                target_audience=res.get("target_audience", "Software Engineer"),
            )

            return XaiExplanationResponse(
                explanation_id=explanation_id,
                verification_run_id=run.id,
                submission_id=run.submission_id,
                verification_status="FAILED",
                eligible=True,
                eligibility_reason=f"Grounded Ollama model '{model_used}' inference completed successfully across {len(run.defect_reports)} defect(s).",
                summary=summary.strip(),
                what_failed=what_failed,
                confirmed_observations=confirmed_observations,
                evidence_based_interpretation=distinguished_interpretation,
                recommendation=recommendation,
                suggested_investigations=[
                    f"Review lines around defect localization in {filename}",
                    "Inspect failed assertion and model interpretation prior to approving repair dispatch",
                ],
                evidence_references={
                    "defect_ids": [d.defect_id for d in run.defect_reports],
                    "failed_tests": [d.failed_test for d in run.defect_reports if d.failed_test],
                    "total_defects": len(run.defect_reports),
                    "model_inference": {
                        **provenance,
                        "genuine_inference": True,
                        "fallback_used": False,
                    },
                },
                explanation_method=f"ollama_inference ({model_used})",
                provider=f"ollama/{model_used}",
                inference_provenance=inference_prov,
                generated_at=datetime.now(timezone.utc),
                schema_version=self.SCHEMA_VERSION,
            )
        except Exception as exc:
            logger.info("Ollama inference unavailable or failed (%s). Falling back to deterministic evidence.", exc)
            fallback_res = self.fallback.generate(run, submission)
            fallback_reason = f"{type(exc).__name__}: {str(exc)}"
            fallback_res.explanation_method = f"deterministic_evidence_v1 (ollama_fallback: {type(exc).__name__})"
            fallback_res.provider = f"deterministic_evidence_v1 (fallback: {type(exc).__name__})"
            fallback_res.inference_provenance = InferenceProvenance(
                provider="deterministic",
                model=getattr(self.client, "model_name", "qwen2.5-coder:3b"),
                genuine_inference=False,
                fallback_used=True,
                fallback_reason=fallback_reason,
                duration_ms=None,
            )
            fallback_res.evidence_references["model_inference"] = {
                "provider": "deterministic",
                "model": getattr(self.client, "model_name", "qwen2.5-coder:3b"),
                "genuine_inference": False,
                "fallback_used": True,
                "fallback_reason": fallback_reason,
            }
            return fallback_res


class XaiExplanationService:
    """
    Dedicated explanation service orchestrating human-facing XAI generation
    and proposal-required machine-readable traceability-scoped defect reports.
    """

    def __init__(self, provider: Optional[BaseExplanationProvider] = None):
        # Default to Ollama provider with transparent deterministic fallback
        self.provider = provider or OllamaExplanationProvider()

    def generate_explanation(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        """
        Generates a human-facing, evidence-grounded XAI explanation.
        Purely read-only and side-effect free; never executes code or mutates storage.
        """
        return self.provider.generate(run, submission)

    def generate_traceability_scoped_explanation(
        self,
        run: VerificationRunResponse,
        defect: DefectReport,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> TraceabilityScopedXaiPayload:
        """
        Synthesizes machine-readable, Component-3-scoped defect explanation (SO3, FR04).
        Scoped to Component 3's traceability graph (requirement IDs, test seams, and target lines).
        """
        req_ids = submission.requirement_ids if submission and submission.requirement_ids else []
        if defect.requirement_id and defect.requirement_id not in req_ids:
            req_ids.append(defect.requirement_id)

        filename = defect.file_path or (submission.filename if submission else "solution.py")
        category_enum = DefectCategory.FUNCTIONAL_BUG
        try:
            if defect.defect_category:
                category_enum = DefectCategory(defect.defect_category)
        except ValueError:
            pass

        return TraceabilityScopedXaiPayload(
            explanation_id=f"xai-scoped-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:{defect.defect_id}').hex[:12]}",
            verification_run_id=run.id,
            submission_id=run.submission_id,
            requirement_ids=req_ids,
            test_seams_implicated=[f"seam:{filename}:{defect.line_number or 0}"],
            defect_id=defect.defect_id,
            defect_category=category_enum,
            cwe_id=defect.cwe_id,
            affected_file=filename,
            line_number=defect.line_number,
            failed_test_name=defect.failed_test or "unknown_test",
            root_cause_explanation=(
                f"Observed {defect.failure_category or 'failure'} in test '{defect.failed_test}'. "
                f"Diagnostic: {defect.assertion_or_exception}."
            ),
            regeneration_guidance=(
                f"Component 3 should regenerate module '{filename}' around line {defect.line_number or 'unknown'} "
                f"to satisfy requirement(s) {', '.join(req_ids) if req_ids else 'baseline specification'}."
            ),
            schema_version="1.0",
        )

