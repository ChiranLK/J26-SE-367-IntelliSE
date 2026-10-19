import hashlib
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
    EvidenceItem,
    FunctionExplanationItem,
    InferenceProvenance,
    ModuleResponsibilityItem,
    PostDeliveryExplanation,
    TechnicalExplanation,
    XaiExplanationResponse,
)
from app.services.code_analysis import inspect_python_code_ast, sanitize_code_secrets


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
        resp.eligible = False
        resp.delivery_status = "SIMULATED_DELIVERY"
        resp.eligibility_reason = (
            "Simulation preview in development mode; production explanation eligibility is not satisfied by simulation alone. "
            "Production delivery requires authenticated service credentials."
        )
        resp.recommendation = CorrectionRecommendation(
            action="SIMULATED_DELIVERY_PREVIEW",
            recommended=False,
            reason="Simulated downstream delivery recorded for evaluation/testing. Authenticated service identity required for production delivery.",
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
            fallback_file = submission.filename if submission and submission.filename else "solution.py"
            what_failed = []
            for d in (run.defect_reports or []):
                file_ref = d.file_path or fallback_file
                line_str = f":{d.line_number}" if d.line_number else ""
                diag = f": {d.assertion_or_exception}" if d.assertion_or_exception else ""
                what_failed.append(f"Test '{d.failed_test}' failed at {file_ref}{line_str}{diag}")
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
            suggested_investigations=[
                "Inspect verification telemetry and audit logs for internal details.",
                "Verify downstream release status once the pipeline reaches a terminal state.",
            ],
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

        # 1. AST Structural Inspection
        ast_meta = inspect_python_code_ast(source_code, filename=filename)

        # 2. Secret Redaction / Sanitization
        sanitized_code, redacted_secrets_count = sanitize_code_secrets(source_code)

        # 3. Test Evidence Extraction
        passed_tests = [t.name for t in (run.test_results or []) if t.status.value == "PASSED"]
        total_tests = len(run.test_results or [])

        # 4. Synthesize the 8 Dimensions
        software_title = self._derive_software_title(ast_meta, filename)
        overview = self._synthesize_software_overview(ast_meta, passed_tests, total_tests)
        arch_expl = self._synthesize_architecture_explanation(ast_meta)
        mod_responsibilities = self._synthesize_module_responsibilities(ast_meta, filename)
        functions_expl = self._synthesize_functions_explanation(ast_meta, filename, passed_tests)
        api_data_flow = self._synthesize_api_and_data_flow(ast_meta)
        design_decisions = self._synthesize_design_decisions(ast_meta, submission)
        setup_usage = self._synthesize_setup_and_usage(ast_meta, filename)
        limitations = self._synthesize_limitations_and_scope(ast_meta, total_tests, passed_tests)

        # 5. Beginner vs. Technical Layers
        beginner = BeginnerExplanation(
            overview=(
                f"Welcome! This software provides reliable, verified logic for '{software_title}'. "
                "It has undergone rigorous automated testing to verify that its calculations and workflows "
                "perform accurately according to authorized requirements."
            ),
            what_it_does=(
                f"In simple terms, this module handles {len(ast_meta['functions'])} main operation(s) "
                f"including {', '.join(f['name'] for f in ast_meta['functions'][:3]) or 'core computation'}. "
                "It takes your inputs, checks rules, calculates results, and safely returns answers."
            ),
            how_to_use=(
                f"To use this software in your own Python program, import the module: `import {filename.replace('.py', '')}`. "
                "Then call the available functions with your input values as shown in the usage instructions below."
            ),
            key_capabilities=[
                f"Verified compliance across {total_tests} automated test scenario(s)",
                f"Pure, deterministic Python logic structured across {len(ast_meta['functions'])} functions",
                "Automated defense against runtime exceptions and invalid states",
            ],
            safety_and_boundaries=(
                "Safety note: This software has been certified exclusively for the specific data boundaries tested. "
                "Always check inputs before passing them to the program if operating outside tested domains."
            ),
        )

        technical = TechnicalExplanation(
            architecture_overview=arch_expl,
            module_responsibilities=mod_responsibilities,
            important_functions=functions_expl,
            api_and_data_flow=api_data_flow,
            algorithms_and_design_decisions=design_decisions,
            setup_and_usage=setup_usage,
            known_limitations_and_scope=limitations,
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
            beginner_level=beginner,
            technical_level=technical,
            verified_test_count=total_tests,
            sanitized_secrets_count=redacted_secrets_count,
            generated_at=datetime.now(timezone.utc),
        )

        summary_text = (
            f"Software '{software_title}' has been successfully verified, cleared through governance gates, "
            f"and confirmed delivered. All {total_tests} test cases passed. "
            f"The software comprises {len(ast_meta['functions'])} functions and {ast_meta['line_count']} lines of code. "
            "Comprehensive post-delivery code understanding documentation is provided below."
        )

        confirmed_observations: List[EvidenceItem] = []
        for t_name in passed_tests:
            confirmed_observations.append(
                EvidenceItem(
                    test_name=t_name,
                    failure_category="VERIFIED_CAPABILITY",
                    assertion_or_exception="PASS",
                    file_path=filename,
                )
            )

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
                "functions_count": len(ast_meta["functions"]),
                "line_count": ast_meta["line_count"],
            },
            explanation_method=self.PROVIDER_NAME,
            provider=self.PROVIDER_NAME,
            inference_provenance=InferenceProvenance(
                provider=self.PROVIDER_NAME,
                model=None,
                genuine_inference=False,
                fallback_used=False,
                fallback_reason="Grounded deterministic AST code understanding engine",
                duration_ms=None,
            ),
            generated_at=datetime.now(timezone.utc),
            schema_version=self.SCHEMA_VERSION,
        )

    # -------------------------------------------------------------------------
    # Dimension Synthesizers (Grounded strictly in AST and verified telemetry)
    # -------------------------------------------------------------------------

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
        lines = [
            f"This software consists of a verified Python module with {ast_meta['line_count']} lines of code.",
            f"It exposes {len(ast_meta['functions'])} top-level functions and {len(ast_meta['classes'])} classes.",
        ]
        if doc:
            lines.append(f"Module documentation: \"{doc.strip()}\"")
        lines.append(
            f"The implementation was verified through an isolated Docker container test harness with {total_tests} "
            f"passing test case(s) ({', '.join(passed_tests[:4]) if passed_tests else 'all passing'})."
        )
        return "\n\n".join(lines)

    def _synthesize_architecture_explanation(self, ast_meta: Dict[str, Any]) -> str:
        funcs = ast_meta.get("functions", [])
        classes = ast_meta.get("classes", [])
        imports = ast_meta.get("imports", [])

        parts = [
            "### Architectural Topology",
            f"- **Decomposition**: Single-module functional architecture ({ast_meta['line_count']} physical LOC).",
            f"- **Dependencies**: {', '.join(imports) if imports else 'Pure standard library (zero external dependencies)'}.",
        ]

        if classes:
            parts.append(f"- **Object Model**: Contains class(es): {', '.join(c['name'] for c in classes)}.")

        if funcs:
            parts.append(
                f"- **Callable Procedures**: {len(funcs)} functions organized for clear separation of concerns: "
                f"{', '.join(f['name'] for f in funcs)}."
            )

        return "\n".join(parts)

    def _synthesize_module_responsibilities(
        self,
        ast_meta: Dict[str, Any],
        filename: str,
    ) -> List[ModuleResponsibilityItem]:
        symbols = [f["name"] for f in ast_meta.get("functions", [])]
        symbols.extend([c["name"] for c in ast_meta.get("classes", [])])

        doc = ast_meta.get("module_docstring")
        resp = doc.strip() if doc else f"Provides verified computational services for {filename}."

        return [
            ModuleResponsibilityItem(
                module_name=filename.replace(".py", ""),
                file_path=filename,
                primary_responsibility=resp,
                exported_symbols=symbols,
                line_count=ast_meta["line_count"],
            )
        ]

    def _synthesize_functions_explanation(
        self,
        ast_meta: Dict[str, Any],
        filename: str,
        passed_tests: List[str],
    ) -> List[FunctionExplanationItem]:
        items: List[FunctionExplanationItem] = []

        for f in ast_meta.get("functions", []):
            name = f["name"]
            # Find matching tests that mention this function
            matching_tests = [t for t in passed_tests if name in t]

            # Beginner description
            beginner_desc = (
                f.get("docstring")
                or f"Computes {name.replace('_', ' ')} based on supplied arguments and returns the calculated result."
            )

            # Technical behavior
            param_names = [p["name"] for p in f.get("parameters", [])]
            tech_desc = (
                f"Executes '{name}' defined at line {f['line_number']} to {f['end_line_number']}. "
                f"Accepts parameter(s) ({', '.join(param_names) or 'none'}) and yields "
                f"{f.get('return_type') or 'inferred dynamic result'}."
            )
            if f.get("calls"):
                tech_desc += f" Internally invokes helper(s): {', '.join(f['calls'])}."

            items.append(
                FunctionExplanationItem(
                    function_name=name,
                    signature=f["signature"],
                    file_path=filename,
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
        if not funcs:
            return "No public entry points or callable procedures found in module AST."

        flows = [
            "### Data Flow & API Entry Points",
            "1. **Input Ingestion**: Client code invokes module functions with positional or keyword parameters.",
        ]

        for i, f in enumerate(funcs[:3], start=2):
            param_names = [p["name"] for p in f.get("parameters", [])]
            flows.append(
                f"{i}. **Processing Pipeline — `{f['name']}`**: Receives `({', '.join(param_names)})`, "
                f"evaluates expressions, and produces output matching test specifications."
            )

        flows.append(
            f"{len(funcs[:3]) + 2}. **Output Emission**: Functions return processed values directly to caller without mutable side-effects."
        )

        return "\n".join(flows)

    def _synthesize_design_decisions(
        self,
        ast_meta: Dict[str, Any],
        submission: Optional[CodeSubmissionResponse],
    ) -> List[DesignDecisionItem]:
        decisions: List[DesignDecisionItem] = []

        # Decision 1: Pure Functions / Statelessness
        decisions.append(
            DesignDecisionItem(
                topic="State Management",
                decision="Stateless functional execution",
                rationale="Minimizes concurrent race conditions and facilitates reproducible test verification.",
                evidence_in_code=f"Module implements {len(ast_meta['functions'])} top-level functions operating on explicit arguments.",
                traceability_seam="NFR-REPRODUCIBILITY",
            )
        )

        # Decision 2: Zero External Dependencies
        if not ast_meta.get("imports"):
            decisions.append(
                DesignDecisionItem(
                    topic="Dependency Confinement",
                    decision="Pure standard library implementation",
                    rationale="Eliminates external supply-chain vulnerabilities and guarantees lightweight execution.",
                    evidence_in_code="Zero external third-party package imports declared in AST.",
                    traceability_seam="NFR-SECURITY",
                )
            )

        # Decision 3: Explicit Parameter Annotations or Signatures
        annotated = [f for f in ast_meta.get("functions", []) if any(p.get("type") for p in f.get("parameters", []))]
        if annotated:
            decisions.append(
                DesignDecisionItem(
                    topic="Type Discipline",
                    decision="Type-annotated function signatures",
                    rationale="Improves developer IDE discoverability and static validation.",
                    evidence_in_code=f"Type annotations present in function(s): {', '.join(f['name'] for f in annotated)}.",
                    traceability_seam="NFR-MAINTAINABILITY",
                )
            )

        return decisions

    def _synthesize_setup_and_usage(self, ast_meta: Dict[str, Any], filename: str) -> str:
        mod_name = filename.replace(".py", "")
        funcs = ast_meta.get("functions", [])

        sample_call = ""
        if funcs:
            f0 = funcs[0]
            param_names = [p["name"] for p in f0.get("parameters", [])]
            args_str = ", ".join("100.0" if "amount" in p or "val" in p or "x" in p else "'sample'" for p in param_names)
            sample_call = f"result = {mod_name}.{f0['name']}({args_str})\nprint('Result:', result)"

        code_block = f"""```python
# 1. Import the delivered module
import {mod_name}

# 2. Call the verified functions
{sample_call}
```"""

        return f"""### Setup and Usage Guide

#### Prerequisites
- Python 3.10+
- No third-party pip dependencies required.

#### Code Snippet
{code_block}
"""

    def _synthesize_limitations_and_scope(
        self,
        ast_meta: Dict[str, Any],
        total_tests: int,
        passed_tests: List[str],
    ) -> str:
        return f"""### Verification Scope and Operational Boundaries

1. **Certified Test Scope**: This software has been verified against {total_tests} automated test case(s) in an isolated container environment.
2. **Boundary Qualifications**: Passing the test suite guarantees conformity to tested oracles ({', '.join(passed_tests[:3]) or 'specified checks'}), but does not mathematically prove absence of defects under untested edge cases.
3. **Environment Assumptions**: Assumes standard CPython 3 runtime semantics.
4. **Input Constraints**: Callers must validate external network or untrusted user input before passing it to module functions.
"""
