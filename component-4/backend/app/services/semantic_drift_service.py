import ast
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.logging import logger
from app.schemas.common import DefectSeverity
from app.schemas.research_reports import DriftDetail, SemanticDriftReport


class SemanticDriftService:
    """
    Semantic-Drift & Test Weakening Detection Service (Proposal Section 3.7.6, FR07, NFR01).
    Detects assertion weakening, silent test deletion, or scope reduction across test revisions
    to prevent false convergence.
    """

    def analyze_test_suite_drift(
        self,
        original_test_code: str,
        candidate_test_code: str,
        verification_run_id: str = "run-unknown",
    ) -> SemanticDriftReport:
        """
        Compares candidate test suite against authoritative original suite using AST inspection.
        Returns a SemanticDriftReport indicating whether test weakening or scope reduction occurred.
        """
        report_id = f"drift-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # 1. Parse ASTs
        orig_tree = self._safe_parse(original_test_code)
        cand_tree = self._safe_parse(candidate_test_code)

        if not orig_tree or not cand_tree:
            # Syntax failure in test code constitutes a drift violation
            return SemanticDriftReport(
                report_id=report_id,
                verification_run_id=verification_run_id,
                has_drift=True,
                drift_types=["SYNTAX_PARSE_FAILURE"],
                details=[
                    DriftDetail(
                        test_name="<suite_parser>",
                        drift_type="SYNTAX_PARSE_FAILURE",
                        severity=DefectSeverity.CRITICAL,
                        description="Test suite failed AST syntax parsing; cannot verify semantic preservation.",
                    )
                ],
                original_test_count=0,
                candidate_test_count=0,
                original_assertion_count=0,
                candidate_assertion_count=0,
                requires_human_validation=True,
                analyzed_at=now,
            )

        # 2. Extract test functions and assertions
        orig_tests = self._extract_test_functions(orig_tree)
        cand_tests = self._extract_test_functions(cand_tree)

        orig_test_count = len(orig_tests)
        cand_test_count = len(cand_tests)
        orig_assert_count = sum(len(a) for a in orig_tests.values())
        cand_assert_count = sum(len(a) for a in cand_tests.values())

        drift_details: List[DriftDetail] = []
        drift_types_set: Set[str] = set()

        # 3. Check for Deleted Tests (FR07)
        for t_name in orig_tests:
            if t_name not in cand_tests:
                drift_types_set.add("TEST_DELETED")
                drift_details.append(
                    DriftDetail(
                        test_name=t_name,
                        drift_type="TEST_DELETED",
                        severity=DefectSeverity.CRITICAL,
                        description=f"Authorized test case '{t_name}' was removed from the test suite.",
                    )
                )

        # 4. Check for Weakened Assertions or Reduced Assertion Counts (FR07, NFR01)
        for t_name, orig_asserts in orig_tests.items():
            if t_name in cand_tests:
                cand_asserts = cand_tests[t_name]

                # Fewer assertions in the candidate test function
                if len(cand_asserts) < len(orig_asserts):
                    drift_types_set.add("ASSERTION_WEAKENED")
                    drift_details.append(
                        DriftDetail(
                            test_name=t_name,
                            drift_type="ASSERTION_WEAKENED",
                            severity=DefectSeverity.HIGH,
                            description=(
                                f"Test '{t_name}' reduced assertion count from {len(orig_asserts)} "
                                f"to {len(cand_asserts)}."
                            ),
                        )
                    )

                # Check for trivially true assertions: "assert True" or "assert 1"
                for c_node, c_expr, lineno in cand_asserts:
                    if self._is_trivially_true_assertion(c_node):
                        drift_types_set.add("ASSERTION_WEAKENED")
                        drift_details.append(
                            DriftDetail(
                                test_name=t_name,
                                drift_type="ASSERTION_WEAKENED",
                                severity=DefectSeverity.CRITICAL,
                                description=(
                                    f"Test '{t_name}' contains a trivially satisfied assertion '{c_expr}' "
                                    "masking potential defect."
                                ),
                                candidate_expression=c_expr,
                                line_number=lineno,
                            )
                        )

        # 5. Check for Overall Suite Size Reduction
        if cand_test_count < orig_test_count or cand_assert_count < orig_assert_count:
            drift_types_set.add("TEST_SCOPE_REDUCTION")

        has_drift = len(drift_details) > 0 or len(drift_types_set) > 0
        requires_human = has_drift

        if has_drift:
            logger.warning(
                "Semantic drift detected for run %s: %d drift detail(s), types=%s",
                verification_run_id,
                len(drift_details),
                list(drift_types_set),
            )

        return SemanticDriftReport(
            report_id=report_id,
            verification_run_id=verification_run_id,
            has_drift=has_drift,
            drift_types=sorted(list(drift_types_set)),
            details=drift_details,
            original_test_count=orig_test_count,
            candidate_test_count=cand_test_count,
            original_assertion_count=orig_assert_count,
            candidate_assertion_count=cand_assert_count,
            requires_human_validation=requires_human,
            analyzed_at=now,
        )

    def _safe_parse(self, code: str) -> Optional[ast.AST]:
        try:
            return ast.parse(code)
        except Exception:
            return None

    def _extract_test_functions(self, tree: ast.AST) -> Dict[str, List[Tuple[ast.Assert, str, int]]]:
        """Maps each test function name to its list of (AssertNode, source_expr, lineno)."""
        test_map = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                asserts = []
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        expr_str = ast.unparse(sub.test) if hasattr(ast, "unparse") else "assert"
                        asserts.append((sub, expr_str, getattr(sub, "lineno", 0)))
                test_map[node.name] = asserts
        return test_map

    def _is_trivially_true_assertion(self, assert_node: ast.Assert) -> bool:
        """Detects assertions that are trivially satisfied (e.g. assert True, assert 1)."""
        test_expr = assert_node.test
        if isinstance(test_expr, ast.Constant):
            if test_expr.value is True or test_expr.value == 1:
                return True
        return False
