"""
Generate dedicated versioned pilot benchmark artifacts for Phase 3C.1 under component-4/benchmark/pilot_phase3c1/.
"""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.benchmark.phase3c1_pilot import (
    PILOT_SCENARIOS,
    PilotBenchmarkRunner,
)

async def main():
    root_dir = backend_dir.parent
    target_dir = root_dir / "benchmark" / "pilot_phase3c1"
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating Phase 3C.1 Pilot artifacts in: {target_dir}")

    # 1. Scenarios dataset JSON
    scenarios_data = []
    for s in PILOT_SCENARIOS:
        sc_dict = {
            "scenario_id": s.scenario_id,
            "scenario_group": s.ground_truth.expected_category,
            "name": s.input_data.name,
            "input_data": s.input_data.model_dump(),
            "ground_truth": s.ground_truth.model_dump(),
            "checksum": hashlib.sha256(s.input_data.module_code.encode("utf-8")).hexdigest(),
        }
        scenarios_data.append(sc_dict)

    scenarios_file = target_dir / "pilot_scenarios.json"
    with open(scenarios_file, "w", encoding="utf-8") as f:
        json.dump(scenarios_data, f, indent=2)
    print(f"Wrote {len(scenarios_data)} scenarios to {scenarios_file}")

    # 2. Execute pilot and write pilot_evaluation_results.json
    runner = PilotBenchmarkRunner(use_real_docker=False)
    results = await runner.execute_pilot()

    results_file = target_dir / "pilot_evaluation_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote pilot results to {results_file}")

    # Also keep backend/benchmark_results_phase3c1_pilot.json synchronized
    backend_results_file = backend_dir / "benchmark_results_phase3c1_pilot.json"
    with open(backend_results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Synchronized {backend_results_file}")

    # 3. Create manifest with SHA-256 hashes
    manifest = {
        "release": "Phase 3C.1 Pilot Benchmark",
        "version": "v3.1.0-phase3c1-pilot",
        "description": "Reproducible machine-readable pilot benchmark dataset, execution observations, and evaluation metrics",
        "files": {}
    }

    for p in [scenarios_file, results_file]:
        with open(p, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        manifest["files"][p.name] = {
            "sha256": h,
            "size_bytes": p.stat().st_size,
        }

    manifest_file = target_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote provenance manifest to {manifest_file}")
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
