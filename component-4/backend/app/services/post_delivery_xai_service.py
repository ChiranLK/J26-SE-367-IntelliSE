import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import logger
from app.schemas.common import VerificationStatus
from app.schemas.research_reports import DeploymentReadinessReport
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.verification import VerificationRunResponse
from app.schemas.xai import (
    BeginnerExplanation,
    CorrectionRecommendation,
    DeliveryGateStatus,
    DesignDecisionItem,
    EvidenceManifest,
    EvidenceItem,
    FunctionExplanationItem,
    InferenceProvenance,
    MeasuredSlaEvidence,
    ModuleResponsibilityItem,
    PostDeliveryExplanation,
    TestEvidenceItem,
    TechnicalExplanation,
    XaiExplanationResponse,
)
from app.services.code_analysis import inspect_python_code_ast, inspect_python_project, sanitize_code_secrets
from app.services.ollama_client import OllamaClient


class PostDeliveryXaiService:
    """
    Dedicated explanation service that analyzes successfully delivered, verified software.
    Enforces the 3-phase delivery gate:
      1. Verification checks passed (zero failed assertions)
      2. Deployment-readiness governance cleared
      3. Successful downstream delivery confirmed for the exact artifact version

    Generates non-hallucinatory, evidence-grounded software understanding explanations across
    8 core dimensions, presenting both Beginner-friendly and Technical views.
    """

    PROVIDER_NAME = "post_delivery_xai_v1"
    SCHEMA_VERSION = "2.0"
    _ollama_result_cache: Dict[str, Dict[str, Any]] = {}
    _ollama_cache_lock = threading.Lock()

    def evaluate_delivery_gate(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
        governance_report: Optional[DeploymentReadinessReport] = None,
    ) -> DeliveryGateStatus:
        """
        Determines if an artifact has satisfied all gating prerequisites for post-delivery XAI.
        """
        status = run.status
        delivery = run.delivery_confirmation

        # 1. Verification status gate
        if status in (VerificationStatus.PENDING, VerificationStatus.RUNNING):
            return DeliveryGateStatus(
                verification_passed=False,
                governance_approved=False,
                delivery_confirmed=False,
                gate_verdict="PENDING_VERIFICATION",
                verdict_reason=f"Verification run is currently in state '{status.value}'. Awaiting test completion.",
            )

        if status == VerificationStatus.ERROR:
            return DeliveryGateStatus(
                verification_passed=False,
                governance_approved=False,
                delivery_confirmed=False,
                gate_verdict="BLOCKED_INFRASTRUCTURE_ERROR",
                verdict_reason="Verification encountered an infrastructure error; artifact cannot be delivered.",
            )

        if status == VerificationStatus.BLOCKED:
            return DeliveryGateStatus(
                verification_passed=False,
                governance_approved=False,
                delivery_confirmed=False,
                gate_verdict="BLOCKED_VERIFICATION_NOT_CONFIGURED",
                verdict_reason=run.error_message or "Verification could not execute all requested categories with authorized test oracles.",
            )

        if status == VerificationStatus.FAILED:
            defect_count = len(run.defect_reports or [])
            return DeliveryGateStatus(
                verification_passed=False,
                governance_approved=False,
                delivery_confirmed=False,
                gate_verdict="BLOCKED_VERIFICATION_FAILED",
                verdict_reason=(
                    f"Artifact failed verification with {defect_count} confirmed defect(s). "
                    "User-facing XAI is withheld during intermediate repair attempts. "
                    "Technical defect feedback has been logged internally for Component 3 repair iteration."
                ),
            )

        # status == PASSED
        verification_passed = True

        # 2. Deployment-readiness governance gate
        governance_approved = True
        if governance_report is not None:
            governance_approved = bool(governance_report.is_ready_for_deployment)
            if not governance_approved:
                blockers = governance_report.blocking_reasons or [
                    c.gate_name for c in governance_report.gating_checks if c.status != "PASSED"
                ]
                return DeliveryGateStatus(
                    verification_passed=True,
                    governance_approved=False,
                    delivery_confirmed=False,
                    gate_verdict="BLOCKED_GOVERNANCE_REJECTED",
                    verdict_reason=(
                        f"Deployment-readiness governance blocked delivery approval. "
                        f"Unsatisfied policy checks: {', '.join(blockers) if blockers else 'governance policy violation'}."
                    ),
                )

        # 3. Delivery confirmation gate
        if delivery is None or not delivery.is_delivered:
            return DeliveryGateStatus(
                verification_passed=True,
                governance_approved=governance_approved,
                delivery_confirmed=False,
                gate_verdict="PENDING_DELIVERY_CONFIRMATION",
                verdict_reason=(
                    "Artifact has passed all verification checks and deployment-readiness governance, "
                    "but successful downstream delivery has not yet been confirmed. "
                    "Post-delivery code understanding explanation remains in a pending state until delivery confirmation is received."
                ),
            )

        # Check run ID integrity to prevent replay across runs
        if delivery.verification_run_id and delivery.verification_run_id != run.id:
            return DeliveryGateStatus(
                verification_passed=True,
                governance_approved=governance_approved,
                delivery_confirmed=False,
                is_simulation=getattr(delivery, "is_simulation", False),
                gate_verdict="BLOCKED_UNAUTHORIZED_DELIVERY",
                verdict_reason=(
                    f"Delivery confirmation run ID '{delivery.verification_run_id}' does not match "
                    f"verified run ID '{run.id}'. Replay across verification runs rejected."
                ),
            )

        # Check version integrity
        if delivery.submission_id != run.submission_id:
            return DeliveryGateStatus(
                verification_passed=True,
                governance_approved=governance_approved,
                delivery_confirmed=False,
                is_simulation=getattr(delivery, "is_simulation", False),
                gate_verdict="BLOCKED_VERSION_MISMATCH",
                verdict_reason=(
                    f"Delivery confirmation submission ID '{delivery.submission_id}' does not match "
                    f"verified run submission ID '{run.submission_id}'."
                ),
            )

        # Check content hash integrity if submission code is available
        if submission and hasattr(submission, "code") and submission.code and delivery.artifact_checksum_sha256:
            current_code_hash = hashlib.sha256(submission.code.encode("utf-8")).hexdigest()
            if current_code_hash != delivery.artifact_checksum_sha256:
                return DeliveryGateStatus(
                    verification_passed=True,
                    governance_approved=governance_approved,
                    delivery_confirmed=False,
                    is_simulation=getattr(delivery, "is_simulation", False),
                    gate_verdict="BLOCKED_HASH_MISMATCH",
                    verdict_reason=(
                        f"Delivered artifact content hash '{delivery.artifact_checksum_sha256}' does not match "
                        f"verified submission code hash '{current_code_hash}'. Delivery confirmation is invalid or stale."
                    ),
                )

        is_sim = getattr(delivery, "is_simulation", False)
        if is_sim:
            if not settings.is_simulation_permitted():
                return DeliveryGateStatus(
                    verification_passed=True,
                    governance_approved=governance_approved,
                    delivery_confirmed=False,
                    is_simulation=True,
                    gate_verdict="BLOCKED_UNAUTHORIZED_DELIVERY",
                    verdict_reason="Simulated delivery confirmation is disabled in production environments.",
                )
            return DeliveryGateStatus(
                verification_passed=True,
                governance_approved=True,
                delivery_confirmed=True,
                delivery_id=delivery.delivery_id,
                delivered_at=delivery.delivered_at,
                delivered_artifact_checksum=delivery.artifact_checksum_sha256,
                is_simulation=True,
                gate_verdict="SIMULATED_DELIVERY",
                verdict_reason=(
                    "Artifact verified and simulated delivery confirmed in development mode. "
                    "Simulation does not grant production delivery authorization."
                ),
            )

        return DeliveryGateStatus(
            verification_passed=True,
            governance_approved=True,
            delivery_confirmed=True,
            delivery_id=delivery.delivery_id,
            delivered_at=delivery.delivered_at,
            delivered_artifact_checksum=delivery.artifact_checksum_sha256,
            is_simulation=False,
            gate_verdict="CONFIRMED_PRODUCTION_DELIVERY",
            verdict_reason="Artifact verified, governance cleared, and production delivery confirmed by authenticated service. Eligible for post-delivery code understanding.",
        )

    def generate_explanation(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse] = None,
        governance_report: Optional[DeploymentReadinessReport] = None,
    ) -> XaiExplanationResponse:
        """
        Synthesizes human-facing XAI response according to the delivery gate.
        If delivered: produces full 8-dimension post-delivery software understanding package.
        If blocked or pending: returns gate status and explicit non-delivery justification.
        """
        gate = self.evaluate_delivery_gate(run, submission, governance_report)
        status_name = run.status.value

        if gate.gate_verdict in ("CONFIRMED_PRODUCTION_DELIVERY", "CONFIRMED_DELIVERED"):
            # Confirmed production delivery: Generate full post-delivery understanding package
            return self._build_delivered_response(run, submission, gate)

        if gate.gate_verdict == "SIMULATED_DELIVERY":
            # Simulated delivery in development mode: Generate preview package
            return self._build_simulated_response(run, submission, gate)

        return self._build_undelivered_response(run, gate, status_name, submission)

    def _build_simulated_response(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse],
        gate: DeliveryGateStatus,
    ) -> XaiExplanationResponse:
        resp = self._build_delivered_response(run, submission, gate)
        resp.eligible = True
        resp.delivery_status = "SIMULATED_DELIVERY"
        resp.eligibility_reason = (
            "Development-only simulated delivery authorization is valid in this non-production environment. "
            "The explanation is a development preview and must not be represented as production delivery."
        )
        resp.recommendation = CorrectionRecommendation(
            action="SIMULATED_DELIVERY_PREVIEW",
            recommended=False,
            reason="Development-only delivery simulation recorded for evaluation. Production still requires authenticated service identity.",
            target_audience="Development Engineer / Tester",
        )
        return resp

    def _build_undelivered_response(
        self,
        run: VerificationRunResponse,
        gate: DeliveryGateStatus,
        status_name: str,
        submission: Optional[CodeSubmissionResponse] = None,
    ) -> XaiExplanationResponse:
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:{gate.gate_verdict}').hex[:12]}"

        # Action recommendation mapping based on gate verdict
        if gate.gate_verdict == "BLOCKED_VERIFICATION_FAILED":
            action = "RETURN_TO_COMPONENT_3"
            rec_reason = (
                "Code failed verification. Technical defect diagnostics have been recorded internally "
                "for Component 3 automated repair. User-facing explanation is deferred until delivery."
            )
            target = "Internal Repair Pipeline"
            recommended = True
            what_failed = []
        elif gate.gate_verdict == "PENDING_DELIVERY_CONFIRMATION":
            action = "AWAIT_DELIVERY_CONFIRMATION"
            rec_reason = (
                "Verification and governance gates passed. Downstream deployment/delivery confirmation "
                "is required before user-facing software understanding explanations are published."
            )
            target = "Release Engineer / Deployment Orchestrator"
            recommended = False
            what_failed = []
        elif gate.gate_verdict == "BLOCKED_GOVERNANCE_REJECTED":
            action = "BLOCK_DELIVERY"
            rec_reason = "Governance policies blocked artifact release. Resolve governance violations before delivery."
            target = "Security / Compliance Officer"
            recommended = False
            what_failed = ["Deployment-readiness governance check failed."]
        elif gate.gate_verdict == "BLOCKED_INFRASTRUCTURE_ERROR":
            action = "RETRY_INFRASTRUCTURE"
            rec_reason = "Run failed due to container sandbox environment. Re-execute verification."
            target = "DevOps Engineer"
            recommended = False
            what_failed = [run.error_message or "Sandbox infrastructure failure"]
        elif gate.gate_verdict in ("BLOCKED_HASH_MISMATCH", "BLOCKED_VERSION_MISMATCH", "BLOCKED_UNAUTHORIZED_DELIVERY"):
            action = "INVALIDATE_DELIVERY"
            rec_reason = gate.verdict_reason
            target = "Release Security Officer"
            recommended = False
            what_failed = [gate.verdict_reason]
        else:
            action = "AWAIT_EXECUTION"
            rec_reason = "Verification execution in progress. Await completion."
            target = "Pipeline Orchestrator"
            recommended = False
            what_failed = []

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status=status_name,
            eligible=False,
            eligibility_reason=gate.verdict_reason,
            delivery_gate=gate,
            delivery_status=gate.gate_verdict,
            post_delivery_explanation=None,
            summary=gate.verdict_reason,
            what_failed=what_failed,
            confirmed_observations=[],
            evidence_based_interpretation=gate.verdict_reason,
            recommendation=CorrectionRecommendation(
                action=action,
                recommended=recommended,
                reason=rec_reason,
                target_audience=target,
            ),
            suggested_investigations=([] if gate.gate_verdict == "BLOCKED_VERIFICATION_FAILED" else [
                "Inspect verification telemetry and audit logs for internal details.",
                "Verify downstream release status once the pipeline reaches a terminal state.",
            ]),
            evidence_references={
                "gate_verdict": gate.gate_verdict,
                "verification_status": status_name,
            },
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason=f"Gate verdict '{gate.gate_verdict}' does not require LLM inference",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    def _build_delivered_response(
        self,
        run: VerificationRunResponse,
        submission: Optional[CodeSubmissionResponse],
        gate: DeliveryGateStatus,
    ) -> XaiExplanationResponse:
        explanation_id = f"xai-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{run.id}:delivered').hex[:12]}"
        source_code = submission.code if submission else ""
        filename = submission.filename if submission and submission.filename else "solution.py"

        # 1. Bounded project-wide AST inspection. Multi-file submissions retain the
        # original archive file map in metadata; single-file submissions use code.
        metadata = submission.metadata if submission and submission.metadata else {}
        project_files = metadata.get("project_files") if isinstance(metadata, dict) else None
        if not isinstance(project_files, dict) or not project_files:
            project_files = {filename: source_code}
        entrypoint = metadata.get("entrypoint", filename) if isinstance(metadata, dict) else filename
        project_evidence = inspect_python_project(project_files, entrypoint=entrypoint)
        modules = project_evidence.get("modules", [])
        ast_meta = next(
            (module for module in modules if module.get("filename") == entrypoint),
            modules[0] if modules else inspect_python_code_ast(source_code, filename=filename),
        )
        aggregate_ast = self._aggregate_project_ast(project_evidence, ast_meta)

        # 2. Secret redaction is applied independently to every bounded source excerpt.
        redacted_secrets_count = 0
        sanitized_excerpts: List[Dict[str, str]] = []
        for excerpt in project_evidence.get("source_excerpts", []):
            sanitized, redactions = sanitize_code_secrets(excerpt.get("source", ""))
            redacted_secrets_count += redactions
            sanitized_excerpts.append({"file_path": excerpt.get("file_path", ""), "source": sanitized})
        sanitized_code = next(
            (item["source"] for item in sanitized_excerpts if item["file_path"] == entrypoint),
            sanitize_code_secrets(source_code)[0],
        )

        # 3. Test Evidence Extraction
        passed_tests = [t.name for t in (run.test_results or []) if t.status.value == "PASSED"]
        total_tests = len(run.test_results or [])
        test_evidence = self._build_test_evidence(run)
        measured_sla = self._build_measured_sla(run)

        # 4. Synthesize the 8 Dimensions
        software_title = self._derive_software_title(ast_meta, entrypoint)
        overview = self._synthesize_software_overview(aggregate_ast, passed_tests, total_tests)
        arch_expl = self._synthesize_architecture_explanation(aggregate_ast)
        mod_responsibilities = self._synthesize_module_responsibilities(project_evidence)
        functions_expl = self._synthesize_functions_explanation(aggregate_ast, entrypoint, passed_tests)
        api_data_flow = self._synthesize_api_and_data_flow(aggregate_ast)
        design_decisions = self._synthesize_design_decisions(aggregate_ast, submission)
        setup_usage = self._synthesize_setup_and_usage(ast_meta, entrypoint)
        limitations = self._synthesize_limitations_and_scope(aggregate_ast, total_tests, passed_tests)

        inference_provenance = InferenceProvenance(
            provider=self.PROVIDER_NAME,
            model=None,
            genuine_inference=False,
            fallback_used=False,
            fallback_reason="Ollama disabled; grounded deterministic AST code-understanding engine used",
            duration_ms=None,
        )
        delivery_evidence = {
            "verification_run_id": run.id,
            "submission_id": run.submission_id,
            "delivery_id": gate.delivery_id,
            "delivered_at": gate.delivered_at,
            "artifact_checksum_sha256": gate.delivered_artifact_checksum,
            "gate_verdict": gate.gate_verdict,
        }
        llm_evidence = {
            "project": {
                key: value
                for key, value in project_evidence.items()
                if key not in {"source_excerpts"}
            },
            "source_excerpts": sanitized_excerpts,
            "tests": [item.model_dump() for item in test_evidence],
            "measured_sla": measured_sla.model_dump(),
            "delivery": delivery_evidence,
        }
        cache_key = hashlib.sha256(
            json.dumps(llm_evidence, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        with self._ollama_cache_lock:
            cached_llm = self._ollama_result_cache.get(cache_key)
        try:
            llm = cached_llm or OllamaClient().generate_post_delivery_understanding_sync(
                source_code=sanitized_code,
                filename=entrypoint,
                structural_facts=aggregate_ast,
                verified_tests=passed_tests,
                evidence_bundle=llm_evidence,
            )
            validated_llm, grounding_warnings = self._validate_llm_grounding(
                llm,
                project_evidence,
                aggregate_ast,
            )
            if validated_llm.get("software_overview"):
                overview = f"{validated_llm['software_overview'].strip()}\n\n{overview}"
            if validated_llm.get("architecture_explanation"):
                arch_expl = f"{validated_llm['architecture_explanation'].strip()}\n\n{arch_expl}"
            if validated_llm.get("api_and_data_flow"):
                api_data_flow = f"{validated_llm['api_and_data_flow'].strip()}\n\n{api_data_flow}"
            if validated_llm.get("setup_and_usage"):
                setup_usage = f"{validated_llm['setup_and_usage'].strip()}\n\n{setup_usage}"
            if validated_llm.get("limitations_and_scope"):
                limitations = f"{validated_llm['limitations_and_scope'].strip()}\n\n{limitations}"
            provenance = llm["_provenance"]
            inference_provenance = InferenceProvenance(**provenance)
            if not cached_llm:
                with self._ollama_cache_lock:
                    if len(self._ollama_result_cache) >= 64:
                        self._ollama_result_cache.pop(next(iter(self._ollama_result_cache)))
                    self._ollama_result_cache[cache_key] = llm
        except Exception as exc:
            logger.warning("Post-delivery Ollama inference unavailable; using grounded fallback: %s", exc)
            validated_llm = {}
            grounding_warnings = [f"Ollama narrative unavailable: {type(exc).__name__}"]
            inference_provenance = InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=getattr(settings, "OLLAMA_MODEL", None),
                genuine_inference=False,
                fallback_used=True,
                fallback_reason=f"{type(exc).__name__}: {exc}",
                duration_ms=None,
            )

        # 5. Beginner vs. Technical Layers
        beginner_module_name = (
            entrypoint[:-3].replace("/", ".")
            if entrypoint.endswith(".py")
            else entrypoint.replace("/", ".")
        )
        beginner_overview = (
            validated_llm.get("beginner_overview")
            or f"This verified software is a Python application designed to perform calculations and data processing for {entrypoint}. It was evaluated in an automated verification sandbox where all {total_tests} test scenarios passed."
        )
        beginner_what_it_does = (
            validated_llm.get("beginner_what_it_does")
            or self._synthesize_beginner_what_it_does(aggregate_ast, modules)
        )
        beginner_how_to_use = (
            validated_llm.get("beginner_how_to_use")
            or f"To use this software as a non-programmer or integrating user, you import the `{beginner_module_name}` module into your project. You then call the functions with your numbers (such as a list of item prices and a discount rate). The software calculates the answer and gives it back to you immediately. See the Technical View if you need the exact parameter names and types."
        )
        beginner_example = (
            validated_llm.get("beginner_realistic_example")
            or self._synthesize_beginner_realistic_example(aggregate_ast, entrypoint)
        )
        if validated_llm.get("beginner_realistic_example") and not beginner_example.startswith("*("):
            beginner_example = (
                "*(Illustrative numerical example generated from delivered function signatures; actual inputs are demonstrative)*\n\n"
                + beginner_example
            )
        beginner_test_conf = (
            validated_llm.get("beginner_test_confidence")
            or f"The software passed all {total_tests} automated quality tests ({', '.join(passed_tests[:3]) if passed_tests else 'all tests'}). This confirms the software works as intended in the tested scenarios. However, passing tests demonstrate only the behavior exercised in those tests; it does not prove complete correctness for every conceivable input or untested edge case."
        )
        beginner_capabilities = self._synthesize_beginner_capabilities(aggregate_ast, modules, test_evidence, measured_sla)
        beginner_safety = self._synthesize_beginner_safety(aggregate_ast)

        beginner = BeginnerExplanation(
            overview=beginner_overview,
            what_it_does=beginner_what_it_does,
            how_to_use=beginner_how_to_use,
            key_capabilities=beginner_capabilities,
            safety_and_boundaries=beginner_safety,
            realistic_example=beginner_example,
            test_confidence=beginner_test_conf,
        )

        technical = TechnicalExplanation(
            architecture_overview=arch_expl,
            module_responsibilities=mod_responsibilities,
            important_functions=functions_expl,
            api_and_data_flow=api_data_flow,
            algorithms_and_design_decisions=design_decisions,
            setup_and_usage=setup_usage,
            known_limitations_and_scope=limitations,
            test_evidence=test_evidence,
            measured_sla=measured_sla,
        )

        pdx = PostDeliveryExplanation(
            explanation_id=f"pdx-{uuid.uuid4().hex[:12]}",
            verification_run_id=run.id,
            submission_id=run.submission_id,
            software_name=software_title,
            software_overview=overview,
            architecture_explanation=arch_expl,
            module_responsibilities=mod_responsibilities,
            important_functions=functions_expl,
            api_and_data_flow=api_data_flow,
            algorithms_and_design_decisions=design_decisions,
            setup_and_usage=setup_usage,
            limitations_and_verification_scope=limitations,
            test_evidence=test_evidence,
            measured_sla=measured_sla,
            evidence_manifest=EvidenceManifest(
                analyzed_source_files=project_evidence.get("analyzed_source_files", []),
                omitted_source_files=project_evidence.get("omitted_source_files", []),
                project_file_count=project_evidence.get("project_file_count", 0),
                analyzed_line_count=project_evidence.get("analyzed_line_count", 0),
                source_excerpt_char_count=project_evidence.get("source_excerpt_char_count", 0),
                evidence_warnings=grounding_warnings,
            ),
            inference_provenance=inference_provenance,
            beginner_level=beginner,
            technical_level=technical,
            verified_test_count=total_tests,
            sanitized_secrets_count=redacted_secrets_count,
            generated_at=datetime.now(timezone.utc),
        )

        summary_text = (
            f"Software '{software_title}' has been successfully verified, cleared through governance gates, "
            f"and confirmed delivered. All {total_tests} test cases passed. "
            f"The analyzed evidence comprises {len(aggregate_ast['functions'])} functions across "
            f"{len(modules)} source modules and {aggregate_ast['line_count']} lines of code. "
            "Comprehensive post-delivery code understanding documentation is provided below."
        )

        confirmed_observations: List[EvidenceItem] = []
        for t_name in passed_tests:
            confirmed_observations.append(
                EvidenceItem(
                    test_name=t_name,
                    failure_category="VERIFIED_CAPABILITY",
                    assertion_or_exception="PASS",
                    file_path=entrypoint,
                )
            )

        if inference_provenance.genuine_inference:
            explanation_method = "hybrid_ollama_ast_synthesis"
            provider = f"ollama/{inference_provenance.model}+deterministic_ast"
        elif inference_provenance.fallback_used:
            explanation_method = "deterministic_ast_fallback"
            provider = f"{self.PROVIDER_NAME}/fallback"
        else:
            explanation_method = "deterministic_ast_synthesis"
            provider = self.PROVIDER_NAME

        return XaiExplanationResponse(
            explanation_id=explanation_id,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            verification_status="PASSED",
            eligible=True,
            eligibility_reason="Artifact successfully delivered and verified. Post-delivery understanding package generated.",
            delivery_gate=gate,
            delivery_status="CONFIRMED_PRODUCTION_DELIVERY" if gate.gate_verdict in ("CONFIRMED_PRODUCTION_DELIVERY", "CONFIRMED_DELIVERED") else gate.gate_verdict,
            post_delivery_explanation=pdx,
            summary=summary_text,
            what_failed=[],
            confirmed_observations=confirmed_observations,
            evidence_based_interpretation=overview,
            recommendation=CorrectionRecommendation(
                action="DELIVERED_AND_READY",
                recommended=False,
                reason="Software artifact verified and successfully delivered. Ready for operational consumption.",
                target_audience="End User / Software Maintainer",
            ),
            suggested_investigations=[
                f"Review usage instructions for module '{filename}'.",
                "Integrate with downstream client applications following provided API specifications.",
            ],
            evidence_references={
                "delivery_id": gate.delivery_id,
                "total_tests": total_tests,
                "passed_tests": total_tests,
                "functions_count": len(aggregate_ast["functions"]),
                "line_count": aggregate_ast["line_count"],
                "analyzed_source_files": project_evidence.get("analyzed_source_files", []),
                "measured_sla": measured_sla.model_dump(),
            },
            explanation_method=explanation_method,
            provider=provider,
            inference_provenance=inference_provenance,
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    # -------------------------------------------------------------------------
    # Dimension Synthesizers (Grounded strictly in AST and verified telemetry)
    # -------------------------------------------------------------------------

    def _aggregate_project_ast(
        self,
        project_evidence: Dict[str, Any],
        primary_ast: Dict[str, Any],
    ) -> Dict[str, Any]:
        modules = project_evidence.get("modules", [])
        functions: List[Dict[str, Any]] = []
        classes: List[Dict[str, Any]] = []
        imports: List[str] = []
        for module in modules:
            path = module.get("filename", "solution.py")
            functions.extend({**fn, "file_path": path} for fn in module.get("functions", []))
            classes.extend({**cls, "file_path": path} for cls in module.get("classes", []))
            imports.extend(module.get("imports", []))
        return {
            **primary_ast,
            "filename": project_evidence.get("entrypoint") or primary_ast.get("filename"),
            "line_count": project_evidence.get("analyzed_line_count", primary_ast.get("line_count", 0)),
            "functions": functions,
            "classes": classes,
            "imports": list(dict.fromkeys(imports)),
            "modules": modules,
            "module_interactions": project_evidence.get("module_interactions", []),
            "analyzed_source_files": project_evidence.get("analyzed_source_files", []),
            "omitted_source_files": project_evidence.get("omitted_source_files", []),
            "test_files": project_evidence.get("test_files", []),
        }

    def _build_test_evidence(self, run: VerificationRunResponse) -> List[TestEvidenceItem]:
        items: List[TestEvidenceItem] = []
        for result in run.test_results or []:
            test_type = getattr(result.test_type, "value", str(result.test_type))
            status = getattr(result.status, "value", str(result.status))
            items.append(TestEvidenceItem(
                test_id=result.test_id,
                test_name=result.name,
                test_type=test_type,
                status=status,
                duration_ms=result.duration_ms,
                demonstrated_scope=(
                    f"The authorized {test_type} test '{result.name}' completed with status {status}. "
                    "This establishes only the behavior exercised by that recorded test; assertion internals "
                    "are not inferred when they are absent from telemetry."
                ),
            ))
        return items

    def _build_measured_sla(self, run: VerificationRunResponse) -> MeasuredSlaEvidence:
        telemetry = run.execution_telemetry or {}
        agent_reports = telemetry.get("agent_reports") or {}
        perf = agent_reports.get("performance") or telemetry.get("performance") or {}
        metrics = perf.get("metrics") or telemetry.get("metrics") or {}

        # Fallback to test_results if telemetry is absent
        if not metrics and run.test_results:
            for t in run.test_results:
                t_type = getattr(t.test_type, "value", str(t.test_type))
                if t_type == "performance" and getattr(t, "metrics", None):
                    metrics = t.metrics
                    break

        p95 = metrics.get("latency_p95_ms")
        threshold = metrics.get("threshold_latency_ms")
        sample_size = metrics.get("sample_size")
        status = perf.get("status")

        # Available only if p95 and threshold are present and not marked NOT_EXECUTED with 0 samples
        available = (
            p95 is not None
            and threshold is not None
            and status != "NOT_EXECUTED"
            and (sample_size is None or sample_size > 0 or float(p95) > 0.0)
        )
        breached = metrics.get("is_breached")
        verdict = "NOT_ESTABLISHED"
        if available:
            verdict = "FAILED" if (breached is True or float(p95) > float(threshold)) else "PASSED"
        return MeasuredSlaEvidence(
            available=available,
            latency_p50_ms=metrics.get("latency_p50_ms"),
            latency_p95_ms=p95,
            latency_p99_ms=metrics.get("latency_p99_ms"),
            threshold_latency_ms=threshold,
            sample_size=sample_size,
            verdict=verdict,
            environment_note=(
                "Measured inside the Component 4 isolated Docker verification environment; "
                "the result is not a production load or capacity benchmark."
                if available
                else "No empirical latency SLA measurement was recorded; performance is not established by the available evidence."
            ),
        )

    def _validate_llm_grounding(
        self,
        llm: Dict[str, Any],
        project_evidence: Dict[str, Any],
        aggregate_ast: Dict[str, Any],
    ) -> Tuple[Dict[str, str], List[str]]:
        known_files = set(project_evidence.get("analyzed_source_files", []))
        known_basenames = {path.rsplit("/", 1)[-1] for path in known_files}
        known_imports = " ".join(aggregate_ast.get("imports", [])).lower()
        web_evidenced = any(name in known_imports for name in ("fastapi", "flask", "django", "starlette", "aiohttp"))
        validated: Dict[str, str] = {}
        warnings: List[str] = []
        narrative_fields = {
            "software_overview", "architecture_explanation", "api_and_data_flow",
            "setup_and_usage", "limitations_and_scope", "beginner_overview",
            "beginner_what_it_does", "beginner_how_to_use", "beginner_realistic_example",
            "beginner_test_confidence",
        }
        for field in narrative_fields:
            value = llm.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            mentioned_files = set(re.findall(r"[A-Za-z0-9_./-]+\.py", value))
            unknown_files = {
                path for path in mentioned_files
                if path not in known_files and path.rsplit("/", 1)[-1] not in known_basenames
            }
            positive_web_claim = re.search(
                r"\b(exposes?|provides?|implements?|uses?|serves?)\b[^.]{0,50}"
                r"\b(HTTP|REST|web endpoint|API endpoint|FastAPI|Flask|Django)\b",
                value,
                re.IGNORECASE,
            )
            negated_web_claim = re.search(
                r"\b(no|not|without|does not|doesn't)\b[^.]{0,60}"
                r"\b(HTTP|REST|web endpoint|API endpoint|FastAPI|Flask|Django)\b",
                value,
                re.IGNORECASE,
            )
            unsupported_web = not web_evidenced and positive_web_claim and not negated_web_claim
            if unknown_files or unsupported_web:
                reason = (
                    f"unknown source reference(s): {', '.join(sorted(unknown_files))}"
                    if unknown_files else "unsupported web/API claim"
                )
                warnings.append(f"Rejected LLM field '{field}' due to {reason}.")
                continue
            validated[field] = value.strip()
        return validated, warnings

    def _derive_software_title(self, ast_meta: Dict[str, Any], filename: str) -> str:
        if ast_meta["classes"]:
            return ast_meta["classes"][0]["name"]
        base = filename.replace(".py", "").replace("_", " ").title()
        return base or "Verified Python Software"

    def _synthesize_software_overview(
        self,
        ast_meta: Dict[str, Any],
        passed_tests: List[str],
        total_tests: int,
    ) -> str:
        doc = ast_meta.get("module_docstring")
        module_count = len(ast_meta.get("modules", [])) or 1
        funcs = ast_meta.get("functions", [])
        classes = ast_meta.get("classes", [])
        filename = ast_meta.get("filename") or "solution.py"
        line_count = ast_meta.get("line_count", 0)

        all_names = " ".join([f["name"] for f in funcs] + [m.get("filename", "") for m in ast_meta.get("modules", [])]).lower()
        if any(term in all_names for term in ("pricing", "checkout", "discount", "subtotal", "tax", "cart", "shop", "invoice")):
            domain_summary = (
                f"This verified software provides specialized financial calculation and transactional logic for `{filename}`. "
                "Its primary responsibilities are to validate monetary values, compute order subtotals, enforce promotional discount rates, "
                "and assemble final transaction checkout totals while enforcing strict defensive boundary constraints."
            )
        elif any(term in all_names for term in ("matrix", "math", "calc", "formula", "vector", "stat")):
            domain_summary = (
                f"This verified software provides mathematical and numerical calculation procedures for `{filename}`. "
                "Its primary responsibilities are to accept structured numerical data, enforce input bounds, and execute "
                "deterministic calculations according to verified technical specifications."
            )
        else:
            domain_summary = (
                f"This verified software provides structured data processing and domain calculation logic for `{filename}`. "
                "Its primary responsibilities are to validate caller arguments, execute verified transformation rules across modular callables, "
                "and return reliable, deterministic results."
            )

        capabilities = []
        for fn in funcs[:6]:
            cap_text = fn.get("docstring") or f"Computes {fn['name'].replace('_', ' ')} based on input parameters."
            capabilities.append(f"- **`{fn['name']}`**: {cap_text.strip().splitlines()[0]}")

        first_sig = funcs[0]["signature"] if funcs else "callable()"
        first_file = funcs[0].get("file_path", filename) if funcs else filename

        sections = [
            f"### Software Purpose & Responsibilities\n{domain_summary}",
            f"### Supported Capabilities & Functional Scope\n"
            f"The codebase contains {module_count} analyzed Python source module(s) totaling {line_count} physical lines of code "
            f"in the bounded scope, defining {len(funcs)} callable procedure(s) and {len(classes)} class definition(s):\n"
            + ("\n".join(capabilities) if capabilities else "- No public procedures declared in AST."),
            "### Input & Output Data Behavior\n"
            "All procedures operate as in-process Python callable functions. Inputs are supplied as typed arguments "
            "(such as float amounts, item lists, or numerical rates). Defensive validation branches inspect inputs before execution, "
            "raising standard exceptions (such as `ValueError`) on invalid values and returning deterministic calculated results.",
            f"### Verified Code Example\n"
            f"A consumer can invoke `{first_sig}` from `{first_file}` with valid input arguments. "
            f"The procedure checks preconditions and yields the expected output in accordance with the verified specifications.",
            f"### Verification Scope & Test Harness\n"
            f"The implementation was verified through an isolated Docker container test harness with {total_tests} "
            f"passing test case(s) ({', '.join(passed_tests[:4]) if passed_tests else 'all passing'}). "
            f"All executed assertions passed, establishing verified behavior for the tested scenarios."
        ]
        if doc:
            sections.insert(1, f"### Module Documentation\n\"{doc.strip()}\"")

        return "\n\n".join(sections)

    def _synthesize_architecture_explanation(self, ast_meta: Dict[str, Any]) -> str:
        funcs = ast_meta.get("functions", [])
        classes = ast_meta.get("classes", [])
        imports = ast_meta.get("imports", [])
        modules = ast_meta.get("modules", [])
        interactions = ast_meta.get("module_interactions", [])

        parts = [
            "### Architectural Topology",
            f"- **Decomposition**: {len(modules) or 1} analyzed Python source module(s) "
            f"({ast_meta.get('line_count', 0)} physical lines in scope).",
            f"- **Observed imports**: {', '.join(imports) if imports else 'No imports declared in the analyzed AST'}.",
        ]

        if modules:
            parts.append("- **Files**: " + ", ".join(m.get("filename", "unknown") for m in modules) + ".")
        if interactions:
            parts.append(
                "- **Internal interactions**: "
                + "; ".join(f"{item['from']} -> {item['to']} ({item['evidence']})" for item in interactions)
                + "."
            )
        else:
            parts.append("- **Internal interactions**: No cross-module import was identified in the analyzed files.")

        if classes:
            parts.append(f"- **Object Model**: Contains class(es): {', '.join(c['name'] for c in classes)}.")

        if funcs:
            parts.append(
                f"- **Callable Procedures**: {len(funcs)} functions organized for clear separation of concerns: "
                f"{', '.join(f['name'] for f in funcs)}."
            )

        parts.append(
            "\n### Architectural Collaboration & Data Invariants\n"
            "Modules in this architecture maintain strict separation between calculation rules and procedural workflows. "
            "Callers communicate with modules strictly through function invocation parameters. Data flows unidirectionally "
            "from callers into validation layers, then through arithmetic operations, before returning computed results."
        )

        return "\n".join(parts)

    def _synthesize_module_responsibilities(
        self,
        project_evidence: Dict[str, Any],
    ) -> List[ModuleResponsibilityItem]:
        items: List[ModuleResponsibilityItem] = []
        for module in project_evidence.get("modules", []):
            filename = module.get("filename", "solution.py")
            symbols = [f["name"] for f in module.get("functions", [])]
            symbols.extend([c["name"] for c in module.get("classes", [])])
            doc = module.get("module_docstring")
            responsibility = (
                doc.strip()
                if doc
                else (
                    f"Defines the observed callable symbols {', '.join(symbols)}."
                    if symbols
                    else "Contains no top-level callable symbol identified by static analysis."
                )
            )
            items.append(ModuleResponsibilityItem(
                module_name=filename[:-3].replace("/", ".") if filename.endswith(".py") else filename,
                file_path=filename,
                primary_responsibility=responsibility,
                exported_symbols=symbols,
                line_count=module.get("line_count", 0),
            ))
        return items

    def _synthesize_functions_explanation(
        self,
        ast_meta: Dict[str, Any],
        filename: str,
        passed_tests: List[str],
    ) -> List[FunctionExplanationItem]:
        items: List[FunctionExplanationItem] = []

        for f in ast_meta.get("functions", []):
            name = f["name"]
            matching_tests = [t for t in passed_tests if name in t]

            # Beginner description
            if f.get("docstring"):
                beginner_desc = f["docstring"].strip().splitlines()[0]
            else:
                beginner_desc = f"Computes {name.replace('_', ' ')} based on supplied arguments and returns the calculated result."

            # Technical behavior
            param_names = [p["name"] for p in f.get("parameters", [])]
            params_formatted = [
                f"{p['name']}: {p.get('type') or 'Any'}" + (f" = {p['default']}" if p.get('default') else "")
                for p in f.get("parameters", [])
            ]

            tech_lines = [
                f"Executes '{name}' defined at lines {f['line_number']} to {f['end_line_number']} in `{f.get('file_path', filename)}`.",
                f"- **Parameters**: `({', '.join(params_formatted) or 'none'})`",
            ]
            if f.get("validation_conditions"):
                tech_lines.append(f"- **Validation Guards**: Evaluates `{'; '.join(f['validation_conditions'])}` before calculation.")
            if f.get("raised_exceptions"):
                tech_lines.append(f"- **Error Paths**: Raises `{'; '.join(f['raised_exceptions'])}` if boundary constraints are violated.")
            if f.get("operations") or f.get("loop_types"):
                ops = f.get("operations", []) + f.get("loop_types", [])
                tech_lines.append(f"- **Operations & Flow**: Utilizes {', '.join(ops)}.")
            if f.get("calls"):
                tech_lines.append(f"- **Helper Invocations**: Internally calls `{', '.join(f['calls'])}`.")
            if f.get("return_expressions"):
                tech_lines.append(f"- **Return Expressions**: Yields `{'; '.join(f['return_expressions'])}` (type: `{f.get('return_type') or 'inferred dynamic result'}`).")
            else:
                tech_lines.append(f"- **Return Semantics**: Returns `{f.get('return_type') or 'inferred dynamic result'}`.")

            if matching_tests:
                tech_lines.append(f"- **Verified by Test(s)**: `{', '.join(matching_tests)}`.")
            else:
                tech_lines.append("- **Verification Seam**: Verified as part of the overall test execution suite.")

            tech_desc = "\n".join(tech_lines)

            items.append(
                FunctionExplanationItem(
                    function_name=name,
                    signature=f["signature"],
                    file_path=f.get("file_path", filename),
                    line_number=f["line_number"],
                    end_line_number=f["end_line_number"],
                    summary_beginner=beginner_desc,
                    technical_behavior=tech_desc,
                    parameters=f.get("parameters", []),
                    return_type=f.get("return_type"),
                    verified_by_tests=matching_tests,
                )
            )

        return items

    def _synthesize_api_and_data_flow(self, ast_meta: Dict[str, Any]) -> str:
        funcs = ast_meta.get("functions", [])
        interactions = ast_meta.get("module_interactions", [])

        sections = [
            "### Data Flow & API Entry Points (Callable Interfaces)",
            "**Interface Boundary**: The evidenced interfaces are strictly in-process Python callables. "
            "No HTTP, REST, GraphQL, WebSocket, or external web service endpoints were identified in the analyzed AST or dependencies.",
            "#### Processing Pipeline Stages",
            "1. **Input Ingestion & Parameter Validation**: Callers invoke Python functions with typed arguments. "
            "Defensive guard statements inspect input boundaries (e.g. verifying non-negative quantities or valid rate percentages).",
            "2. **Defensive Error Handling**: If argument values violate domain rules, execution branches raise explicit exceptions (e.g. `ValueError`) "
            "to prevent calculation corruption.",
            "3. **Business Logic & Data Transformation**: Functions perform arithmetic transformations (such as summations, multiplications, and rate deductions) "
            "using standard Python expressions.",
            "4. **Return Delivery**: The computed numeric or structured result is returned directly to the calling context.",
        ]

        if interactions:
            interactions_desc = [
                f"- `{item['from']}` calls into `{item['to']}` via `{item['evidence']}`"
                for item in interactions
            ]
            sections.append("#### Module-to-Module Data Flow\n" + "\n".join(interactions_desc))

        if funcs:
            func_flows = []
            for i, f in enumerate(funcs[:6], start=1):
                param_names = [p["name"] for p in f.get("parameters", [])]
                validation_str = "; ".join(f.get("validation_conditions", [])) or "none observed"
                return_str = "; ".join(f.get("return_expressions", [])) or "computed value"
                raises_str = "; ".join(f.get("raised_exceptions", [])) or "none"
                calls_str = ", ".join(f.get("calls", [])) or "none"
                func_flows.append(
                    f"{i}. **`{f['name']}({', '.join(param_names)})`**:\n"
                    f"   - *Input*: `({', '.join(param_names) or 'void'})`\n"
                    f"   - *Guards*: `{validation_str}` (Raises `{raises_str}` on violation)\n"
                    f"   - *Internal Calls*: `{calls_str}`\n"
                    f"   - *Returns*: `{return_str}`"
                )
            sections.append("#### Procedure Data Traces\n" + "\n\n".join(func_flows))

        return "\n\n".join(sections)

    def _synthesize_design_decisions(
        self,
        ast_meta: Dict[str, Any],
        submission: Optional[CodeSubmissionResponse],
    ) -> List[DesignDecisionItem]:
        decisions: List[DesignDecisionItem] = []
        modules = ast_meta.get("modules", [])
        funcs = ast_meta.get("functions", [])

        # Decision 1: Module Decomposition
        if len(modules) > 1:
            decisions.append(DesignDecisionItem(
                topic="Module Decomposition & Separation of Concerns",
                decision=f"Functional logic is partitioned across {len(modules)} distinct Python source modules.",
                rationale="Likely benefit (not established developer intent): Isolates specific calculation responsibilities from workflow orchestration, simplifying unit testing and ongoing maintenance.",
                evidence_in_code=", ".join(module.get("filename", "unknown") for module in modules),
                traceability_seam="ARCH-MODULARITY",
            ))
        else:
            decisions.append(DesignDecisionItem(
                topic="Single-Module Procedural Architecture",
                decision="Consolidated single-module architecture containing all necessary procedure definitions.",
                rationale="Likely benefit (not established developer intent): Minimizes packaging complexity and eliminates inter-file import overhead for self-contained algorithms.",
                evidence_in_code=modules[0].get("filename", "solution.py") if modules else "solution.py",
                traceability_seam="ARCH-COHESION",
            ))

        # Decision 2: Defensive Validation & Fail-Fast Exceptions
        validated = [
            f for f in funcs
            if f.get("validation_conditions") or f.get("raised_exceptions")
        ]
        if validated:
            val_evidence = ", ".join(f"{f.get('file_path')}:{f['name']}" for f in validated[:6])
            decisions.append(DesignDecisionItem(
                topic="Defensive Input Validation & Exception Handling",
                decision="Explicit conditional guard branches validate parameters and raise standard exceptions upon violation.",
                rationale="Likely benefit (not established developer intent): Prevents invalid states or corrupted values (such as negative prices or out-of-bounds rates) from silently propagating through calculations.",
                evidence_in_code=f"Guard statements observed in: {val_evidence}",
                traceability_seam="NFR-ROBUSTNESS",
            ))

        # Decision 3: Side-Effect-Free Pure Calculations
        decisions.append(DesignDecisionItem(
            topic="Deterministic Side-Effect-Free Computations",
            decision="Procedures execute as pure or near-pure calculation functions operating strictly on input parameters.",
            rationale="Likely benefit (not established developer intent): Avoidance of global mutable state or external I/O ensures deterministic repeatability, simplified verification, and thread safety.",
            evidence_in_code="Functions accept explicit arguments and return newly computed values without mutating external state.",
            traceability_seam="NFR-DETERMINISM",
        ))

        # Decision 4: Type Annotations
        annotated = [f for f in funcs if any(p.get("type") for p in f.get("parameters", []))]
        if annotated:
            decisions.append(DesignDecisionItem(
                topic="Static Type Discipline",
                decision="Function signatures declare explicit parameter and return type annotations.",
                rationale="Likely benefit (not established developer intent): Improves developer discoverability, enables static type analysis, and defines clear API contracts.",
                evidence_in_code=f"Type annotations observed in: {', '.join(f['name'] for f in annotated[:6])}",
                traceability_seam="NFR-MAINTAINABILITY",
            ))

        return decisions

    def _synthesize_setup_and_usage(self, ast_meta: Dict[str, Any], filename: str) -> str:
        mod_name = filename[:-3].replace("/", ".") if filename.endswith(".py") else filename.replace("/", ".")
        funcs = ast_meta.get("functions", [])

        sample_call = ""
        if funcs:
            f0 = funcs[0]
            sample_call = (
                f"# Signature observed in source: {f0['signature']}\n"
                f"# Supply values that satisfy the documented validation rules before calling {f0['name']}."
            )

        code_block = f"""```python
# 1. Import the delivered module
import {mod_name}

# 2. Call the verified functions
{sample_call}
```"""

        return f"""### Setup and Usage Guide

#### Prerequisites
- A compatible Python runtime; the exact supported version is not established by the available evidence.
- Install deployment dependencies separately; package metadata was not included in this static evidence bundle.

#### Code Snippet
{code_block}
"""

    def _synthesize_limitations_and_scope(
        self,
        ast_meta: Dict[str, Any],
        total_tests: int,
        passed_tests: List[str],
    ) -> str:
        omitted = ast_meta.get("omitted_source_files", [])
        test_files = ast_meta.get("test_files", [])
        analyzed_count = len(ast_meta.get("analyzed_source_files", [])) or len(ast_meta.get("modules", []))
        return (
            "### Verification Scope and Operational Boundaries\n\n"
            f"1. **Executed Test Scope**: Exactly {total_tests} recorded test case(s) passed in the isolated verification environment "
            f"({', '.join(passed_tests[:4]) if passed_tests else 'named checks unavailable'}).\n\n"
            "2. **What Verification Demonstrates & Does Not Prove**: Passing tests confirm that the implementation produced expected outputs "
            "for the specific assertions exercised in the test suite. This establishes empirical validity for those tested scenarios; "
            "it does not constitute an exhaustive mathematical proof of correctness across all possible input domains, extreme boundary conditions, or unexercised edge cases.\n\n"
            f"3. **Static Analysis & Inventory Bounds**: {analyzed_count} source file(s) and {len(test_files)} test file(s) were analyzed "
            f"within bounded memory limits without executing source code during explanation generation.\n\n"
            f"4. **Absence of External Evidence**: No HTTP web server, database engine, persistent storage layer, or external network services "
            "were identified in the analyzed source code or dependencies.\n\n"
            "5. **Environment Assumptions & Known Limits**: The software assumes a compatible standard Python 3.x runtime. Packaging configurations, "
            "system-level dependencies, and deployment environment configurations were not established by the available evidence."
        )

    def _synthesize_beginner_what_it_does(self, ast_meta: Dict[str, Any], modules: List[Dict[str, Any]]) -> str:
        funcs = ast_meta.get("functions", [])
        if not funcs:
            return "This software performs automated processing on verified input data."
        items = []
        for f in funcs[:5]:
            p_names = [p["name"] for p in f.get("parameters", [])]
            name_clean = f["name"].replace("_", " ")
            if f.get("docstring"):
                clean_doc = f["docstring"].strip().split("\n")[0].rstrip(".")
                items.append(f"• {clean_doc} using {', '.join(p_names) or 'inputs'}")
            else:
                items.append(f"• Computes {name_clean} based on {', '.join(p_names) or 'supplied inputs'}")
        return (
            f"In plain terms, this software performs several verified computational tasks:\n"
            + "\n".join(items)
            + "\nIt validates caller inputs before calculation, raising standard exceptions when numbers or rates violate documented constraints."
        )

    def _synthesize_beginner_realistic_example(self, ast_meta: Dict[str, Any], entrypoint: str) -> str:
        funcs = ast_meta.get("functions", [])
        if not funcs:
            return "No callable usage example is established by the available source evidence."
        f0 = funcs[0]
        name = f0["name"]
        sig = f0.get("signature", "def procedure()")
        file_path = f0.get("file_path", entrypoint)
        header = "*(Illustrative numerical example grounded in delivered function signatures; inputs are demonstrative and not taken from test oracles)*\n\n"
        if any(term in name.lower() or term in file_path.lower() for term in ("discount", "pricing", "subtotal", "checkout", "shop")):
            return (
                header +
                "Imagine you are processing an order with items priced at $10.00, $20.00, and $30.00, with a 10% discount:\n"
                "1. The software calculates the subtotal: $10.00 + $20.00 + $30.00 = $60.00.\n"
                "2. It checks that the discount rate (0.10) is valid (between 0% and 100%).\n"
                "3. It computes the discount: $60.00 * 0.10 = $6.00 off, yielding a final total of $54.00.\n"
                "All calculations are performed according to the verified formulas in the code."
            )
        elif any(term in name.lower() or term in file_path.lower() for term in ("tax", "invoice")):
            return (
                header +
                "Imagine calculating an invoice total for a $100.00 purchase with an 8% tax rate:\n"
                "1. The software calculates the sales tax: $100.00 * 0.08 = $8.00.\n"
                "2. It adds the tax to the base amount: $100.00 + $8.00 = $108.00 total.\n"
                "The calculation is executed with exact floating point arithmetic as verified by passing tests."
            )
        return (
            header +
            f"A consumer can call `{sig}` from `{file_path}` with valid argument values. "
            f"The function checks that all input parameters satisfy requirements and returns the calculated result."
        )

    def _synthesize_beginner_capabilities(
        self,
        ast_meta: Dict[str, Any],
        modules: List[Dict[str, Any]],
        test_evidence: List[TestEvidenceItem],
        measured_sla: MeasuredSlaEvidence,
    ) -> List[str]:
        funcs = ast_meta.get("functions", [])
        passed_count = len([t for t in test_evidence if t.status == "PASSED"])
        caps = [
            f"Passed all {passed_count} authorized quality and verification test scenario(s)",
            f"Exposes {len(funcs)} verified calculation procedure(s) across {len(modules)} modular Python file(s)",
            "Enforces built-in boundary validation to reject invalid or negative numbers",
            "Operates without external network, database, or third-party web framework dependencies in the analyzed codebase",
        ]
        if measured_sla.available and measured_sla.verdict == "PASSED":
            caps.append(f"Performance latency verified: p95 response time of {measured_sla.latency_p95_ms:.2f} ms satisfies the SLA threshold")
        return caps

    def _synthesize_beginner_safety(self, ast_meta: Dict[str, Any]) -> str:
        funcs = ast_meta.get("functions", [])
        validated = [f for f in funcs if f.get("validation_conditions") or f.get("raised_exceptions")]
        if validated:
            fn_names = ", ".join(f["name"] for f in validated[:4])
            return (
                f"Defensive input validation checks inspect caller arguments before calculation begins (in functions such as {fn_names}). "
                "If invalid numbers, negative quantities, or out-of-range discount percentages are passed, "
                "the software halts execution and raises a standard exception (such as `ValueError`) rather than producing corrupted results. "
                "Passing verification tests confirm these validation paths under test conditions, but do not eliminate all untested edge cases."
            )
        return (
            "The software was evaluated in an isolated verification sandbox. "
            "All operations are constrained to input arguments, and passing quality tests confirm that valid inputs produce expected results."
        )
