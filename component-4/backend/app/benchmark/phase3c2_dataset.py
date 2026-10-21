"""
INTELISE Component 4 — Phase 3C.2: Large-Scale Benchmark Schemas and Loader.

Provides:
- Phase3C2EvaluationInput: Public evaluation interface strictly devoid of ground-truth labels.
- Phase3C2SealedGroundTruth: Hidden ground-truth store containing labels, mutation operators, and oracles.
- Phase3C2DatasetLoader: Loader enforcing zero-leakage partition access and benchmark sealing.
"""
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.common import DefectCategory


class BenchmarkPartition(str, Enum):
    DEVELOPMENT = "dev"
    VALIDATION = "val"
    FROZEN_HELDOUT = "held_out"


class Phase3C2EvaluationInput(BaseModel):
    """
    Public evaluation input visible to Component 4 detectors, LLM agents, and baselines.
    STRICT ANTI-LEAKAGE GUARANTEE:
    Contains zero defect labels, zero CWE IDs, zero mutation operators, zero expected line numbers,
    and zero oracle answers.
    """
    scenario_id: str = Field(description="Unique scenario ID, e.g. P3C2-001")
    name: str = Field(description="Descriptive public title of the scenario")
    filename: str = Field(default="solution.py", description="Target file under test")
    module_code: str = Field(description="Python source code under verification")
    test_code: str = Field(description="Executable test suite authorized for verification")
    requirement_ids: List[str] = Field(default_factory=lambda: ["REQ-001"], description="Requirement specifications")
    requested_test_types: List[str] = Field(default_factory=lambda: ["unit"], description="Requested verification types")
    original_test_code: Optional[str] = Field(default=None, description="Original test suite for regression/drift checking")
    candidate_test_code: Optional[str] = Field(default=None, description="Candidate test suite for drift checking")
    repair_candidate_patches: Optional[List[str]] = Field(default=None, description="Candidate patches for repair evaluation")
    is_repair_loop_scenario: bool = Field(default=False, description="Flag indicating repair loop testing")


class Phase3C2SealedGroundTruth(BaseModel):
    """
    Sealed ground-truth record stored in isolation.
    Must never be loaded or passed into detection agents or baseline evaluators during execution.
    Joined strictly post-hoc for benchmark scoring and metric calculation.
    """
    scenario_id: str = Field(description="Unique scenario ID matching Phase3C2EvaluationInput")
    defect_id: Optional[str] = Field(default=None, description="Unique defect ID (None for clean controls)")
    has_defect: bool = Field(description="Ground truth binary defect label")
    defect_category: str = Field(description="Ground truth defect category (or clean_control)")
    expected_cwe_id: Optional[str] = Field(default=None, description="Expected CWE identifier if security vulnerability")
    expected_line_number: Optional[int] = Field(default=None, description="1-indexed physical source line of defect")
    difficulty: str = Field(description="Difficulty level: easy, medium, hard")
    family_id: str = Field(description="Source project/template family identifier")
    partition: str = Field(description="Assigned partition: dev, val, or held_out")
    mutation_operator: Optional[str] = Field(default=None, description="Applied mutation operator")
    original_clean_source: str = Field(description="Clean reference source code")
    mutated_source: str = Field(description="Mutated or tested source code")
    oracle_id: str = Field(description="Unique identifier of the independent verification oracle")
    expected_behavior: str = Field(description="Documented specification of expected behavior")
    observed_defective_behavior: str = Field(description="Documented description of observed defect manifestation")
    validation_result: str = Field(default="PASSED", description="Independent oracle validation outcome: PASSED or QUARANTINED")
    validation_evidence: Dict[str, Any] = Field(default_factory=dict, description="Execution evidence from oracle validation")
    generation_seed: int = Field(default=42, description="Random seed used during deterministic generation")
    created_timestamp: str = Field(description="ISO-8601 creation timestamp")


class Phase3C2DatasetLoader:
    """
    Secure loader for the Phase 3C.2 benchmark dataset.
    Provides partition filtering and enforces sealed boundary separation.
    """

    def __init__(self, benchmark_dir: Optional[Path] = None):
        if benchmark_dir is None:
            # Default to component-4/benchmark/phase3c2
            self.benchmark_dir = Path(__file__).resolve().parent.parent.parent.parent / "benchmark" / "phase3c2"
        else:
            self.benchmark_dir = Path(benchmark_dir)

        self.inputs_file = self.benchmark_dir / "evaluation_inputs.json"
        self.ground_truth_file = self.benchmark_dir / "sealed_ground_truth.json"
        self.manifest_file = self.benchmark_dir / "manifest.json"
        self.checksums_file = self.benchmark_dir / "dataset_checksums.json"

    def load_manifest(self) -> Dict[str, Any]:
        """Loads the dataset manifest."""
        if not self.manifest_file.exists():
            raise FileNotFoundError(f"Dataset manifest not found at {self.manifest_file}")
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_evaluation_inputs(self, partition: Optional[str] = None) -> List[Phase3C2EvaluationInput]:
        """
        Loads evaluation inputs for detectors and baselines.
        Zero ground truth is exposed.
        """
        if not self.inputs_file.exists():
            raise FileNotFoundError(f"Evaluation inputs not found at {self.inputs_file}")

        with open(self.inputs_file, "r", encoding="utf-8") as f:
            raw_inputs = json.load(f)

        inputs = [Phase3C2EvaluationInput(**item) for item in raw_inputs]

        if partition is not None:
            # To filter by partition without exposing ground truth to evaluators,
            # we query partition mappings from manifest or sealed truth partition map
            partition_map = self._get_partition_scenario_ids(partition)
            inputs = [inp for inp in inputs if inp.scenario_id in partition_map]

        return inputs

    def load_sealed_ground_truth(self, partition: Optional[str] = None) -> List[Phase3C2SealedGroundTruth]:
        """
        Loads sealed ground truth strictly for post-evaluation metrics calculation.
        """
        if not self.ground_truth_file.exists():
            raise FileNotFoundError(f"Sealed ground truth not found at {self.ground_truth_file}")

        with open(self.ground_truth_file, "r", encoding="utf-8") as f:
            raw_gt = json.load(f)

        gt_records = [Phase3C2SealedGroundTruth(**item) for item in raw_gt]

        if partition is not None:
            gt_records = [gt for gt in gt_records if gt.partition == partition]

        return gt_records

    def _get_partition_scenario_ids(self, partition: str) -> set:
        """Retrieves set of scenario IDs for a partition from the manifest."""
        manifest = self.load_manifest()
        partitions = manifest.get("partitions", {})
        if partition in partitions:
            return set(partitions[partition].get("scenario_ids", []))
        # Fallback to reading sealed ground truth partition field
        with open(self.ground_truth_file, "r", encoding="utf-8") as f:
            raw_gt = json.load(f)
        return {item["scenario_id"] for item in raw_gt if item.get("partition") == partition}

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verifies checksums of dataset files against dataset_checksums.json.
        """
        if not self.checksums_file.exists():
            return {"valid": False, "error": f"Checksums file not found at {self.checksums_file}"}

        with open(self.checksums_file, "r", encoding="utf-8") as f:
            checksums = json.load(f)

        mismatches = []
        for filename, expected_hash in checksums.get("files", {}).items():
            filepath = self.benchmark_dir / filename
            if not filepath.exists():
                mismatches.append(f"Missing file: {filename}")
                continue
            with open(filepath, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                mismatches.append(f"Hash mismatch for {filename}: expected {expected_hash}, got {actual_hash}")

        return {
            "valid": len(mismatches) == 0,
            "mismatches": mismatches,
            "checked_files": list(checksums.get("files", {}).keys()),
        }
