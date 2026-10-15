from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.core.logging import logger
from app.schemas.common import TestResultStatus, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.repair import (
    DefectResolutionComparison,
    DefectResolutionDetail,
    OverallResolutionVerdict,
    ResolutionStatus,
    TestResolutionDetail,
)
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse


class DefectResolutionService:
    """
    Deterministic defect resolution comparison between original and corrected verification runs.
    Compares recorded test evidence and defect reports without guessing or fabricating resolutions.
    """

    def compare_runs(
        self,
        original_run: VerificationRunResponse,
        corrected_run: VerificationRunResponse,
    ) -> DefectResolutionComparison:
        """
        Produce a deterministic before-and-after comparison between original and corrected verification runs.
        """
        # 1. Check for infrastructure failures or non-comparable states in the corrected run
        is_inconclusive = False
        inconclusive_notes = []

        if corrected_run.status in [
            VerificationStatus.ERROR,
            VerificationStatus.PENDING,
            VerificationStatus.RUNNING,
        ]:
            is_inconclusive = True
            inconclusive_notes.append(
                f"Corrected verification ended with status '{corrected_run.status.value}', "
                f"precluding conclusive defect resolution determination."
            )

        orig_tests: Dict[str, TestResult] = {
            t.name or t.test_name or t.test_id: t for t in (original_run.test_results or [])
        }
        corr_tests: Dict[str, TestResult] = {
            t.name or t.test_name or t.test_id: t for t in (corrected_run.test_results or [])
        }

        if not orig_tests:
            is_inconclusive = True
            inconclusive_notes.append("Original verification run has no recorded test results.")

        if not corr_tests and not is_inconclusive:
            is_inconclusive = True
            inconclusive_notes.append("Corrected verification run produced no recorded test results.")

        # Check for missing tests in corrected run
        missing_tests = set(orig_tests.keys()) - set(corr_tests.keys())
        if missing_tests:
            is_inconclusive = True
            inconclusive_notes.append(
                f"Corrected run did not execute all original tests. Missing: {sorted(list(missing_tests))}."
            )

        # 2. Granular Test-level comparison
        test_comparisons: List[TestResolutionDetail] = []
        all_test_keys = set(orig_tests.keys()).union(set(corr_tests.keys()))

        for test_key in sorted(all_test_keys):
            orig_t = orig_tests.get(test_key)
            corr_t = corr_tests.get(test_key)

            orig_status_str = orig_t.status.value if orig_t else "NOT_PRESENT"
            corr_status_str = corr_t.status.value if corr_t else "NOT_PRESENT"

            error_msg = corr_t.error_message if corr_t else None

            if not orig_t:
                # Test only present in corrected run
                if corr_t and corr_t.status == TestResultStatus.FAILED:
                    resolution_status = ResolutionStatus.NEW_FAILURE
                    notes = "New test case failed in corrected verification."
                else:
                    resolution_status = ResolutionStatus.RESOLVED
                    notes = "Additional test case passed in corrected verification."
            elif not corr_t:
                # Test present originally but missing in corrected run
                resolution_status = ResolutionStatus.INCONCLUSIVE
                notes = "Test was not executed in corrected run."
            elif is_inconclusive:
                resolution_status = ResolutionStatus.INCONCLUSIVE
                notes = "Inconclusive due to corrected run execution status."
            elif orig_t.status == TestResultStatus.FAILED:
                if corr_t.status == TestResultStatus.PASSED:
                    resolution_status = ResolutionStatus.RESOLVED
                    notes = "Previously failing test now demonstrably passes."
                elif corr_t.status == TestResultStatus.FAILED:
                    resolution_status = ResolutionStatus.STILL_FAILING
                    notes = "Test continues to fail in corrected verification."
                else:
                    resolution_status = ResolutionStatus.INCONCLUSIVE
                    notes = f"Unexpected corrected status: {corr_status_str}"
            elif orig_t.status == TestResultStatus.PASSED:
                if corr_t.status == TestResultStatus.FAILED:
                    resolution_status = ResolutionStatus.NEW_FAILURE
                    notes = "Regression: previously passing test now fails."
                else:
                    resolution_status = ResolutionStatus.RESOLVED
                    notes = "Previously passing test continues to pass."
            else:
                resolution_status = ResolutionStatus.INCONCLUSIVE
                notes = f"Original status was {orig_status_str}."

            test_comparisons.append(
                TestResolutionDetail(
                    test_name=test_key,
                    original_status=orig_status_str,
                    corrected_status=corr_status_str,
                    resolution_status=resolution_status,
                    error_message=error_msg,
                    notes=notes,
                )
            )

        # 3. Defect-level comparison
        defect_comparisons: List[DefectResolutionDetail] = []
        original_defects: List[DefectReport] = original_run.defect_reports or []

        for defect in original_defects:
            failed_test_name = defect.failed_test or defect.title or defect.defect_id
            corr_t = corr_tests.get(failed_test_name)

            if is_inconclusive:
                res_status = ResolutionStatus.INCONCLUSIVE
                def_notes = "Inconclusive: corrected run terminated abnormally or was incomplete."
            elif not corr_t:
                res_status = ResolutionStatus.INCONCLUSIVE
                def_notes = f"Test '{failed_test_name}' was not executed in the corrected run."
            elif corr_t.status == TestResultStatus.PASSED:
                res_status = ResolutionStatus.RESOLVED
                def_notes = f"Defect resolved: '{failed_test_name}' passed in re-verification."
            elif corr_t.status == TestResultStatus.FAILED:
                res_status = ResolutionStatus.STILL_FAILING
                def_notes = f"Defect persists: '{failed_test_name}' still failed."
            else:
                res_status = ResolutionStatus.INCONCLUSIVE
                def_notes = f"Test status '{corr_t.status.value}' cannot confirm resolution."

            defect_comparisons.append(
                DefectResolutionDetail(
                    defect_id=defect.defect_id,
                    title=defect.title,
                    failed_test=failed_test_name,
                    resolution_status=res_status,
                    original_assertion=defect.assertion_or_exception,
                    notes=def_notes,
                )
            )

        # 4. Metric counts
        resolved_defects = sum(
            1 for d in defect_comparisons if d.resolution_status == ResolutionStatus.RESOLVED
        )
        remaining_defects = sum(
            1 for d in defect_comparisons if d.resolution_status == ResolutionStatus.STILL_FAILING
        )
        new_failures = sum(
            1 for t in test_comparisons if t.resolution_status == ResolutionStatus.NEW_FAILURE
        )

        # If there were no formal DefectReports recorded originally, fall back to test-level counts
        if not original_defects and orig_tests:
            orig_failing_tests = [
                t for t in test_comparisons if t.original_status == TestResultStatus.FAILED.value
            ]
            total_orig_count = len(orig_failing_tests)
            resolved_defects = sum(
                1 for t in orig_failing_tests if t.resolution_status == ResolutionStatus.RESOLVED
            )
            remaining_defects = sum(
                1 for t in orig_failing_tests if t.resolution_status == ResolutionStatus.STILL_FAILING
            )
        else:
            total_orig_count = len(original_defects)

        if total_orig_count > 0:
            resolution_rate = round((resolved_defects / total_orig_count) * 100.0, 1)
        else:
            resolution_rate = 100.0 if not new_failures and not is_inconclusive else 0.0

        # 5. Overall Resolution Verdict
        if is_inconclusive:
            verdict = OverallResolutionVerdict.INCONCLUSIVE
        elif new_failures > 0:
            verdict = OverallResolutionVerdict.REGRESSION_INTRODUCED
        elif total_orig_count > 0 and remaining_defects == 0 and resolved_defects == total_orig_count:
            verdict = OverallResolutionVerdict.FULLY_RESOLVED
        elif resolved_defects > 0 and remaining_defects > 0:
            verdict = OverallResolutionVerdict.PARTIALLY_RESOLVED
        elif resolved_defects == 0 and remaining_defects > 0:
            verdict = OverallResolutionVerdict.UNRESOLVED
        elif total_orig_count == 0 and not new_failures:
            verdict = OverallResolutionVerdict.FULLY_RESOLVED
        else:
            verdict = OverallResolutionVerdict.INCONCLUSIVE

        overall_notes = "; ".join(inconclusive_notes) if inconclusive_notes else None

        return DefectResolutionComparison(
            original_run_id=original_run.id,
            corrected_run_id=corrected_run.id,
            original_status=original_run.status.value,
            corrected_status=corrected_run.status.value,
            verdict=verdict,
            original_defects_count=total_orig_count,
            resolved_defects_count=resolved_defects,
            remaining_defects_count=remaining_defects,
            new_defects_count=new_failures,
            resolution_rate=resolution_rate,
            test_comparisons=test_comparisons,
            defect_comparisons=defect_comparisons,
            notes=overall_notes,
        )
