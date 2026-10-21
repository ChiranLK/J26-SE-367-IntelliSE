"""
INTELISE Component 4 — Phase 3C.2: Dataset Loader Smoke and Boundary Test Suite.

Tests that Phase3C2DatasetLoader:
- Correctly parses the manifest and partitions.
- Safely delivers Phase3C2EvaluationInput with zero leaked ground truth.
- Exposes partition filtering (dev, val, held_out) without cross-leakage.
- Verifies dataset checksum integrity.
"""
from pathlib import Path
import pytest

from app.benchmark.phase3c2_dataset import (
    Phase3C2DatasetLoader,
    Phase3C2EvaluationInput,
    Phase3C2SealedGroundTruth,
)


@pytest.fixture(scope="module")
def dataset_loader() -> Phase3C2DatasetLoader:
    benchmark_dir = Path(__file__).resolve().parent.parent.parent / "benchmark" / "phase3c2"
    return Phase3C2DatasetLoader(benchmark_dir=benchmark_dir)


def test_loader_manifest(dataset_loader: Phase3C2DatasetLoader):
    manifest = dataset_loader.load_manifest()
    assert manifest["summary"]["total_scenarios"] == 500
    assert manifest["summary"]["total_defects"] == 400
    assert manifest["summary"]["total_clean_controls"] == 100
    assert manifest["dataset_version"] == "v3.2.0-phase3c2-large"


def test_loader_evaluation_inputs_all(dataset_loader: Phase3C2DatasetLoader):
    inputs = dataset_loader.load_evaluation_inputs()
    assert len(inputs) == 500
    assert isinstance(inputs[0], Phase3C2EvaluationInput)
    # Check that model fields exclude any ground truth
    sample_dict = inputs[0].model_dump()
    assert "defect_id" not in sample_dict
    assert "mutation_operator" not in sample_dict
    assert "expected_line_number" not in sample_dict


def test_loader_evaluation_inputs_by_partition(dataset_loader: Phase3C2DatasetLoader):
    dev_inputs = dataset_loader.load_evaluation_inputs(partition="dev")
    val_inputs = dataset_loader.load_evaluation_inputs(partition="val")
    held_inputs = dataset_loader.load_evaluation_inputs(partition="held_out")

    assert len(dev_inputs) == 250
    assert len(val_inputs) == 100
    assert len(held_inputs) == 150

    dev_ids = {i.scenario_id for i in dev_inputs}
    val_ids = {i.scenario_id for i in val_inputs}
    held_ids = {i.scenario_id for i in held_inputs}

    assert len(dev_ids & val_ids) == 0
    assert len(dev_ids & held_ids) == 0
    assert len(val_ids & held_ids) == 0


def test_loader_sealed_ground_truth(dataset_loader: Phase3C2DatasetLoader):
    gt_all = dataset_loader.load_sealed_ground_truth()
    assert len(gt_all) == 500
    assert isinstance(gt_all[0], Phase3C2SealedGroundTruth)

    gt_dev = dataset_loader.load_sealed_ground_truth(partition="dev")
    gt_val = dataset_loader.load_sealed_ground_truth(partition="val")
    gt_held = dataset_loader.load_sealed_ground_truth(partition="held_out")

    assert len(gt_dev) == 250
    assert len(gt_val) == 100
    assert len(gt_held) == 150


def test_loader_verify_integrity(dataset_loader: Phase3C2DatasetLoader):
    result = dataset_loader.verify_integrity()
    assert result["valid"] is True
    assert result["mismatches"] == []
