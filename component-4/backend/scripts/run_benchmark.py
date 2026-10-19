#!/usr/bin/env python
"""
CLI Runner for INTELISE Component 4 Seeded-Defect Benchmark (Proposal Section 3.8).
Executes benchmark evaluation with methodological integrity (zero ground-truth leakage).
Supports both revised methodology fixtures and historical pilot dataset.
Default execution mode is genuine Docker container sandbox. Fast simulated mode is available via --simulated.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.benchmark.dataset import PILOT_BENCHMARK_SCENARIOS, REVISED_BENCHMARK_SCENARIOS
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.phase3_dataset import (
    DATASET_VERSION,
    PHASE3_ALL_SCENARIOS,
    PHASE3_DEV_SCENARIOS,
    PHASE3_HELDOUT_SCENARIOS,
    generate_phase3_manifest,
)


async def main():
    parser = argparse.ArgumentParser(description="INTELISE Component 4 Research Benchmark Evaluator")
    parser.add_argument(
        "--dataset",
        choices=["phase3_heldout", "phase3_dev", "phase3_all", "revised", "pilot"],
        default="phase3_heldout",
        help="Benchmark dataset to evaluate (Default: phase3_heldout)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output JSON filename (Default: auto-selected by dataset)",
    )
    parser.add_argument(
        "--simulated",
        action="store_true",
        default=False,
        help="Run high-speed simulated evaluation (Default: Real Docker execution)",
    )
    args = parser.parse_args()

    use_real_docker = not args.simulated
    mode_label = "REAL DOCKER CONTAINER SANDBOX" if use_real_docker else "FAST SIMULATED EXECUTION"
    dataset_choice = args.dataset

    manifest_hash = None
    if dataset_choice == "phase3_heldout":
        dataset = PHASE3_HELDOUT_SCENARIOS
        eval_version = f"{DATASET_VERSION}-heldout"
        split_label = "held_out"
        default_output = "benchmark_results_phase3_heldout.json"
        manifest = generate_phase3_manifest()
        manifest_hash = manifest["checksums"]["held_out_subset_sha256"]
    elif dataset_choice == "phase3_dev":
        dataset = PHASE3_DEV_SCENARIOS
        eval_version = f"{DATASET_VERSION}-dev"
        split_label = "dev"
        default_output = "benchmark_results_phase3_dev.json"
        manifest = generate_phase3_manifest()
        manifest_hash = manifest["checksums"]["dev_subset_sha256"]
    elif dataset_choice == "phase3_all":
        dataset = PHASE3_ALL_SCENARIOS
        eval_version = f"{DATASET_VERSION}-full100"
        split_label = "all_100"
        default_output = "benchmark_results_phase3_100.json"
        manifest = generate_phase3_manifest()
        manifest_hash = manifest["checksums"]["overall_manifest_sha256"]
    elif dataset_choice == "revised":
        dataset = REVISED_BENCHMARK_SCENARIOS
        eval_version = "v2_methodology_corrected"
        split_label = "revised_24"
        default_output = "benchmark_results_revised.json"
    else:
        dataset = PILOT_BENCHMARK_SCENARIOS
        eval_version = "v1_pilot"
        split_label = "pilot_18"
        default_output = "benchmark_results_pilot_reeval.json"

    output_filename = args.output or default_output

    print("=" * 80)
    print("INTELISE Component 4 — Seeded-Defect Research Benchmark Evaluation (SO6)")
    print(f"Dataset:        {dataset_choice.upper()} FIXTURES ({len(dataset)} Scenarios)")
    print(f"Dataset Split:  {split_label}")
    if manifest_hash:
        print(f"Manifest Hash:  {manifest_hash}")
    print(f"Execution Mode: {mode_label}")
    print("Integrity:      ZERO GROUND-TRUTH LEAKAGE (Independent predictions before scoring)")
    print("=" * 80)

    evaluator = BenchmarkEvaluator(use_real_docker=use_real_docker)
    summary = await evaluator.run_evaluation(
        scenarios=dataset,
        save_to_file=True,
        output_filename=output_filename,
        evaluation_version=eval_version,
        dataset_split=split_label,
        manifest_checksum=manifest_hash,
    )

    print(f"\nTotal Scenarios Evaluated: {summary.total_scenarios}")
    print(f"  - Clean Controls:            {summary.clean_controls_evaluated}")
    print(f"  - Functional Bugs:           {summary.functional_bugs_evaluated}")
    print(f"  - Security Vulnerabilities:  {summary.security_vulnerabilities_evaluated}")
    print(f"  - Performance Bottlenecks:   {summary.performance_bottlenecks_evaluated}")
    print(f"  - Regressions:               {summary.regressions_evaluated}")
    print(f"  - Non-Convergent By Design:  {summary.non_convergent_evaluated}")
    print(f"  - Semantic Drift Checks:     {summary.semantic_drift_cases_evaluated}")

    if summary.binary_detection_metrics:
        bdm = summary.binary_detection_metrics
        print("\n" + "-" * 80)
        print("BINARY DEFECT DETECTION PERFORMANCE (Defective vs Clean)")
        print("-" * 80)
        print(f"Accuracy:  {bdm.get('accuracy', 0.0):.3f} | Precision: {bdm.get('precision', 0.0):.3f} | Recall: {bdm.get('recall', 0.0):.3f} | F1: {bdm.get('f1_score', 0.0):.3f}")
        print(f"Confusion: TP={bdm.get('true_positives')}, FP={bdm.get('false_positives')}, TN={bdm.get('true_negatives')}, FN={bdm.get('false_negatives')}")

    print("\n" + "-" * 80)
    print("DEFECT TAXONOMY CLASSIFICATION METRICS (Table 5 Targets)")
    print("-" * 80)
    print(f"{'Category':<26} | {'Prec':<6} | {'Recall':<6} | {'F1':<6} | {'Target':<6} | {'Status'}")
    print("-" * 80)
    for cat_name, m in summary.category_metrics.items():
        status_icon = "MET [OK]" if m.target_met else "BELOW [X]"
        print(f"{cat_name:<26} | {m.precision:<6.3f} | {m.recall:<6.3f} | {m.f1_score:<6.3f} | {m.target_recall:<6.2f} | {status_icon}")
    print("-" * 80)
    print(f"{'OVERALL (Macro)':<26} | {summary.overall_precision:<6.3f} | {summary.overall_recall:<6.3f} | {summary.overall_f1:<6.3f} | {'-':<6} | -")

    if summary.confusion_matrix:
        print("\n" + "-" * 80)
        print("MULTICLASS CONFUSION MATRIX (Rows: Ground Truth, Columns: Predicted)")
        print("-" * 80)
        short_names = {"clean_control": "Clean", "functional_bug": "Func", "security_vulnerability": "Sec", "performance_bottleneck": "Perf", "regression": "Reg"}
        header = f"{'True \\ Pred':<14} | " + " | ".join(f"{short_names.get(k, k):<6}" for k in short_names)
        print(header)
        print("-" * 80)
        for r_key, r_name in short_names.items():
            row_vals = [f"{summary.confusion_matrix.get(r_key, {}).get(c_key, 0):<6}" for c_key in short_names]
            print(f"{r_name:<14} | " + " | ".join(row_vals))

    if summary.localization_metrics:
        lm = summary.localization_metrics
        print("\n" + "-" * 80)
        print("EVIDENCE-BASED DEFECT LOCALIZATION")
        print("-" * 80)
        print(f"Evaluated Defective Scenarios: {lm.get('scenarios_evaluated')}")
        print(f"Exact Line Hit Rate:           {lm.get('exact_line_accuracy', 0.0) * 100:.1f}% ({lm.get('exact_line_matches')}/{lm.get('scenarios_evaluated')})")
        print(f"Proximity Line Hit Rate (±2):  {lm.get('near_line_accuracy', 0.0) * 100:.1f}% ({lm.get('near_line_matches')}/{lm.get('scenarios_evaluated')})")

    if summary.semantic_drift_metrics:
        sdm = summary.semantic_drift_metrics
        print("\n" + "-" * 80)
        print("SEMANTIC-DRIFT & TEST WEAKENING METRICS (FR07, SO5)")
        print("-" * 80)
        print(f"Scenarios Evaluated: {sdm.get('scenarios_evaluated')}")
        print(f"Drift Precision:     {sdm.get('precision', 0.0):.3f} | Recall: {sdm.get('recall', 0.0):.3f} | F1: {sdm.get('f1_score', 0.0):.3f}")
        print(f"Drift Confusion:     TP={sdm.get('true_positives')}, FP={sdm.get('false_positives')}, TN={sdm.get('true_negatives')}, FN={sdm.get('false_negatives')}")

    if summary.convergence_repair_metrics:
        crm = summary.convergence_repair_metrics
        print("\n" + "-" * 80)
        print("CONTROLLED MULTI-ITERATION REPAIR & GOVERNANCE ESCALATION (SO5, RQ4)")
        print("-" * 80)
        print(f"Harness Mode:            {crm.get('evaluation_mode')}")
        print(f"Live Component 3 Link:   {crm.get('component_3_live_integration')} (Disabled via COMPONENT_3_ENABLED=false)")
        print(f"Repair Scenarios Run:    {crm.get('scenarios_evaluated')}")
        print(f"Correct Escalation Rate: {crm.get('correct_escalation_rate', 0.0) * 100:.1f}%")

    print("\n" + "-" * 80)
    print("EXECUTION OVERHEAD")
    print("-" * 80)
    print(f"Mean Latency:   {summary.mean_execution_time_ms:.2f} ms")
    print(f"Median Latency: {summary.median_execution_time_ms:.2f} ms")
    print(f"95th % Latency: {summary.p95_execution_time_ms:.2f} ms")

    print("\n" + "-" * 80)
    print("COMPARATIVE EXECUTABLE BASELINES")
    print("-" * 80)
    print(f"Component 4 Multi-Agent F1:             {summary.overall_f1:.3f}")
    delta = summary.overall_f1 - summary.single_agent_baseline_f1
    print(f"Baseline 1 (Conventional CI Pytest):    F1: {summary.single_agent_baseline_f1:.3f} (Delta: {delta:+.3f})")
    print(f"Baseline 2 (Static Analysis AST Only):  Recall: {summary.static_analysis_baseline_recall:.3f} vs Component 4 {summary.category_metrics['security_vulnerability'].recall:.3f}")
    print(f"Baseline 3 (Generic XAI Protocol):      Protocol frozen in docs/BLINDED_HUMAN_EVALUATION_PROTOCOL.md")
    print("=" * 80)
    print(f"Detailed results saved to: {output_filename}\n")


if __name__ == "__main__":
    asyncio.run(main())
