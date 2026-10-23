import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import logger
from app.schemas.common import ConvergenceRiskLevel, DefectSeverity, DeploymentReadinessStatus, VerificationStatus
from app.schemas.research_reports import (
    DeploymentReadinessReport,
    IterationCycleSummary,
    ModuleConvergenceRiskReport,
    ReadinessGatingCheck,
    SemanticDriftReport,
)
from app.schemas.submission import SubmissionResponse
from app.schemas.verification import VerificationRunResponse


class GovernanceReportService:
    """
    Produces proposal-required Module Convergence Risk Reports (SO5, FR10)
    and Deployment Readiness Reports (FR11, NFR01).
    """

    def generate_convergence_risk_report(
        self,
        run: VerificationRunResponse,
        submission: Optional[SubmissionResponse] = None,
        drift_report: Optional[SemanticDriftReport] = None,
    ) -> ModuleConvergenceRiskReport:
        """
        Synthesizes the Module Convergence Risk Report (SO5, FR10).
        Calculates architectural risk based on iteration count, stability, and superficial convergence.
        """
        now = datetime.now(timezone.utc)
        report_id = f"mcrr-{uuid.uuid4().hex[:12]}"
        module_name = submission.filename if submission and submission.filename else "solution.py"

        iterations = run.feedback_iterations or []
        total_iterations = max(len(iterations), 1)

        # 1. Determine Iteration History
        iteration_history = []
        for it in iterations:
            it_time = getattr(it, "created_at", now) or now
            iteration_history.append(
                IterationCycleSummary(
                    iteration_number=it.iteration_number,
                    defects_count=it.defects_count,
                    status=str(getattr(it, "status", getattr(it, "delivery_status", "DISPATCHED"))),
                    resolved_defects=max(0, it.defects_count - len(run.defect_reports)),
                    timestamp=it_time,
                )
            )

        # 2. Superficial Convergence Check (FR07, SO5)
        is_superficial = False
        if drift_report and drift_report.has_drift and run.status == VerificationStatus.PASSED:
            is_superficial = True

        # 3. Determine Risk Level
        signals = []
        if total_iterations == 1 and run.status == VerificationStatus.PASSED:
            risk_level = ConvergenceRiskLevel.LOW
            signals.append("Clean first-pass convergence: module satisfied all test oracles on initial verification.")
        elif total_iterations <= 3 and run.status == VerificationStatus.PASSED and not is_superficial:
            risk_level = ConvergenceRiskLevel.MEDIUM
            signals.append(f"Standard convergence: module required {total_iterations} feedback cycles before passing.")
        elif total_iterations >= 4:
            risk_level = ConvergenceRiskLevel.HIGH
            signals.append(
                f"High iteration overhead: module required {total_iterations} cycles, indicating architectural instability."
            )
        else:
            risk_level = ConvergenceRiskLevel.HIGH

        if is_superficial:
            risk_level = ConvergenceRiskLevel.CRITICAL
            signals.append(
                "Superficial convergence detected: module passed tests only after test assertions or scopes were modified."
            )

        # Non-convergent runs
        if run.status in (VerificationStatus.FAILED, VerificationStatus.ERROR):
            signals.append(f"Unresolved failures: {len(run.defect_reports)} defect(s) remain open.")
            if total_iterations >= 3:
                risk_level = ConvergenceRiskLevel.CRITICAL
                signals.append("Module failed repeatedly across multiple iterations; automatic convergence capped.")

        # 4. Escalation Decision (FR09)
        escalation_required = risk_level in (ConvergenceRiskLevel.HIGH, ConvergenceRiskLevel.CRITICAL) or is_superficial
        escalation_reason = None
        if escalation_required:
            if is_superficial:
                escalation_reason = "Escalated to human review due to detected test-suite semantic drift / assertion weakening."
            elif run.status != VerificationStatus.PASSED:
                escalation_reason = f"Escalated to human review due to persistent failure after {total_iterations} feedback cycle(s)."
            else:
                escalation_reason = f"Escalated to human review due to high iteration count ({total_iterations} cycles)."

        return ModuleConvergenceRiskReport(
            report_id=report_id,
            module_name=module_name,
            verification_run_id=run.id,
            submission_id=run.submission_id,
            total_iterations=total_iterations,
            risk_level=risk_level,
            is_superficial_convergence=is_superficial,
            escalation_required=escalation_required,
            escalation_reason=escalation_reason,
            diagnostic_signals=signals,
            iteration_history=iteration_history,
            issued_at=now,
        )

    def generate_deployment_readiness_report(
        self,
        run: VerificationRunResponse,
        submission: Optional[SubmissionResponse] = None,
        drift_report: Optional[SemanticDriftReport] = None,
        convergence_report: Optional[ModuleConvergenceRiskReport] = None,
    ) -> DeploymentReadinessReport:
        """
        Synthesizes the Deployment Readiness Report (FR11, NFR01).
        Enforces release safety gates with zero tolerance for unresolved defects or semantic drift.
        """
        now = datetime.now(timezone.utc)
        report_id = f"drr-{uuid.uuid4().hex[:12]}"
        module_name = submission.filename if submission and submission.filename else "solution.py"

        gating_checks: List[ReadinessGatingCheck] = []
        blocking_reasons: List[str] = []

        # Gate 1: All Verification Tests Passed (FR11)
        tests_passed = run.status == VerificationStatus.PASSED and len(run.test_results) > 0
        gating_checks.append(
            ReadinessGatingCheck(
                gate_name="ALL_TESTS_PASSED",
                status="PASSED" if tests_passed else "FAILED",
                required=True,
                details=(
                    f"Verification run status is '{run.status.value}'. "
                    f"{sum(1 for t in run.test_results if t.status.value == 'PASSED')}/{len(run.test_results)} test(s) passed."
                ),
            )
        )
        if not tests_passed:
            blocking_reasons.append(f"Module has not passed authorized test suite (current status: {run.status.value}).")

        # Gate 2: Zero Critical / Security Vulnerabilities (SO2, FR03)
        critical_defects = [
            d for d in run.defect_reports
            if d.severity == DefectSeverity.CRITICAL or d.defect_category == "security_vulnerability"
        ]
        sec_passed = len(critical_defects) == 0
        gating_checks.append(
            ReadinessGatingCheck(
                gate_name="ZERO_CRITICAL_SECURITY_DEFECTS",
                status="PASSED" if sec_passed else "FAILED",
                required=True,
                details=f"Identified {len(critical_defects)} critical or security vulnerability defect(s).",
            )
        )
        if not sec_passed:
            blocking_reasons.append(f"Module contains {len(critical_defects)} unmitigated critical or security defect(s).")

        # Gate 3: Zero Unresolved Performance Bottlenecks (SO1, SO2)
        perf_defects = [d for d in run.defect_reports if d.defect_category == "performance_bottleneck"]
        perf_report = (run.execution_telemetry or {}).get("agent_reports", {}).get("performance", {})
        perf_status = perf_report.get("status") if isinstance(perf_report, dict) else None
        perf_executed = perf_status not in (None, "NOT_EXECUTED", "BLOCKED", "PENDING")
        perf_passed = perf_executed and perf_status == "PASSED" and len(perf_defects) == 0
        perf_gate_status = "PASSED" if perf_passed else ("NOT_EXECUTED" if not perf_executed else "FAILED")
        gating_checks.append(
            ReadinessGatingCheck(
                gate_name="ZERO_PERFORMANCE_BOTTLENECK_BREACHES",
                status=perf_gate_status,
                # Performance is a release gate only when an authorized workload
                # was actually configured and executed.  An absent workload stays
                # visibly NOT_EXECUTED; it is never mislabeled as PASSED.
                required=perf_executed,
                details=(
                    "Performance testing was NOT_EXECUTED; no passing performance verdict is available."
                    if not perf_executed
                    else f"Performance status is '{perf_status}'; identified {len(perf_defects)} unmitigated threshold breach(es)."
                ),
            )
        )
        if perf_executed and not perf_passed:
            blocking_reasons.append(f"Module contains {len(perf_defects)} unmitigated performance bottleneck(s).")

        # Gate 4: Zero Semantic Drift (FR07, NFR01)
        has_unresolved_drift = drift_report.has_drift if drift_report else False
        drift_passed = not has_unresolved_drift
        gating_checks.append(
            ReadinessGatingCheck(
                gate_name="ZERO_SEMANTIC_DRIFT",
                status="PASSED" if drift_passed else "FAILED",
                required=True,
                details=(
                    "No test suite assertion weakening or deletion detected."
                    if drift_passed
                    else f"Detected test suite semantic drift: {', '.join(drift_report.drift_types if drift_report else [])}"
                ),
            )
        )
        if not drift_passed:
            blocking_reasons.append(
                "NFR01 Safety Violation: Module cannot be authorized for deployment while an unresolved semantic-drift flag exists."
            )

        # Gate 5: Acceptable Convergence Risk (SO5, FR10)
        risk_level = convergence_report.risk_level if convergence_report else ConvergenceRiskLevel.LOW
        risk_acceptable = risk_level in (ConvergenceRiskLevel.LOW, ConvergenceRiskLevel.MEDIUM)
        gating_checks.append(
            ReadinessGatingCheck(
                gate_name="CONVERGENCE_RISK_ACCEPTABLE",
                status="PASSED" if risk_acceptable else "WARNING",
                required=False,
                details=f"Convergence risk evaluated at level '{risk_level.value}'.",
            )
        )
        if not risk_acceptable and risk_level == ConvergenceRiskLevel.CRITICAL:
            blocking_reasons.append("Module evaluated at CRITICAL convergence risk; human sign-off required.")

        # Final Readiness Determination
        all_required_passed = all(check.status == "PASSED" for check in gating_checks if check.required)
        if all_required_passed and len(blocking_reasons) == 0:
            readiness_status = DeploymentReadinessStatus.READY
            is_ready = True
        elif not all_required_passed:
            readiness_status = DeploymentReadinessStatus.BLOCKED
            is_ready = False
        else:
            readiness_status = DeploymentReadinessStatus.NEEDS_REVIEW
            is_ready = False

        # Cryptographic Provenance Hash
        source_code = submission.code if submission else ""
        suite_id = getattr(run, "test_suite_id", "") or ""
        provenance_content = f"{run.id}:{run.status.value}:{source_code}:{suite_id}:{now.isoformat()}"
        provenance_hash = hashlib.sha256(provenance_content.encode("utf-8")).hexdigest()

        return DeploymentReadinessReport(
            report_id=report_id,
            module_name=module_name,
            verification_run_id=run.id,
            readiness_status=readiness_status,
            is_ready_for_deployment=is_ready,
            gating_checks=gating_checks,
            blocking_reasons=blocking_reasons,
            provenance_hash=provenance_hash,
            issued_at=now,
        )
