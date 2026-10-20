"""
INTELISE Component 4 — Phase 3C.1A: Defect Evidence Reconciliation Service.

Defines transparent, documented reconciliation rules for combining deterministic test
execution evidence and AST security findings with bounded LLM defect reasoning hypotheses.

Core Principles:
1. Hard deterministic evidence cannot be overwritten or dismissed by model output.
2. Verified test failures and AST security findings strictly preserve FAILED verification status.
3. LLM contributes where deterministic evidence is under-specified:
   - Line localization for assertion-only tracebacks
   - Root-cause explanation enrichment
   - Actionable repair recommendations
   - Defect taxonomy refinement for ambiguous failures
4. AI contribution is recorded with complete audit telemetry.
"""
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.schemas.common import DefectSeverity
from app.schemas.defect_report import DefectReport
from app.schemas.llm_defect_reasoning import (
    AIContributionTelemetry,
    InferenceStatus,
    LLMDefectHypothesis,
    SupportedDefectCategory,
)


class DefectReconciliationService:
    """
    Reconciles deterministic verification findings with bounded LLM hypotheses.
    Enforces documented precedence rules and populates AI contribution instrumentation.
    """

    def reconcile(
        self,
        deterministic_defects: List[DefectReport],
        llm_hypothesis: Optional[LLMDefectHypothesis],
        candidate_code: str,
        evaluation_mode: str = "LLM_ASSISTED",
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[DefectReport], AIContributionTelemetry, List[Dict[str, Any]]]:
        """
        Reconciles deterministic defect reports with LLM hypothesis.
        Returns:
            - reconciled_defects: List[DefectReport]
            - ai_telemetry: AIContributionTelemetry
            - machine_guidance: List[Dict[str, Any]] formatted for Component 3 feedback
        """
        code_lines = candidate_code.splitlines() if candidate_code else []
        total_code_lines = len(code_lines)
        reconciled = [d.model_copy(deep=True) for d in deterministic_defects]
        reconciliation_log: List[str] = []

        is_llm_mode = evaluation_mode.upper() == "LLM_ASSISTED"

        if not is_llm_mode or llm_hypothesis is None:
            # DETERMINISTIC_ONLY MODE
            ai_telemetry = AIContributionTelemetry(
                evaluation_mode="DETERMINISTIC_ONLY",
                llm_enabled=False,
                actual_llm_invocation_count=0,
                successful_llm_response_count=0,
                failed_llm_response_count=0,
                model_identifier=getattr(llm_hypothesis, "model_identifier", "none") if llm_hypothesis else "none",
                model_digest=getattr(llm_hypothesis, "model_digest", None) if llm_hypothesis else None,
                inference_latency_ms=0.0,
                timeout_events=0,
                fallback_events=0,
                validated_llm_findings=0,
                rejected_llm_findings=0,
                llm_changed_classification=False,
                llm_changed_localization=False,
                llm_changed_repair_recommendation=False,
                reconciliation_log=["Evaluation mode: DETERMINISTIC_ONLY. Bypassed LLM inference."],
            )
            return reconciled, ai_telemetry, []

        # LLM_ASSISTED MODE
        invocations = 1
        success_count = 1 if llm_hypothesis.inference_status == InferenceStatus.SUCCESS else 0
        failed_count = 1 if llm_hypothesis.inference_status in (InferenceStatus.FAILED, InferenceStatus.FALLBACK, InferenceStatus.TIMEOUT) else 0
        timeout_count = 1 if llm_hypothesis.inference_status == InferenceStatus.TIMEOUT else 0
        fallback_count = 1 if llm_hypothesis.inference_status == InferenceStatus.FALLBACK or (failed_count > 0 and success_count == 0) else 0
        val_findings = len(llm_hypothesis.validated_evidence_ids)
        rej_findings = len(llm_hypothesis.rejected_evidence_ids)

        changed_class = False
        changed_loc = False
        changed_repair = False

        # If inference failed or timed out, retain deterministic findings completely
        if llm_hypothesis.inference_status not in (InferenceStatus.SUCCESS, InferenceStatus.VALIDATION_REJECTED):
            reconciliation_log.append(
                f"LLM inference status '{llm_hypothesis.inference_status.value}' (Reason: {llm_hypothesis.uncertainty_reason}). "
                "Retaining raw deterministic verification reports."
            )
            ai_telemetry = AIContributionTelemetry(
                evaluation_mode="LLM_ASSISTED",
                llm_enabled=True,
                actual_llm_invocation_count=invocations,
                successful_llm_response_count=success_count,
                failed_llm_response_count=failed_count,
                model_identifier=llm_hypothesis.model_identifier,
                model_digest=llm_hypothesis.model_digest,
                inference_latency_ms=llm_hypothesis.inference_duration_ms or 0.0,
                timeout_events=timeout_count,
                fallback_events=fallback_count,
                validated_llm_findings=val_findings,
                rejected_llm_findings=rej_findings,
                llm_changed_classification=False,
                llm_changed_localization=False,
                llm_changed_repair_recommendation=False,
                reconciliation_log=reconciliation_log,
            )
            return reconciled, ai_telemetry, []

        unsupported_claims_gen = len(llm_hypothesis.rejected_evidence_ids)
        unsupported_claims_rej = len(llm_hypothesis.rejected_evidence_ids)
        unsupported_claims_acc = 0
        user_visible_errs = 0

        # Baseline claims accounting: category, line localization, evidence references, root cause, repair
        claims_checked = 1  # Predicted defect category
        if llm_hypothesis.suspected_line is not None:
            claims_checked += 1
        claims_checked += len(llm_hypothesis.supporting_evidence_ids) or (
            len(llm_hypothesis.validated_evidence_ids) + len(llm_hypothesis.rejected_evidence_ids)
        )
        if llm_hypothesis.root_cause_explanation:
            claims_checked += 1
        if llm_hypothesis.repair_recommendation:
            claims_checked += 1

        # Rule 1: Clean code invariance — if zero deterministic defects and zero failed tests, do not invent defects
        if not reconciled:
            if llm_hypothesis.predicted_defect_category not in ("clean_control", "clean"):
                unsupported_claims_gen += 1
                unsupported_claims_rej += 1
                reconciliation_log.append("Clean code control: Suppressed hallucinated defect hypothesis on clean code.")
            if llm_hypothesis.suspected_line is not None:
                unsupported_claims_gen += 1
                unsupported_claims_rej += 1
                reconciliation_log.append(f"Clean code control: Suppressed hallucinated line {llm_hypothesis.suspected_line} on clean code.")
            reconciliation_log.append("Clean code control: Zero deterministic failures. Preserving 0 defect reports.")
            ai_telemetry = AIContributionTelemetry(
                evaluation_mode="LLM_ASSISTED",
                llm_enabled=True,
                actual_llm_invocation_count=invocations,
                successful_llm_response_count=success_count,
                failed_llm_response_count=failed_count,
                model_identifier=llm_hypothesis.model_identifier,
                model_digest=llm_hypothesis.model_digest,
                inference_latency_ms=llm_hypothesis.inference_duration_ms or 0.0,
                timeout_events=timeout_count,
                fallback_events=fallback_count,
                validated_llm_findings=val_findings,
                rejected_llm_findings=rej_findings,
                claims_checked=claims_checked,
                llm_changed_classification=False,
                llm_changed_localization=False,
                llm_changed_repair_recommendation=False,
                unsupported_claims_generated=unsupported_claims_gen,
                unsupported_claims_rejected=unsupported_claims_rej,
                unsupported_claims_accepted=0,
                user_visible_feedback_errors=0,
                prompt_tokens=getattr(llm_hypothesis, "prompt_eval_count", None),
                completion_tokens=getattr(llm_hypothesis, "eval_count", None),
                reconciliation_log=reconciliation_log,
            )
            return reconciled, ai_telemetry, []

        # Iterate over existing deterministic defect reports and apply bounded reconciliation
        machine_guidance: List[Dict[str, Any]] = []

        for defect in reconciled:
            # Rule 2: Confirmed AST Security findings cannot be altered or reclassified by the LLM
            is_confirmed_security = (
                defect.provenance == "AST_STATIC_ANALYSIS"
                or (defect.cwe_id and defect.confidence == "CONFIRMED")
            )

            if is_confirmed_security:
                reconciliation_log.append(
                    f"Defect {defect.defect_id}: Authoritative AST security finding {defect.cwe_id} on line "
                    f"{defect.line_number} is immutable. LLM reclassification forbidden."
                )
                if llm_hypothesis.predicted_defect_category and llm_hypothesis.predicted_defect_category not in ("security_vulnerability", "security"):
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1
                # LLM can still enrich repair suggestion if relevant
                if llm_hypothesis.repair_recommendation and not defect.suggested_fix:
                    defect.suggested_fix = llm_hypothesis.repair_recommendation
                    changed_repair = True
                continue

            # Rule 3: Localization Promotion & Grounding Verification
            # Authoritative lines are strictly unhandled runtime traceback frames in the solution file (CONFIRMED)
            # or exact AST static security findings (CONFIRMED).
            # Heuristic AST source mapping (AST_SOURCE_MAPPING) is a static fallback when stack trace lacks solution frames,
            # and is eligible for promotion ONLY when LLM provides an in-bounds, high-confidence line with validated evidence grounding.
            has_authoritative_line = (
                defect.line_number is not None
                and defect.line_number > 0
                and defect.provenance in ("TRACEBACK_FRAME_ANALYSIS", "AST_STATIC_ANALYSIS")
                and defect.confidence == "CONFIRMED"
            )

            if has_authoritative_line and llm_hypothesis.suspected_line is not None:
                if llm_hypothesis.suspected_line != defect.line_number:
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: Authoritative location (line {defect.line_number}, {defect.provenance}) "
                        f"takes strict precedence over conflicting LLM suggested line {llm_hypothesis.suspected_line}."
                    )
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1
                else:
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: LLM suggested line {llm_hypothesis.suspected_line} "
                        f"corroborates authoritative location line {defect.line_number}."
                    )

            elif not has_authoritative_line and llm_hypothesis.suspected_line is not None:
                # Evidence grounding check: must have at least one validated evidence reference,
                # or have supporting evidence with 0 fabricated/rejected evidence IDs.
                has_grounded_evidence = bool(llm_hypothesis.validated_evidence_ids) or (
                    len(llm_hypothesis.rejected_evidence_ids) == 0 and bool(llm_hypothesis.supporting_evidence_ids)
                )

                if 1 <= llm_hypothesis.suspected_line <= max(1, total_code_lines) and llm_hypothesis.confidence >= 0.7 and has_grounded_evidence:
                    old_line = defect.line_number
                    old_prov = defect.provenance
                    defect.line_number = llm_hypothesis.suspected_line
                    defect.confidence = "HIGH"
                    defect.provenance = "LLM_ASSISTED_LOCALIZATION"
                    changed_loc = True
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: Promoted LLM-assisted line localization "
                        f"from line {old_line} ({old_prov}) to line {llm_hypothesis.suspected_line} "
                        f"(provenance: LLM_ASSISTED_LOCALIZATION, confidence: {llm_hypothesis.confidence}, "
                        f"evidence: {llm_hypothesis.validated_evidence_ids})."
                    )
                elif not (1 <= llm_hypothesis.suspected_line <= max(1, total_code_lines)):
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: LLM suggested out-of-bounds line "
                        f"{llm_hypothesis.suspected_line} (valid range: 1..{total_code_lines}). Rejected."
                    )
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1
                elif llm_hypothesis.confidence < 0.7:
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: LLM suspected line {llm_hypothesis.suspected_line} "
                        f"rejected due to low confidence ({llm_hypothesis.confidence} < 0.7). Retained line {defect.line_number}."
                    )
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1
                else:
                    # Confidence >= 0.7 and in bounds, but lacking grounded empirical evidence
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: LLM suspected line {llm_hypothesis.suspected_line} "
                        f"rejected due to ungrounded evidence (validated_evidence_ids empty or rejected). "
                        f"Retained line {defect.line_number}."
                    )
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1

            # Rule 4: Ambiguous Category Refinement
            # If deterministic category is functional_bug / unknown, and LLM suggests a specific
            # category with confidence >= 0.7 and supporting evidence:
            curr_cat = defect.defect_category or "functional_bug"
            llm_cat = llm_hypothesis.predicted_defect_category

            if curr_cat in ("functional_bug", "unknown") and llm_cat not in ("functional_bug", "unknown", "clean_control"):
                if llm_hypothesis.confidence >= 0.7 and llm_hypothesis.validated_evidence_ids:
                    old_cat = curr_cat
                    defect.defect_category = llm_cat
                    changed_class = True
                    reconciliation_log.append(
                        f"Defect {defect.defect_id}: Refined taxonomy category from '{old_cat}' "
                        f"to '{llm_cat}' (confidence: {llm_hypothesis.confidence}, evidence: {llm_hypothesis.validated_evidence_ids})."
                    )
                else:
                    unsupported_claims_gen += 1
                    unsupported_claims_rej += 1

            # Rule 5: Repair Recommendation and Root Cause Enrichment
            if llm_hypothesis.repair_recommendation:
                defect.suggested_fix = llm_hypothesis.repair_recommendation
                changed_repair = True

            if llm_hypothesis.root_cause_explanation:
                if "[LLM Root Cause]:" not in defect.description:
                    defect.description = f"{defect.description}\n[LLM Root Cause]: {llm_hypothesis.root_cause_explanation}"

            # Append machine-readable guidance item
            machine_guidance.append({
                "defect_id": defect.defect_id,
                "predicted_defect_category": defect.defect_category,
                "suspected_file": defect.file_path or input_data_filename(defect),
                "suspected_line": defect.line_number,
                "root_cause_explanation": llm_hypothesis.root_cause_explanation,
                "repair_recommendation": defect.suggested_fix,
                "confidence": llm_hypothesis.confidence,
                "model_identifier": llm_hypothesis.model_identifier,
                "evidence_references": llm_hypothesis.validated_evidence_ids,
            })

        ai_telemetry = AIContributionTelemetry(
            evaluation_mode="LLM_ASSISTED",
            llm_enabled=True,
            actual_llm_invocation_count=invocations,
            successful_llm_response_count=success_count,
            failed_llm_response_count=failed_count,
            model_identifier=llm_hypothesis.model_identifier,
            model_digest=llm_hypothesis.model_digest,
            inference_latency_ms=llm_hypothesis.inference_duration_ms or 0.0,
            timeout_events=timeout_count,
            fallback_events=fallback_count,
            validated_llm_findings=val_findings,
            rejected_llm_findings=rej_findings,
            claims_checked=claims_checked,
            llm_changed_classification=changed_class,
            llm_changed_localization=changed_loc,
            llm_changed_repair_recommendation=changed_repair,
            unsupported_claims_generated=unsupported_claims_gen,
            unsupported_claims_rejected=unsupported_claims_rej,
            unsupported_claims_accepted=unsupported_claims_acc,
            user_visible_feedback_errors=user_visible_errs,
            prompt_tokens=getattr(llm_hypothesis, "prompt_eval_count", None),
            completion_tokens=getattr(llm_hypothesis, "eval_count", None),
            reconciliation_log=reconciliation_log,
        )

        return reconciled, ai_telemetry, machine_guidance


def input_data_filename(defect: DefectReport) -> str:
    """Helper to extract fallback filename."""
    return defect.file_path or "solution.py"
