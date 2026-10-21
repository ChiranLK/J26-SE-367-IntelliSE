"""
Common structures and oracle execution utilities for Phase 3C.2 dataset generation.
"""
import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ScenarioSpec:
    """Internal specification for a single benchmark scenario during construction."""
    scenario_index: int  # 1 to 50 within family
    name: str
    difficulty: str  # "easy", "medium", "hard"
    category: str    # "functional_bug", "security_vulnerability", "performance_bottleneck", "regression", "integration_defect", "semantic_drift", "non_convergent_by_design", "clean_control"
    has_defect: bool
    expected_cwe: Optional[str]
    expected_line: Optional[int]
    mutation_op: Optional[str]
    clean_code: str
    mutated_code: str
    test_code: str
    expected_behavior: str
    observed_behavior: str
    oracle_code: str  # Independent verification test suite executed against code
    requirement_ids: List[str] = field(default_factory=lambda: ["REQ-001"])
    requested_test_types: List[str] = field(default_factory=lambda: ["unit"])
    original_test_code: Optional[str] = None
    candidate_test_code: Optional[str] = None
    repair_candidate_patches: Optional[List[str]] = None
    is_repair_loop_scenario: bool = False


class ScenarioOracleRunner:
    """
    Executes independent ground-truth verification oracles.
    Guarantees:
    1. Clean code passes the oracle test suite.
    2. Defective code fails the oracle test suite (attributable to mutation).
    3. Clean controls pass 100% of functional and boundary checks.
    4. Code and test suites parse into valid Python AST.
    """

    @staticmethod
    def validate_ast(code: str, label: str) -> Tuple[bool, Optional[str]]:
        try:
            tree = ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError in {label}: {e}"

    @classmethod
    def execute_oracle(cls, spec: ScenarioSpec, family_id: str, scenario_id: str) -> Dict[str, Any]:
        """
        Executes independent verification on the scenario.
        Returns detailed validation outcome and execution evidence.
        """
        evidence: Dict[str, Any] = {
            "family_id": family_id,
            "scenario_id": scenario_id,
            "clean_ast_valid": False,
            "mutated_ast_valid": False,
            "test_ast_valid": False,
            "clean_execution_passed": False,
            "mutated_execution_failed": False,
            "execution_time_ms": 0.0,
            "error_detail": None,
        }

        start_time = time.perf_counter()

        # 1. AST Validation
        ok, err = cls.validate_ast(spec.clean_code, "clean_code")
        if not ok:
            evidence["error_detail"] = err
            return {"status": "QUARANTINED", "evidence": evidence}
        evidence["clean_ast_valid"] = True

        ok, err = cls.validate_ast(spec.mutated_code, "mutated_code")
        if not ok:
            evidence["error_detail"] = err
            return {"status": "QUARANTINED", "evidence": evidence}
        evidence["mutated_ast_valid"] = True

        ok, err = cls.validate_ast(spec.test_code, "test_code")
        if not ok:
            evidence["error_detail"] = err
            return {"status": "QUARANTINED", "evidence": evidence}
        evidence["test_ast_valid"] = True

        import linecache

        # 2. Clean Code Execution against Oracle
        clean_fn = f"<scenario_{scenario_id}_clean>"
        linecache.cache[clean_fn] = (
            len(spec.clean_code),
            None,
            [line + "\n" for line in spec.clean_code.splitlines()],
            clean_fn
        )
        clean_ns: Dict[str, Any] = {"__file__": clean_fn}
        try:
            co = compile(spec.clean_code, clean_fn, "exec")
            exec(co, clean_ns)
            exec(spec.oracle_code, clean_ns)
            if "run_oracle" in clean_ns:
                clean_ns["run_oracle"]()
            evidence["clean_execution_passed"] = True
        except Exception as e:
            evidence["error_detail"] = f"Clean code oracle failed: {type(e).__name__}: {e}"
            return {"status": "QUARANTINED", "evidence": evidence}

        # 3. Defective Code Execution against Oracle (or Clean Control negative checks)
        if spec.has_defect:
            mut_fn = f"<scenario_{scenario_id}_mutated>"
            linecache.cache[mut_fn] = (
                len(spec.mutated_code),
                None,
                [line + "\n" for line in spec.mutated_code.splitlines()],
                mut_fn
            )
            mut_ns: Dict[str, Any] = {"__file__": mut_fn}
            try:
                co_mut = compile(spec.mutated_code, mut_fn, "exec")
                exec(co_mut, mut_ns)
                exec(spec.oracle_code, mut_ns)
                if "run_oracle" in mut_ns:
                    mut_ns["run_oracle"]()
                # If we get here, the mutated code passed the oracle -> Oracle FAILED to detect defect!
                evidence["error_detail"] = "Mutated code unexpectedly passed the independent oracle!"
                return {"status": "QUARANTINED", "evidence": evidence}
            except Exception as e:
                # Expected failure on mutated code
                evidence["mutated_execution_failed"] = True
                evidence["mutated_failure_type"] = type(e).__name__
                evidence["mutated_failure_msg"] = str(e)
        else:
            # Clean control - mutated_code should be identical or clean variant
            evidence["mutated_execution_failed"] = False

        evidence["execution_time_ms"] = round((time.perf_counter() - start_time) * 1000.0, 3)
        return {"status": "PASSED", "evidence": evidence}
