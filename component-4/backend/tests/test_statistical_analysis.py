"""
Tests for Benchmark Statistical Analysis & Metric Consistency (Phase 3B.2 Task 3).

Validates:
1. Perfect classification.
2. All-negative predictions.
3. All-positive predictions.
4. Zero-division edge cases.
5. Incorrectly sized confusion matrices (sum != total).
6. Missing scenario predictions and fields.
7. Duplicate scenario IDs.
8. Mismatched scenario sets between systems.
9. McNemar paired correctness construction.
10. F1 calculation consistency with ConfusionMatrix.
"""
import pytest
from app.benchmark.statistical_analysis import (
    ConfusionMatrix,
    BinaryMetrics,
    PairedCorrectnessTable,
    McNemarResult,
    construct_confusion_matrix,
    compute_metrics_from_confusion_matrix,
    compute_binary_metrics,
    wilson_score_interval,
    exact_mcnemar_test,
    construct_paired_correctness_table,
    run_paired_bootstrap,
    validate_scenario_lists,
)


def test_perfect_classification():
    """Validates metrics when predictions match ground truth exactly."""
    y_true = [True, True, False, False, True]
    y_pred = [True, True, False, False, True]

    metrics = compute_binary_metrics(y_true, y_pred)
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0

    cm = metrics.confusion_matrix
    assert cm.true_positives == 3
    assert cm.true_negatives == 2
    assert cm.false_positives == 0
    assert cm.false_negatives == 0
    assert cm.positive_support == 3
    assert cm.negative_support == 2
    assert cm.total == 5


def test_all_negative_predictions():
    """Validates metrics when all predictions are False (no alarms)."""
    y_true = [True, True, False, False]
    y_pred = [False, False, False, False]

    metrics = compute_binary_metrics(y_true, y_pred)
    assert metrics.accuracy == 0.5  # 2 TN out of 4
    assert metrics.precision == 1.0  # Zero false positives
    assert metrics.recall == 0.0  # 0 TP out of 2 positive
    assert metrics.f1_score == 0.0

    cm = metrics.confusion_matrix
    assert cm.true_positives == 0
    assert cm.true_negatives == 2
    assert cm.false_positives == 0
    assert cm.false_negatives == 2
    assert cm.total == 4


def test_all_positive_predictions():
    """Validates metrics when all predictions are True."""
    y_true = [True, True, False, False]
    y_pred = [True, True, True, True]

    metrics = compute_binary_metrics(y_true, y_pred)
    assert metrics.accuracy == 0.5  # 2 TP out of 4
    assert metrics.precision == 0.5  # 2 TP out of 4 predicted
    assert metrics.recall == 1.0  # 2 TP out of 2 actual
    assert round(metrics.f1_score, 4) == round(2 * 0.5 * 1.0 / (0.5 + 1.0), 4)

    cm = metrics.confusion_matrix
    assert cm.true_positives == 2
    assert cm.true_negatives == 0
    assert cm.false_positives == 2
    assert cm.false_negatives == 0
    assert cm.total == 4


def test_zero_division_edge_cases():
    """Validates handling of zero-division edge cases."""
    # All negative ground truth, all negative prediction
    y_true_neg = [False, False, False]
    y_pred_neg = [False, False, False]
    m1 = compute_binary_metrics(y_true_neg, y_pred_neg)
    assert m1.accuracy == 1.0
    assert m1.precision == 1.0
    assert m1.recall == 0.0  # No actual positives
    assert m1.f1_score == 0.0

    # All positive ground truth, all negative prediction
    y_true_pos = [True, True]
    y_pred_all_fn = [False, False]
    m2 = compute_binary_metrics(y_true_pos, y_pred_all_fn)
    assert m2.accuracy == 0.0
    assert m2.recall == 0.0
    assert m2.precision == 1.0
    assert m2.f1_score == 0.0

    # Wilson interval with zero total
    assert wilson_score_interval(0, 0) == (0.0, 0.0)
    assert wilson_score_interval(0, 10)[0] == 0.0
    assert wilson_score_interval(10, 10)[1] == 1.0

    # McNemar with zero discordant pairs
    mcn = exact_mcnemar_test(0, 0)
    assert mcn.discordant_pairs == 0
    assert mcn.p_value_exact_binomial == 1.0
    assert mcn.is_significant_at_05 is False


def test_incorrectly_sized_confusion_matrices():
    """Validates that ConfusionMatrix rejects sums not matching total or negative counts."""
    with pytest.raises(ValueError, match="does not match declared total"):
        ConfusionMatrix(
            true_positives=10,
            false_positives=2,
            true_negatives=5,
            false_negatives=1,
            positive_support=11,
            negative_support=7,
            total=20,  # 10 + 2 + 5 + 1 = 18 != 20
        )

    with pytest.raises(ValueError, match="must be non-negative"):
        ConfusionMatrix(
            true_positives=-1,
            false_positives=0,
            true_negatives=5,
            false_negatives=0,
            positive_support=0,
            negative_support=5,
            total=4,
        )

    with pytest.raises(ValueError, match="Positive support mismatch"):
        ConfusionMatrix(
            true_positives=10,
            false_positives=2,
            true_negatives=5,
            false_negatives=1,
            positive_support=15,  # 10 + 1 = 11 != 15
            negative_support=7,
            total=18,
        )


def test_missing_scenario_predictions_and_fields():
    """Validates error reporting when scenario predictions or IDs are missing."""
    scenarios_missing_id = [{"other_field": 123}]
    with pytest.raises(ValueError, match="must contain 'scenario_id'"):
        validate_scenario_lists(scenarios_missing_id)

    with pytest.raises(ValueError, match="cannot be empty"):
        validate_scenario_lists([])


def test_duplicate_scenario_ids():
    """Validates error reporting on duplicate scenario IDs."""
    scenarios = [
        {"scenario_id": "SC-001", "pred": True},
        {"scenario_id": "SC-002", "pred": False},
        {"scenario_id": "SC-001", "pred": True},
    ]
    with pytest.raises(ValueError, match="Duplicate scenario IDs detected"):
        validate_scenario_lists(scenarios)


def test_mismatched_scenario_sets_between_systems():
    """Validates error reporting when systems evaluate different scenario sets."""
    sys_a = [
        {"scenario_id": "SC-001", "pred": True},
        {"scenario_id": "SC-002", "pred": False},
    ]
    sys_b_count_mismatch = [
        {"scenario_id": "SC-001", "pred": True},
    ]
    with pytest.raises(ValueError, match="Mismatched scenario count"):
        validate_scenario_lists(sys_a, sys_b_count_mismatch)

    sys_b_id_mismatch = [
        {"scenario_id": "SC-001", "pred": True},
        {"scenario_id": "SC-003", "pred": False},
    ]
    with pytest.raises(ValueError, match="Mismatched scenario IDs"):
        validate_scenario_lists(sys_a, sys_b_id_mismatch)


def test_mcnemar_paired_correctness_construction():
    """Validates construction of 2x2 paired correctness table (a, b, c, d)."""
    # 4 scenarios:
    # 0: both correct
    # 1: A correct, B wrong
    # 2: A wrong, B correct
    # 3: both wrong
    y_true = [True, True, False, False]
    y_a = [True, True, True, True]      # correct: 0, 1 (wrong: 2, 3)
    y_b = [True, False, False, True]     # correct: 0, 2 (wrong: 1, 3)

    table = construct_paired_correctness_table(y_true, y_a, y_b)
    assert table.both_correct == 1       # index 0
    assert table.system_a_only == 1      # index 1
    assert table.system_b_only == 1      # index 2
    assert table.both_incorrect == 1     # index 3
    assert table.total == 4

    mcn = exact_mcnemar_test(table.system_a_only, table.system_b_only)
    assert mcn.b == 1
    assert mcn.c == 1
    assert mcn.discordant_pairs == 2
    assert mcn.p_value_exact_binomial == 1.0


def test_f1_calculation_consistency():
    """Validates mathematical consistency of F1 score with ConfusionMatrix."""
    # Held-out Component 4 empirical numbers
    cm = ConfusionMatrix(
        true_positives=34,
        false_positives=2,
        true_negatives=18,
        false_negatives=6,
        positive_support=40,
        negative_support=20,
        total=60,
    )
    metrics = compute_metrics_from_confusion_matrix(cm)
    assert metrics.accuracy == round(52 / 60, 4)
    assert metrics.precision == round(34 / 36, 4)
    assert metrics.recall == round(34 / 40, 4)

    expected_f1 = (2 * (34 / 36) * (34 / 40)) / ((34 / 36) + (34 / 40))
    assert metrics.f1_score == round(expected_f1, 4)
    assert metrics.f1_score == 0.8947  # 0.895 rounded to 3 places


def test_paired_bootstrap_reproducibility():
    """Validates deterministic bootstrap execution and delta calculation."""
    y_true = [True] * 40 + [False] * 20
    y_c4 = [True] * 34 + [False] * 6 + [True] * 2 + [False] * 18
    y_ci = [True] * 29 + [False] * 11 + [True] * 2 + [False] * 18

    res1 = run_paired_bootstrap(y_true, y_c4, y_ci, iterations=500, seed=42)
    res2 = run_paired_bootstrap(y_true, y_c4, y_ci, iterations=500, seed=42)

    assert res1.f1_a_ci == res2.f1_a_ci
    assert res1.f1_b_ci == res2.f1_b_ci
    assert res1.delta_f1_ci == res2.delta_f1_ci
    assert res1.delta_accuracy_ci == res2.delta_accuracy_ci
