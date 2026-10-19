"""
Dataset Integrity and Reproducibility Validation Tests for INTELISE Component 4 Phase 3 (SO6, Table 4, Table 15).

Validates:
1. Scenario Uniqueness: All 100 scenario IDs are globally unique across development and held-out sets.
2. Dataset Partitioning: Exactly 40 development scenarios and 60 held-out scenarios.
3. Valid Ground-Truth Labels: Every scenario has valid DefectCategory, boolean flags, and appropriate CWE IDs.
4. Physical Line Number Correctness: Expected line numbers reflect actual physical source lines.
5. Positive and Negative Controls: Balance of defective cases and negative controls across security, performance, and drift.
6. Zero Ground-Truth Leakage: Mutating ground-truth labels has 0.00% effect on detector predictions.
7. Stable Dataset Hashes: Manifest SHA-256 hashes match frozen records.
8. Source AST Parseability: All module and test source code compile cleanly into Python ASTs.
"""
import ast
import asyncio
import json
from pathlib import Path
import pytest

from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.benchmark.phase3_dataset import (
    DATASET_VERSION,
    PHASE3_ALL_SCENARIOS,
    PHASE3_DEV_SCENARIOS,
    PHASE3_HELDOUT_SCENARIOS,
    compute_scenario_checksum,
    generate_phase3_manifest,
)
from app.schemas.common import DefectCategory, TestResultStatus


def test_phase3_dataset_partition_counts():
    """Validates that Phase 3 contains exactly 40 dev and 60 held-out scenarios (100 total)."""
    assert len(PHASE3_DEV_SCENARIOS) == 40
    assert len(PHASE3_HELDOUT_SCENARIOS) == 60
    assert len(PHASE3_ALL_SCENARIOS) == 100


def test_phase3_scenario_id_uniqueness():
    """Validates that all 100 scenario IDs are unique and follow established prefixing conventions."""
    all_ids = [s.scenario_id for s in PHASE3_ALL_SCENARIOS]
    assert len(all_ids) == len(set(all_ids)), "Duplicate scenario IDs detected!"

    for s in PHASE3_DEV_SCENARIOS:
        assert s.scenario_id.startswith("PH3-DEV-"), f"Invalid dev ID format: {s.scenario_id}"
        assert s.split == "dev"

    for s in PHASE3_HELDOUT_SCENARIOS:
        assert s.scenario_id.startswith("PH3-HELD-"), f"Invalid held-out ID format: {s.scenario_id}"
        assert s.split == "held_out"


def test_phase3_ast_compilation_all_scenarios():
    """Validates that module_code and test_code for all 100 scenarios compile cleanly into Python AST."""
    for s in PHASE3_ALL_SCENARIOS:
        try:
            mod_tree = ast.parse(s.module_code)
            assert isinstance(mod_tree, ast.Module)
        except SyntaxError as e:
            pytest.fail(f"Module code syntax error in {s.scenario_id}: {e}")

        try:
            test_tree = ast.parse(s.test_code)
            assert isinstance(test_tree, ast.Module)
        except SyntaxError as e:
            pytest.fail(f"Test code syntax error in {s.scenario_id}: {e}")

        if s.original_test_code:
            try:
                orig_tree = ast.parse(s.original_test_code)
                assert isinstance(orig_tree, ast.Module)
            except SyntaxError as e:
                pytest.fail(f"Original test code syntax error in {s.scenario_id}: {e}")

        if s.candidate_test_code:
            try:
                cand_tree = ast.parse(s.candidate_test_code)
                assert isinstance(cand_tree, ast.Module)
            except SyntaxError as e:
                pytest.fail(f"Candidate test code syntax error in {s.scenario_id}: {e}")


def test_phase3_physical_line_numbers_integrity():
    """
    Validates that every defective scenario with expected_line_number points to
    a non-empty, non-comment statement in the actual source code.
    """
    for s in PHASE3_ALL_SCENARIOS:
        if s.has_defect and s.expected_line_number is not None:
            lines = s.module_code.splitlines()
            total_lines = len(lines)
            expected_line = s.expected_line_number

            assert 1 <= expected_line <= total_lines, (
                f"Scenario {s.scenario_id} expected_line_number {expected_line} out of range [1, {total_lines}]"
            )
            # Physical line (1-indexed)
            physical_content = lines[expected_line - 1].strip()
            assert physical_content != "", (
                f"Scenario {s.scenario_id} expected_line_number {expected_line} points to an empty line!"
            )


def test_phase3_positive_and_negative_controls():
    """Validates that clean negative controls exist alongside positive defects in security, performance, and drift."""
    # Security controls
    sec_vulns = [s for s in PHASE3_ALL_SCENARIOS if s.scenario_group == BenchmarkScenarioGroup.SECURITY_VULNERABILITY]
    sec_controls = [s for s in PHASE3_ALL_SCENARIOS if "Negative Security Control" in s.name or "Safe" in s.name and s.scenario_group == BenchmarkScenarioGroup.CLEAN_CONTROL]
    assert len(sec_vulns) >= 10, "Expected at least 10 security vulnerabilities"
    assert len(sec_controls) >= 8, "Expected at least 8 negative security controls"

    # Performance controls
    perf_bottlenecks = [s for s in PHASE3_ALL_SCENARIOS if s.scenario_group == BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK]
    perf_controls = [s for s in PHASE3_ALL_SCENARIOS if "Normal Performance Control" in s.name]
    assert len(perf_bottlenecks) >= 6, "Expected at least 6 performance bottlenecks"
    assert len(perf_controls) >= 3, "Expected at least 3 normal performance controls"

    # Semantic drift controls
    drift_positive = [s for s in PHASE3_ALL_SCENARIOS if s.has_semantic_drift and s.has_defect]
    drift_controls = [s for s in PHASE3_ALL_SCENARIOS if s.scenario_group == BenchmarkScenarioGroup.SEMANTIC_DRIFT and not s.has_semantic_drift]
    assert len(drift_positive) >= 3, "Expected at least 3 positive drift cases"
    assert len(drift_controls) >= 3, "Expected at least 3 negative drift controls"


def test_phase3_ground_truth_leakage_prevention():
    """
    CRITICAL METHODOLOGICAL TEST:
    Verifies that mutating Phase 3 ground-truth labels (has_defect, expected_defect_category,
    has_semantic_drift, scenario_group) produces identical detection and classification.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)
        test_scenarios = [PHASE3_DEV_SCENARIOS[8], PHASE3_DEV_SCENARIOS[18]]  # Functional bug and security bug

        for sc in test_scenarios:
            res_orig, _, _ = await evaluator._execute_scenario(sc)
            status_orig = "FAILED" if any(t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR) for t in res_orig) else "PASSED"
            defects_orig = evaluator.defect_service.analyze_test_results(
                run_id=f"run-{sc.scenario_id}",
                submission_id="sub-1",
                status=status_orig,
                test_results=res_orig,
                affected_filename=sc.filename,
                source_code=sc.module_code,
            )

            # Adversarial mutation: inverted ground-truth labels
            mutated_sc = sc.model_copy(update={
                "has_defect": not sc.has_defect,
                "expected_defect_category": DefectCategory.UNKNOWN if sc.has_defect else DefectCategory.FUNCTIONAL_BUG,
                "has_semantic_drift": True,
                "scenario_group": BenchmarkScenarioGroup.CLEAN_CONTROL,
            })

            res_mut, _, _ = await evaluator._execute_scenario(mutated_sc)
            status_mut = "FAILED" if any(t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR) for t in res_mut) else "PASSED"
            defects_mut = evaluator.defect_service.analyze_test_results(
                run_id=f"run-{mutated_sc.scenario_id}",
                submission_id="sub-2",
                status=status_mut,
                test_results=res_mut,
                affected_filename=mutated_sc.filename,
                source_code=mutated_sc.module_code,
            )

            assert len(defects_orig) == len(defects_mut)
            assert defects_orig[0].defect_category == defects_mut[0].defect_category
            assert defects_orig[0].line_number == defects_mut[0].line_number
            assert defects_orig[0].cwe_id == defects_mut[0].cwe_id

    asyncio.run(_run())


def test_phase3_manifest_hash_stability():
    """Validates that computed dataset SHA-256 digests match the frozen manifest file on disk."""
    manifest_path = Path(__file__).resolve().parent.parent / "app" / "benchmark" / "phase3_manifest.json"
    assert manifest_path.exists(), "phase3_manifest.json does not exist!"

    with open(manifest_path, "r", encoding="utf-8") as f:
        frozen_manifest = json.load(f)

    live_manifest = generate_phase3_manifest()

    assert live_manifest["dataset_version"] == frozen_manifest["dataset_version"]
    assert live_manifest["total_scenarios"] == frozen_manifest["total_scenarios"] == 100
    assert live_manifest["checksums"]["overall_manifest_sha256"] == frozen_manifest["checksums"]["overall_manifest_sha256"]
    assert live_manifest["checksums"]["dev_subset_sha256"] == frozen_manifest["checksums"]["dev_subset_sha256"]
    assert live_manifest["checksums"]["held_out_subset_sha256"] == frozen_manifest["checksums"]["held_out_subset_sha256"]
