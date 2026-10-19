"""
INTELISE Component 4 — Phase 3 100-Scenario Benchmark Dataset Aggregator & Manifest Tools.
Combines:
- 40 Development Scenarios (app.benchmark.phase3_dev.PHASE3_DEV_SCENARIOS)
- 60 Held-Out Evaluation Scenarios (app.benchmark.phase3_heldout.PHASE3_HELDOUT_SCENARIOS)

Provides cryptographic checksum hashing (SHA-256) for frozen dataset verification (Task 2 & Task 6).
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from app.benchmark.models import BenchmarkScenario
from app.benchmark.phase3_dev import PHASE3_DEV_SCENARIOS
from app.benchmark.phase3_heldout import PHASE3_HELDOUT_SCENARIOS

PHASE3_ALL_SCENARIOS: List[BenchmarkScenario] = PHASE3_DEV_SCENARIOS + PHASE3_HELDOUT_SCENARIOS

DATASET_VERSION = "v3.0.0-heldout"


def compute_scenario_checksum(scenario: BenchmarkScenario) -> str:
    """Computes a deterministic SHA-256 digest of a scenario's code, tests, and ground truth."""
    hasher = hashlib.sha256()
    hasher.update(scenario.scenario_id.encode("utf-8"))
    hasher.update(scenario.module_code.strip().encode("utf-8"))
    hasher.update(scenario.test_code.strip().encode("utf-8"))
    if scenario.original_test_code:
        hasher.update(scenario.original_test_code.strip().encode("utf-8"))
    if scenario.candidate_test_code:
        hasher.update(scenario.candidate_test_code.strip().encode("utf-8"))
    hasher.update(str(scenario.has_defect).encode("utf-8"))
    hasher.update(str(scenario.expected_defect_category.value).encode("utf-8"))
    hasher.update(str(scenario.expected_cwe_id or "").encode("utf-8"))
    hasher.update(str(scenario.expected_line_number or "").encode("utf-8"))
    hasher.update(str(scenario.has_semantic_drift).encode("utf-8"))
    hasher.update(str(scenario.is_non_convergent_by_design).encode("utf-8"))
    return hasher.hexdigest()


def generate_phase3_manifest() -> Dict[str, Any]:
    """Generates the frozen dataset manifest with per-scenario and overall SHA-256 checksums."""
    dev_records = []
    dev_hasher = hashlib.sha256()
    for sc in PHASE3_DEV_SCENARIOS:
        sc_hash = compute_scenario_checksum(sc)
        sc.checksum_sha256 = sc_hash
        dev_hasher.update(sc_hash.encode("utf-8"))
        dev_records.append({
            "scenario_id": sc.scenario_id,
            "name": sc.name,
            "group": sc.scenario_group.value,
            "split": "dev",
            "difficulty": sc.difficulty,
            "provenance": sc.provenance,
            "has_defect": sc.has_defect,
            "expected_defect_category": sc.expected_defect_category.value,
            "expected_cwe_id": sc.expected_cwe_id,
            "expected_line_number": sc.expected_line_number,
            "has_semantic_drift": sc.has_semantic_drift,
            "is_non_convergent_by_design": sc.is_non_convergent_by_design,
            "checksum_sha256": sc_hash,
        })

    heldout_records = []
    heldout_hasher = hashlib.sha256()
    for sc in PHASE3_HELDOUT_SCENARIOS:
        sc_hash = compute_scenario_checksum(sc)
        sc.checksum_sha256 = sc_hash
        heldout_hasher.update(sc_hash.encode("utf-8"))
        heldout_records.append({
            "scenario_id": sc.scenario_id,
            "name": sc.name,
            "group": sc.scenario_group.value,
            "split": "held_out",
            "difficulty": sc.difficulty,
            "provenance": sc.provenance,
            "has_defect": sc.has_defect,
            "expected_defect_category": sc.expected_defect_category.value,
            "expected_cwe_id": sc.expected_cwe_id,
            "expected_line_number": sc.expected_line_number,
            "has_semantic_drift": sc.has_semantic_drift,
            "is_non_convergent_by_design": sc.is_non_convergent_by_design,
            "checksum_sha256": sc_hash,
        })

    total_hasher = hashlib.sha256()
    total_hasher.update(dev_hasher.hexdigest().encode("utf-8"))
    total_hasher.update(heldout_hasher.hexdigest().encode("utf-8"))

    manifest = {
        "dataset_version": DATASET_VERSION,
        "dataset_name": "INTELISE Component 4 Phase 3 100-Scenario Benchmark",
        "total_scenarios": len(PHASE3_ALL_SCENARIOS),
        "split_counts": {
            "development_scenarios": len(PHASE3_DEV_SCENARIOS),
            "held_out_scenarios": len(PHASE3_HELDOUT_SCENARIOS),
        },
        "category_distribution": {
            "clean_controls": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "clean_control"),
            "functional_bugs": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "functional_bug"),
            "security_vulnerabilities": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "security_vulnerability"),
            "performance_bottlenecks": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "performance_bottleneck"),
            "integration_defects": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "integration_defect"),
            "regression_defects": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "regression"),
            "semantic_drift_cases": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "semantic_drift"),
            "non_convergent_by_design": sum(1 for s in PHASE3_ALL_SCENARIOS if s.scenario_group.value == "non_convergent_by_design"),
        },
        "checksums": {
            "overall_manifest_sha256": total_hasher.hexdigest(),
            "dev_subset_sha256": dev_hasher.hexdigest(),
            "held_out_subset_sha256": heldout_hasher.hexdigest(),
        },
        "scenarios": dev_records + heldout_records,
    }
    return manifest


def save_manifest_to_file(filepath: Path) -> Dict[str, Any]:
    """Generates and writes the frozen dataset manifest to disk."""
    manifest = generate_phase3_manifest()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest
