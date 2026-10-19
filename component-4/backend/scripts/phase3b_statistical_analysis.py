"""
INTELISE Component 4 — Phase 3B.3 Provenance-Strict Statistical Analysis Script.

Methodological Provenance Rules:
1. Validates prediction evidence against strict provenance categories:
   - EMPIRICAL_EXECUTION: Genuine recorded scenario observations (Component 4)
   - AGGREGATE_ONLY: Published marginal summary counts (Conventional CI Phase 3A Baseline)
   - SYNTHETIC_PROXY: Idealized theoretical model (NON-EMPIRICAL)
2. Declares Empirical Paired Tests (McNemar, Paired Bootstrap) UNAVAILABLE when matched
   scenario-level predictions are absent.
3. Mathematically proves paired indeterminacy from aggregate marginals.
4. Confirms empirical aggregate confusion matrices and metrics.
5. Restricts synthetic proxy analysis to an explicitly labeled non-empirical demonstration.
"""
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add backend directory to sys.path for benchmark module access
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.benchmark.statistical_analysis import (
    ConfusionMatrix,
    PredictionProvenance,
    ProvenanceValidationError,
    ScenarioPrediction,
    construct_confusion_matrix,
    compute_metrics_from_confusion_matrix,
    reconstruct_empirical_aggregate_confusion_matrix,
    explain_paired_indeterminacy_from_aggregates,
    wilson_score_interval,
    exact_mcnemar_test,
    construct_paired_correctness_table,
    run_paired_bootstrap,
    validate_scenario_lists,
    evaluate_synthetic_proxy_demonstration,
)


def run_statistical_analysis():
    dev_path = backend_dir / "benchmark_results_phase3_dev.json"
    heldout_path = backend_dir / "benchmark_results_phase3_heldout.json"
    all100_path = backend_dir / "benchmark_results_phase3_100.json"

    for path in (dev_path, heldout_path, all100_path):
        if not path.exists():
            raise FileNotFoundError(f"Required benchmark result file missing: {path}")

    with open(dev_path, "r") as f:
        res_dev = json.load(f)
    with open(heldout_path, "r") as f:
        res_heldout = json.load(f)
    with open(all100_path, "r") as f:
        res100 = json.load(f)

    splits = [
        ("Development Partition (40 Scenarios)", res_dev, 40),
        ("Held-Out Partition (60 Scenarios)", res_heldout, 60),
        ("Consolidated Benchmark (100 Scenarios)", res100, 100),
    ]

    report_lines = []

    for name, data, expected_n in splits:
        report_lines.append("=" * 80)
        report_lines.append(f"STATISTICAL PROVENANCE & EMPIRICAL ANALYSIS: {name}")
        report_lines.append("=" * 80)

        scenarios = data.get("scenarios", [])
        if len(scenarios) != expected_n:
            raise ValueError(
                f"Partition size violation in {name}: expected {expected_n}, found {len(scenarios)}."
            )

        # Strict Scenario Validation
        validate_scenario_lists(scenarios)

        y_true = [sc["ground_truth"]["has_defect"] for sc in scenarios]
        y_c4 = [sc["predictions"]["detected_has_defect"] for sc in scenarios]

        # [1] Component 4 Empirical Confusion Matrix & Metrics
        cm_c4 = construct_confusion_matrix(y_true, y_c4)
        m_c4 = compute_metrics_from_confusion_matrix(cm_c4)

        report_lines.append("\n[1] Component 4 Multi-Agent Verification (EMPIRICAL SCENARIO PREDICTIONS):")
        report_lines.append(f"  - Provenance       : {PredictionProvenance.EMPIRICAL_EXECUTION.value}")
        report_lines.append(
            f"  - Confusion Matrix : TP={cm_c4.true_positives}, FP={cm_c4.false_positives}, "
            f"TN={cm_c4.true_negatives}, FN={cm_c4.false_negatives} (Sum: {cm_c4.total}/{expected_n})"
        )
        report_lines.append(
            f"  - Class Support    : Positive (Defects) = {cm_c4.positive_support}, "
            f"Negative (Clean Controls) = {cm_c4.negative_support}"
        )
        report_lines.append(
            f"  - Accuracy         : {m_c4.accuracy:.4f} (Wilson 95% CI: {wilson_score_interval(cm_c4.true_positives + cm_c4.true_negatives, expected_n)})"
        )
        report_lines.append(
            f"  - Precision        : {m_c4.precision:.4f} (Wilson 95% CI: {wilson_score_interval(cm_c4.true_positives, cm_c4.true_positives + cm_c4.false_positives)})"
        )
        report_lines.append(
            f"  - Recall           : {m_c4.recall:.4f} (Wilson 95% CI: {wilson_score_interval(cm_c4.true_positives, cm_c4.positive_support)})"
        )
        report_lines.append(
            f"  - Binary F1        : {m_c4.f1_score:.4f}"
        )

        # [2] Conventional CI Baseline — Empirical Published Aggregate Records
        baselines = data.get("baselines", {})
        ci_tp, ci_fp, ci_tn, ci_fn = None, None, None, None
        if baselines:
            # Reconstruct exact confusion matrix from verified historical counts
            if expected_n == 40:
                ci_tp, ci_fp, ci_tn, ci_fn = 20, 1, 8, 11
            elif expected_n == 60:
                ci_tp, ci_fp, ci_tn, ci_fn = 29, 2, 18, 11
            elif expected_n == 100:
                ci_tp, ci_fp, ci_tn, ci_fn = 49, 3, 26, 22

            m_ci_emp = reconstruct_empirical_aggregate_confusion_matrix(
                total=expected_n,
                true_positives=ci_tp,
                false_positives=ci_fp,
                true_negatives=ci_tn,
                false_negatives=ci_fn,
            )

            report_lines.append("\n[2] Conventional CI Baseline — Empirical Published Records (AGGREGATE ONLY):")
            report_lines.append(f"  - Provenance       : {PredictionProvenance.AGGREGATE_ONLY.value}")
            report_lines.append(
                f"  - Confusion Matrix : TP={ci_tp}, FP={ci_fp}, TN={ci_tn}, FN={ci_fn} (Sum: {m_ci_emp.confusion_matrix.total}/{expected_n})"
            )
            report_lines.append(
                f"  - Accuracy         : {m_ci_emp.accuracy:.4f} (Wilson 95% CI: {wilson_score_interval(ci_tp + ci_tn, expected_n)})"
            )
            report_lines.append(
                f"  - Precision        : {m_ci_emp.precision:.4f} (JSON Published: {baselines.get('conventional_ci_precision')})"
            )
            report_lines.append(
                f"  - Recall           : {m_ci_emp.recall:.4f} (JSON Published: {baselines.get('conventional_ci_recall')})"
            )
            report_lines.append(
                f"  - Binary F1        : {m_ci_emp.f1_score:.4f} (JSON Published: {baselines.get('conventional_ci_f1')})"
            )
            report_lines.append(
                "  - Provenance Gap   : Scenario-level predictions for Conventional CI were NOT serialized to disk in Phase 3A."
            )

        # [3] Empirical Paired Significance Testing Status
        report_lines.append("\n[3] Empirical Paired Statistical Comparison Status:")
        report_lines.append("  - Status           : UNAVAILABLE (Missing Genuine Matched Baseline Scenario Predictions)")
        report_lines.append(
            "  - Finding          : McNemar's exact test and paired bootstrap resampling require matched scenario-by-scenario "
            "observations (y_true_i, y_c4_i, y_ci_i). Because Conventional CI predictions were only saved in aggregate, "
            "empirical paired tests cannot be computed for Phase 3A data."
        )

        # Mathematical Proof of Indeterminacy from Aggregates
        if ci_tp is not None:
            indet = explain_paired_indeterminacy_from_aggregates(cm_c4, m_ci_emp.confusion_matrix)
            report_lines.append("\n  - Mathematical Proof of Indeterminacy from Marginals Alone:")
            report_lines.append(f"    * Number of distinct paired (a,b,c,d) tables compatible with these marginals: {indet['compatible_table_count']}")
            report_lines.append(f"    * Range of possible exact McNemar p-values across valid pairings            : [{indet['min_possible_p_value']:.4f}, {indet['max_possible_p_value']:.4f}]")
            report_lines.append(f"    * Spans both significant (p < 0.05) and non-significant (p >= 0.05) outcomes : {indet['multiple_significance_outcomes']}")
            report_lines.append(
                "    * Scientific Conclusion: Deriving paired correctness from aggregate counts without recorded pairings is "
                "statistically invalid. Empirical paired claims are formally retracted for Phase 3A."
            )

        # [4] Theoretical Sensitivity Demonstration (Synthetic Proxy Model — NON-EMPIRICAL)
        # Construct proxy predictions with SYNTHETIC_PROXY provenance
        y_ci_proxy = [
            False if not sc["ground_truth"]["has_defect"]
            else (False if sc["group"] in ("performance_bottleneck", "semantic_drift") else True)
            for sc in scenarios
        ]
        cm_proxy = construct_confusion_matrix(y_true, y_ci_proxy)
        m_proxy = compute_metrics_from_confusion_matrix(cm_proxy)

        preds_c4 = [
            ScenarioPrediction(
                scenario_id=sc["scenario_id"],
                predicted_has_defect=sc["predictions"]["detected_has_defect"],
                provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
                system_name="Component 4 Multi-Agent",
                ground_truth_has_defect=sc["ground_truth"]["has_defect"],
            )
            for sc in scenarios
        ]
        preds_proxy = [
            ScenarioPrediction(
                scenario_id=sc["scenario_id"],
                predicted_has_defect=yp,
                provenance=PredictionProvenance.SYNTHETIC_PROXY,
                system_name="Conventional CI (Synthetic Proxy)",
                ground_truth_has_defect=sc["ground_truth"]["has_defect"],
            )
            for sc, yp in zip(scenarios, y_ci_proxy)
        ]

        proxy_res = evaluate_synthetic_proxy_demonstration(
            predictions_a=preds_c4,
            predictions_b=preds_proxy,
            iterations=10000,
            seed=42,
        )

        report_lines.append("\n[4] Theoretical Sensitivity Demonstration (SYNTHETIC PROXY — NON-EMPIRICAL):")
        report_lines.append("  *** DISCLAIMER: NON-EMPIRICAL MODEL. DO NOT USE FOR EMPIRICAL HYPOTHESIS TESTING. ***")
        report_lines.append(
            f"  - Model Assumptions : Clean controls pass (TN=clean); bottlenecks & drift missed; all others detected."
        )
        report_lines.append(
            f"  - Synthetic Proxy CM: TP={cm_proxy.true_positives}, FP={cm_proxy.false_positives}, "
            f"TN={cm_proxy.true_negatives}, FN={cm_proxy.false_negatives} | F1={m_proxy.f1_score:.4f}, Acc={m_proxy.accuracy:.4f}"
        )
        report_lines.append(f"  - Paired Table (Proxy): a={proxy_res.table.both_correct}, b={proxy_res.table.system_a_only}, c={proxy_res.table.system_b_only}, d={proxy_res.table.both_incorrect}")
        report_lines.append(f"  - McNemar Exact p-val : {proxy_res.mcnemar.p_value_exact_binomial:.4f} (Continuity chi2={proxy_res.mcnemar.chi2_continuity_corrected:.4f})")
        report_lines.append(f"  - Delta F1 95% CI     : {m_c4.f1_score - m_proxy.f1_score:+.4f} [{proxy_res.bootstrap.delta_f1_ci[0]:+.4f}, {proxy_res.bootstrap.delta_f1_ci[1]:+.4f}]")
        report_lines.append(f"  - Delta Acc 95% CI    : {m_c4.accuracy - m_proxy.accuracy:+.4f} [{proxy_res.bootstrap.delta_accuracy_ci[0]:+.4f}, {proxy_res.bootstrap.delta_accuracy_ci[1]:+.4f}]")

        # [5] Execution Telemetry
        durations = [sc.get("duration_ms", 0.0) for sc in scenarios]
        if durations and any(d > 0 for d in durations):
            durations.sort()
            report_lines.append("\n[5] Sandbox Execution Telemetry (Component 4 Multi-Agent):")
            report_lines.append(f"  - Mean Latency        : {statistics.mean(durations):.2f} ms")
            report_lines.append(f"  - Median Latency (p50): {statistics.median(durations):.2f} ms")
            report_lines.append(f"  - 95th Percentile     : {durations[int(len(durations) * 0.95)]:.2f} ms")

        report_lines.append("\n" + "=" * 80 + "\n")

    full_output = "\n".join(report_lines)
    print(full_output)
    return full_output


if __name__ == "__main__":
    run_statistical_analysis()
