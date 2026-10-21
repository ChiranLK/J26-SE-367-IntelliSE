"""
INTELISE Component 4 — Phase 3C.2: Automated Dataset Integrity Test Suite.

Validates the 17 mandatory benchmark integrity criteria for the large-scale
500-scenario dataset (400 defects + 100 clean controls):
1. Unique scenario identifiers.
2. Unique defect identifiers.
3. Source checksum integrity.
4. Oracle independence and reproducibility.
5. Clean versus defective labeling.
6. Partition isolation (Dev 50%, Val 20%, Held-out 30%).
7. Template-family leakage prevention.
8. Near-duplicate detection.
9. Missing ground truth detection.
10. Missing validation evidence detection.
11. Invalid mutations (AST syntax validity).
12. Unstable performance measurements.
13. Missing dependencies (standard library isolation).
14. Unsupported categories audit.
15. Hidden-label leakage check on evaluation inputs.
16. Frozen held-out immutability.
17. Historical benchmark preservation (Phase 3A and 3C.1 pilot).
"""
import ast
import hashlib
import json
from pathlib import Path
import pytest

from app.benchmark.phase3c2_dataset import (
    Phase3C2DatasetLoader,
    Phase3C2EvaluationInput,
    Phase3C2SealedGroundTruth,
)


@pytest.fixture(scope="module")
def benchmark_dir() -> Path:
    base = Path(__file__).resolve().parent.parent.parent / "benchmark" / "phase3c2"
    assert base.exists(), f"Benchmark directory {base} does not exist"
    return base


@pytest.fixture(scope="module")
def dataset_loader(benchmark_dir: Path) -> Phase3C2DatasetLoader:
    return Phase3C2DatasetLoader(benchmark_dir=benchmark_dir)


@pytest.fixture(scope="module")
def manifest(dataset_loader: Phase3C2DatasetLoader):
    return dataset_loader.load_manifest()


@pytest.fixture(scope="module")
def eval_inputs(dataset_loader: Phase3C2DatasetLoader):
    return dataset_loader.load_evaluation_inputs()


@pytest.fixture(scope="module")
def ground_truths(dataset_loader: Phase3C2DatasetLoader):
    return dataset_loader.load_sealed_ground_truth()


@pytest.fixture(scope="module")
def checksums_data(benchmark_dir: Path):
    chk_file = benchmark_dir / "dataset_checksums.json"
    with open(chk_file, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------------------------------------------------------
# Check 1: Unique Scenario Identifiers
# -----------------------------------------------------------------------------
def test_01_scenario_identifiers_uniqueness(eval_inputs, ground_truths):
    """Scenario identifiers must be exactly 500 unique IDs matching format P3C2-XXX."""
    assert len(eval_inputs) == 500, f"Expected 500 evaluation inputs, got {len(eval_inputs)}"
    assert len(ground_truths) == 500, f"Expected 500 ground truth records, got {len(ground_truths)}"

    input_ids = [inp.scenario_id for inp in eval_inputs]
    gt_ids = [gt.scenario_id for gt in ground_truths]

    assert len(set(input_ids)) == 500, "Duplicate scenario_id detected in evaluation inputs"
    assert len(set(gt_ids)) == 500, "Duplicate scenario_id detected in sealed ground truth"
    assert input_ids == gt_ids, "Evaluation inputs scenario_ids must match sealed ground truth 1:1"

    expected_ids = {f"P3C2-{i:03d}" for i in range(1, 501)}
    assert set(input_ids) == expected_ids, "Scenario IDs must follow P3C2-001 through P3C2-500"


# -----------------------------------------------------------------------------
# Check 2: Unique Defect Identifiers
# -----------------------------------------------------------------------------
def test_02_defect_identifiers_uniqueness(ground_truths):
    """Defect identifiers must be exactly 400 unique IDs for defects, and None for clean controls."""
    defect_ids = [gt.defect_id for gt in ground_truths if gt.has_defect]
    clean_defect_ids = [gt.defect_id for gt in ground_truths if not gt.has_defect]

    assert len(defect_ids) == 400, f"Expected 400 defective scenarios, found {len(defect_ids)}"
    assert len(set(defect_ids)) == 400, "Duplicate defect_id found among defective scenarios"
    assert all(d.startswith("DEF-P3C2-") for d in defect_ids), "Defect IDs must follow DEF-P3C2-XXX format"

    assert len(clean_defect_ids) == 100, f"Expected 100 clean controls, found {len(clean_defect_ids)}"
    assert all(d is None for d in clean_defect_ids), "Clean controls must not have invented defect IDs (must be None)"


# -----------------------------------------------------------------------------
# Check 3: Source Checksum Integrity
# -----------------------------------------------------------------------------
def test_03_source_checksum_integrity(dataset_loader, benchmark_dir, checksums_data):
    """File-level SHA-256 and source code checksums must match recorded values."""
    integrity = dataset_loader.verify_integrity()
    assert integrity["valid"] is True, f"Integrity check failed: {integrity}"
    assert integrity["mismatches"] == [], f"Checksum mismatches found: {integrity['mismatches']}"

    # Also verify that every file in checksums_data matches filesystem content
    for filename, recorded_sha in checksums_data["files"].items():
        file_path = benchmark_dir / filename
        assert file_path.exists(), f"Tracked benchmark file {filename} missing"
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        assert hasher.hexdigest() == recorded_sha, f"SHA-256 mismatch for {filename}"


# -----------------------------------------------------------------------------
# Check 4: Oracle Independence and Reproducibility
# -----------------------------------------------------------------------------
def test_04_oracle_independence(ground_truths, benchmark_dir):
    """Oracles must be independently defined and executed without relying on Component 4 AST rules."""
    report_file = benchmark_dir / "oracle_validation_report.json"
    assert report_file.exists(), "Oracle validation report missing"
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["total_scenarios_checked"] == 500
    assert report["total_passed"] == 500
    assert report["total_quarantined"] == 0

    for gt in ground_truths:
        assert gt.validation_result == "PASSED"
        assert gt.oracle_id.startswith("ORACLE-P3C2-")
        assert len(gt.expected_behavior) > 0
        assert len(gt.observed_defective_behavior) > 0


# -----------------------------------------------------------------------------
# Check 5: Clean Versus Defective Labeling
# -----------------------------------------------------------------------------
def test_05_clean_versus_defective_labeling(ground_truths):
    """Strictly distinguish clean controls from defective scenarios."""
    clean_count = 0
    defect_count = 0

    for gt in ground_truths:
        if not gt.has_defect:
            clean_count += 1
            assert gt.defect_category == "clean_control"
            assert gt.defect_id is None
            assert gt.expected_cwe_id is None
            assert gt.expected_line_number is None
            assert gt.mutation_operator is None
            assert gt.original_clean_source == gt.mutated_source
        else:
            defect_count += 1
            assert gt.defect_category != "clean_control"
            assert gt.defect_id is not None
            assert gt.expected_line_number is not None and gt.expected_line_number >= 1
            assert gt.mutation_operator is not None

    assert clean_count == 100, f"Expected 100 clean controls, got {clean_count}"
    assert defect_count == 400, f"Expected 400 defective scenarios, got {defect_count}"


# -----------------------------------------------------------------------------
# Check 6: Partition Isolation
# -----------------------------------------------------------------------------
def test_06_partition_isolation(ground_truths, manifest):
    """Verify Dev (50%), Val (20%), Held-out (30%) split proportions and zero scenario ID overlap."""
    partitions = manifest["partitions"]
    assert partitions["dev"]["count"] == 250
    assert partitions["dev"]["percentage"] == 50.0

    assert partitions["val"]["count"] == 100
    assert partitions["val"]["percentage"] == 20.0

    assert partitions["held_out"]["count"] == 150
    assert partitions["held_out"]["percentage"] == 30.0

    dev_ids = set(partitions["dev"]["scenario_ids"])
    val_ids = set(partitions["val"]["scenario_ids"])
    held_ids = set(partitions["held_out"]["scenario_ids"])

    assert len(dev_ids.intersection(val_ids)) == 0, "Scenario overlap between Dev and Val"
    assert len(dev_ids.intersection(held_ids)) == 0, "Scenario overlap between Dev and HeldOut"
    assert len(val_ids.intersection(held_ids)) == 0, "Scenario overlap between Val and HeldOut"
    assert len(dev_ids | val_ids | held_ids) == 500


# -----------------------------------------------------------------------------
# Check 7: Template-Family Leakage Prevention
# -----------------------------------------------------------------------------
def test_07_template_family_leakage_prevention(ground_truths, manifest):
    """Source-project families must be strictly isolated at partition level with zero cross-leakage."""
    partitions = manifest["partitions"]
    dev_families = set(partitions["dev"]["families"])
    val_families = set(partitions["val"]["families"])
    held_families = set(partitions["held_out"]["families"])

    assert len(dev_families.intersection(val_families)) == 0, "Family leakage between Dev and Val"
    assert len(dev_families.intersection(held_families)) == 0, "Family leakage between Dev and HeldOut"
    assert len(val_families.intersection(held_families)) == 0, "Family leakage between Val and HeldOut"

    expected_dev = {"FAM-01-BOOKING", "FAM-02-INVENTORY", "FAM-03-PAYMENT", "FAM-04-AUTH", "FAM-05-CONTENT"}
    expected_val = {"FAM-06-API", "FAM-07-REPORT"}
    expected_held = {"FAM-08-SCHEDULE", "FAM-09-PIPELINE", "FAM-10-CACHE"}

    assert dev_families == expected_dev
    assert val_families == expected_val
    assert held_families == expected_held


# -----------------------------------------------------------------------------
# Check 8: Near-Duplicate Detection
# -----------------------------------------------------------------------------
def test_08_near_duplicate_detection(ground_truths):
    """Mutated programs must be unique across all 400 defective scenarios (no copy-pasting)."""
    mutated_sources = [gt.mutated_source for gt in ground_truths if gt.has_defect]
    assert len(mutated_sources) == 400
    # Every mutated program string must be distinct
    unique_mutated = set(mutated_sources)
    assert len(unique_mutated) == 400, f"Detected duplicate mutated programs: {400 - len(unique_mutated)} duplicates"


# -----------------------------------------------------------------------------
# Check 9: Missing Ground Truth Detection
# -----------------------------------------------------------------------------
def test_09_missing_ground_truth(ground_truths):
    """All required ground truth metadata must be non-null and valid for every defective scenario."""
    for gt in ground_truths:
        if gt.has_defect:
            assert gt.expected_line_number is not None and gt.expected_line_number > 0
            assert gt.mutation_operator is not None and len(gt.mutation_operator) > 0
            assert gt.expected_behavior is not None and len(gt.expected_behavior) > 0
            assert gt.observed_defective_behavior is not None and len(gt.observed_defective_behavior) > 0
            assert gt.difficulty in {"easy", "medium", "hard"}
            assert gt.family_id.startswith("FAM-")


# -----------------------------------------------------------------------------
# Check 10: Missing Validation Evidence Detection
# -----------------------------------------------------------------------------
def test_10_missing_validation_evidence(ground_truths):
    """Every scenario must include complete execution evidence from the oracle run."""
    for gt in ground_truths:
        evidence = gt.validation_evidence
        assert isinstance(evidence, dict)
        assert evidence.get("clean_ast_valid") is True, f"Clean AST invalid for {gt.scenario_id}"
        assert evidence.get("mutated_ast_valid") is True, f"Mutated AST invalid for {gt.scenario_id}"
        assert evidence.get("test_ast_valid") is True, f"Test AST invalid for {gt.scenario_id}"
        assert evidence.get("clean_execution_passed") is True, f"Clean execution failed for {gt.scenario_id}"
        if gt.has_defect:
            assert evidence.get("mutated_execution_failed") is True, f"Mutated execution did not fail for {gt.scenario_id}"
        else:
            assert evidence.get("mutated_execution_failed") is False, f"Clean control falsely failed for {gt.scenario_id}"


# -----------------------------------------------------------------------------
# Check 11: Invalid Mutations (AST Syntax Validity)
# -----------------------------------------------------------------------------
def test_11_invalid_mutations_ast_syntax(ground_truths, eval_inputs):
    """All 500 clean codes, 500 mutated codes, and 500 test codes must parse into valid Python AST."""
    for gt in ground_truths:
        try:
            ast.parse(gt.original_clean_source)
        except SyntaxError as e:
            pytest.fail(f"Clean source for {gt.scenario_id} has invalid Python syntax: {e}")

        try:
            ast.parse(gt.mutated_source)
        except SyntaxError as e:
            pytest.fail(f"Mutated source for {gt.scenario_id} has invalid Python syntax: {e}")

    for inp in eval_inputs:
        try:
            ast.parse(inp.module_code)
        except SyntaxError as e:
            pytest.fail(f"Evaluation input module code for {inp.scenario_id} has invalid Python syntax: {e}")

        try:
            ast.parse(inp.test_code)
        except SyntaxError as e:
            pytest.fail(f"Evaluation input test code for {inp.scenario_id} has invalid Python syntax: {e}")


# -----------------------------------------------------------------------------
# Check 12: Unstable Performance Measurements
# -----------------------------------------------------------------------------
def test_12_unstable_performance_measurements(ground_truths):
    """Performance bottleneck scenarios must execute reliably under 1.0 second per oracle run."""
    perf_scenarios = [gt for gt in ground_truths if gt.defect_category == "performance_bottleneck"]
    assert len(perf_scenarios) == 50, f"Expected 50 performance bottlenecks, got {len(perf_scenarios)}"

    for gt in perf_scenarios:
        exec_time = gt.validation_evidence.get("execution_time_ms", 0)
        assert exec_time < 1000.0, f"Unstable or slow execution ({exec_time}ms) for performance scenario {gt.scenario_id}"


# -----------------------------------------------------------------------------
# Check 13: Missing Dependencies (Standard Library Isolation)
# -----------------------------------------------------------------------------
def test_13_missing_dependencies_isolation(eval_inputs):
    """All scenarios must be executable purely using Python standard library (no external packages)."""
    allowed_builtins_and_stdlib = {
        "math", "re", "json", "datetime", "typing", "hashlib", "hmac", "inspect",
        "copy", "collections", "time", "random", "itertools", "functools", "urllib",
        "uuid", "decimal", "string", "bisect", "operator", "subprocess", "os", "sys",
        "pathlib", "shutil", "tempfile", "io", "csv"
    }

    for inp in eval_inputs:
        tree = ast.parse(inp.module_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    assert top_pkg in allowed_builtins_and_stdlib, f"Unauthorized external import {top_pkg} in {inp.scenario_id}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_pkg = node.module.split(".")[0]
                    assert top_pkg in allowed_builtins_and_stdlib, f"Unauthorized external import {top_pkg} in {inp.scenario_id}"


# -----------------------------------------------------------------------------
# Check 14: Unsupported Categories Audit
# -----------------------------------------------------------------------------
def test_14_unsupported_categories_audit(ground_truths):
    """Validate distribution across all 7 authorized defect categories plus clean controls."""
    valid_categories = {
        "functional_bug",
        "security_vulnerability",
        "performance_bottleneck",
        "regression",
        "integration_defect",
        "semantic_drift",
        "non_convergent_by_design",
        "clean_control"
    }

    category_counts = {}
    for gt in ground_truths:
        cat = gt.defect_category
        assert cat in valid_categories, f"Invalid or unsupported defect category: {cat}"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    expected_counts = {
        "functional_bug": 120,
        "security_vulnerability": 60,
        "performance_bottleneck": 50,
        "regression": 50,
        "integration_defect": 50,
        "semantic_drift": 40,
        "non_convergent_by_design": 30,
        "clean_control": 100,
    }
    assert category_counts == expected_counts, f"Category count mismatch: {category_counts}"


# -----------------------------------------------------------------------------
# Check 15: Hidden-Label Leakage Check on Evaluation Inputs
# -----------------------------------------------------------------------------
def test_15_hidden_label_leakage_audit(eval_inputs):
    """Evaluation inputs must contain zero defect labels, CWE tags, defect IDs, or answer keys."""
    for inp in eval_inputs:
        d = inp.model_dump()
        # Ensure forbidden fields do not exist in evaluation inputs
        assert "defect_id" not in d
        assert "defect_category" not in d
        assert "expected_cwe_id" not in d
        assert "expected_line_number" not in d
        assert "mutation_operator" not in d
        assert "observed_defective_behavior" not in d
        assert "expected_behavior" not in d
        assert "oracle_code" not in d

        # Inspect scenario name and test_code for accidental leakage of forbidden tokens
        name_lower = inp.name.lower()
        assert "cwe-" not in name_lower, f"CWE ID leaked in scenario name for {inp.scenario_id}"
        assert "def-p3c2" not in name_lower, f"Defect ID leaked in scenario name for {inp.scenario_id}"


# -----------------------------------------------------------------------------
# Check 16: Frozen Held-Out Immutability
# -----------------------------------------------------------------------------
def test_16_frozen_held_out_immutability(manifest, benchmark_dir):
    """The held-out partition must be frozen and its checksum recorded."""
    assert manifest["dataset_version"] == "v3.2.0-phase3c2-large"
    partitions = manifest["partitions"]
    assert "held_out" in partitions
    assert partitions["held_out"]["count"] == 150

    # Ensure partition integrity report verifies zero heldout leakage
    pir_file = benchmark_dir / "partition_integrity_report.json"
    assert pir_file.exists()
    with open(pir_file, "r", encoding="utf-8") as f:
        pir = json.load(f)
    assert pir["isolation_guarantees"]["frozen_heldout_immutability"] is True


# -----------------------------------------------------------------------------
# Check 17: Historical Benchmark Preservation
# -----------------------------------------------------------------------------
def test_17_historical_benchmark_preservation():
    """Historical Phase 3A benchmarks and Phase 3C.1 pilot results must be preserved untouched."""
    base_dir = Path(__file__).resolve().parent.parent

    # Historical Phase 3C.1 pilot benchmark results file
    phase3c1_results = base_dir / "benchmark_results_phase3c1_pilot.json"
    assert phase3c1_results.exists(), "Historical Phase 3C.1 pilot benchmark results missing"
    with open(phase3c1_results, "r", encoding="utf-8") as f:
        pilot_data = json.load(f)
    assert pilot_data["dataset_version"] == "v3.1.0-phase3c1-pilot"
    assert pilot_data["total_scenarios"] == 16
    assert pilot_data["seeded_defects_count"] == 12
    assert pilot_data["clean_controls_count"] == 4

    # Phase 3A benchmark scenarios
    phase3a_file = base_dir / "benchmark" / "scenarios.json"
    if phase3a_file.exists():
        with open(phase3a_file, "r", encoding="utf-8") as f:
            phase3a_data = json.load(f)
        assert len(phase3a_data) >= 20, "Historical Phase 3A benchmark file was modified or corrupted"
