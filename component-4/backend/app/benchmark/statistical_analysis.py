"""
INTELISE Component 4 — Statistical Analysis & Benchmark Verification Library.

Provides mathematically verified routines for:
1. Binary confusion matrix construction and metric derivation (Accuracy, Precision, Recall, F1).
2. Paired correctness contingency table construction (a, b, c, d) for McNemar's test.
3. Exact two-tailed binomial McNemar test and continuity-corrected Chi-square.
4. Wilson score intervals for binomial proportions.
5. Paired non-parametric bootstrap resampling for F1 and difference metrics.
6. Strict validation rules: duplicate scenario IDs, mismatched sets, missing predictions, invalid sizes.
7. Explicit Provenance Tracking & Verification:
   - EMPIRICAL_EXECUTION
   - VERIFIED_LOG_RECONSTRUCTION
   - SYNTHETIC_PROXY
   - AGGREGATE_ONLY
8. Rejection of synthetic proxies and aggregate-only evidence from empirical paired testing.
9. Mathematical demonstration of paired indeterminacy from aggregate confusion matrices.
"""
from dataclasses import dataclass, field
from enum import Enum
import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple


class PredictionProvenance(str, Enum):
    """
    Provenance category of benchmark prediction observations.
    Only EMPIRICAL_EXECUTION and VERIFIED_LOG_RECONSTRUCTION may be used
    for empirical paired statistical tests.
    """
    EMPIRICAL_EXECUTION = "EMPIRICAL_EXECUTION"
    VERIFIED_LOG_RECONSTRUCTION = "VERIFIED_LOG_RECONSTRUCTION"
    SYNTHETIC_PROXY = "SYNTHETIC_PROXY"
    AGGREGATE_ONLY = "AGGREGATE_ONLY"


class ProvenanceValidationError(ValueError):
    """Raised when prediction evidence fails strict provenance or integrity validation."""
    pass


@dataclass(frozen=True)
class ScenarioPrediction:
    """Represents a scenario-level binary defect prediction with strict provenance metadata."""
    scenario_id: str
    predicted_has_defect: bool
    provenance: PredictionProvenance
    system_name: str
    ground_truth_has_defect: Optional[bool] = None
    ground_truth_category: Optional[str] = None
    execution_metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.scenario_id or not self.scenario_id.strip():
            raise ValueError("ScenarioPrediction must have a non-empty scenario_id.")
        if not isinstance(self.provenance, PredictionProvenance):
            # Attempt enum coercion if string passed
            try:
                object.__setattr__(self, "provenance", PredictionProvenance(str(self.provenance)))
            except ValueError:
                raise ProvenanceValidationError(
                    f"Invalid provenance '{self.provenance}'. Must be one of {[p.value for p in PredictionProvenance]}."
                )
        if not self.system_name or not self.system_name.strip():
            raise ValueError("ScenarioPrediction must declare a system_name.")


@dataclass(frozen=True)
class ConfusionMatrix:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    positive_support: int
    negative_support: int
    total: int

    def __post_init__(self):
        if self.true_positives < 0 or self.false_positives < 0 or self.true_negatives < 0 or self.false_negatives < 0:
            raise ValueError("Confusion matrix counts must be non-negative integers.")
        calculated_total = (
            self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        )
        if calculated_total != self.total:
            raise ValueError(
                f"Confusion matrix sum ({calculated_total}) does not match declared total ({self.total})."
            )
        if self.true_positives + self.false_negatives != self.positive_support:
            raise ValueError(
                f"Positive support mismatch: TP ({self.true_positives}) + FN ({self.false_negatives}) != {self.positive_support}."
            )
        if self.true_negatives + self.false_positives != self.negative_support:
            raise ValueError(
                f"Negative support mismatch: TN ({self.true_negatives}) + FP ({self.false_positives}) != {self.negative_support}."
            )


@dataclass(frozen=True)
class BinaryMetrics:
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    confusion_matrix: ConfusionMatrix


@dataclass(frozen=True)
class PairedCorrectnessTable:
    both_correct: int          # a
    system_a_only: int         # b (A correct, B incorrect)
    system_b_only: int         # c (A incorrect, B correct)
    both_incorrect: int        # d
    total: int

    def __post_init__(self):
        calculated = self.both_correct + self.system_a_only + self.system_b_only + self.both_incorrect
        if calculated != self.total:
            raise ValueError(
                f"Paired table sum ({calculated}) does not match partition total ({self.total})."
            )


@dataclass(frozen=True)
class McNemarResult:
    b: int
    c: int
    discordant_pairs: int
    chi2_continuity_corrected: float
    p_value_chi2: float
    p_value_exact_binomial: float
    odds_ratio: float
    is_significant_at_05: bool


@dataclass(frozen=True)
class BootstrapResult:
    iterations: int
    seed: int
    f1_a_ci: Tuple[float, float]
    f1_b_ci: Tuple[float, float]
    delta_f1_ci: Tuple[float, float]
    delta_accuracy_ci: Tuple[float, float]


@dataclass(frozen=True)
class PairedComparisonResult:
    is_empirical: bool
    system_a_name: str
    system_b_name: str
    scenario_count: int
    table: PairedCorrectnessTable
    mcnemar: McNemarResult
    bootstrap: BootstrapResult
    provenance_disclaimer: Optional[str] = None


def validate_scenario_lists(
    scenarios_a: List[Dict[str, Any]],
    scenarios_b: Optional[List[Dict[str, Any]]] = None,
    id_key: str = "scenario_id",
) -> None:
    """
    Validates scenario lists for:
    - Non-empty records
    - Duplicate scenario IDs
    - Mismatched IDs / lengths across systems
    - Presence of required fields
    """
    if not scenarios_a:
        raise ValueError("Scenario list 'A' cannot be empty.")

    ids_a = [s.get(id_key) for s in scenarios_a]
    if any(sid is None for sid in ids_a):
        raise ValueError(f"Every scenario in system A must contain '{id_key}'.")

    if len(ids_a) != len(set(ids_a)):
        seen = set()
        duplicates = [x for x in ids_a if x in seen or seen.add(x)]
        raise ValueError(f"Duplicate scenario IDs detected in system A: {duplicates}")

    if scenarios_b is not None:
        if not scenarios_b:
            raise ValueError("Scenario list 'B' cannot be empty when provided.")
        ids_b = [s.get(id_key) for s in scenarios_b]
        if any(sid is None for sid in ids_b):
            raise ValueError(f"Every scenario in system B must contain '{id_key}'.")

        if len(ids_b) != len(set(ids_b)):
            seen_b = set()
            duplicates_b = [x for x in ids_b if x in seen_b or seen_b.add(x)]
            raise ValueError(f"Duplicate scenario IDs detected in system B: {duplicates_b}")

        if len(ids_a) != len(ids_b):
            raise ValueError(
                f"Mismatched scenario count: system A has {len(ids_a)}, system B has {len(ids_b)}."
            )

        if set(ids_a) != set(ids_b):
            missing_in_b = set(ids_a) - set(ids_b)
            missing_in_a = set(ids_b) - set(ids_a)
            raise ValueError(
                f"Mismatched scenario IDs across systems. Missing in B: {missing_in_b}, Missing in A: {missing_in_a}"
            )


def validate_paired_empirical_evidence(
    predictions_a: List[ScenarioPrediction],
    predictions_b: List[ScenarioPrediction],
    ground_truth: Optional[Dict[str, bool]] = None,
    allow_synthetic_demonstration: bool = False,
) -> None:
    """
    Strict validation for paired statistical comparisons.
    Enforces:
    1. Non-empty predictions.
    2. Unique scenario IDs within each system.
    3. Identical scenario set across both systems.
    4. Exact ground-truth agreement.
    5. Provenance validation: Rejects SYNTHETIC_PROXY and AGGREGATE_ONLY from empirical comparisons.
    """
    if not predictions_a:
        raise ValueError("Predictions for System A cannot be empty.")
    if not predictions_b:
        raise ValueError("Predictions for System B cannot be empty.")

    ids_a = [p.scenario_id for p in predictions_a]
    if len(ids_a) != len(set(ids_a)):
        seen = set()
        dups = [x for x in ids_a if x in seen or seen.add(x)]
        raise ValueError(f"Duplicate scenario IDs detected in System A: {dups}")

    ids_b = [p.scenario_id for p in predictions_b]
    if len(ids_b) != len(set(ids_b)):
        seen_b = set()
        dups_b = [x for x in ids_b if x in seen_b or seen_b.add(x)]
        raise ValueError(f"Duplicate scenario IDs detected in System B: {dups_b}")

    if len(ids_a) != len(ids_b):
        raise ValueError(
            f"Mismatched prediction counts: System A has {len(ids_a)}, System B has {len(ids_b)}."
        )

    if set(ids_a) != set(ids_b):
        diff = set(ids_a) ^ set(ids_b)
        raise ValueError(f"Mismatched scenario IDs across systems: {diff}")

    # Ground truth validation
    map_a = {p.scenario_id: p for p in predictions_a}
    map_b = {p.scenario_id: p for p in predictions_b}

    for sid in ids_a:
        pa = map_a[sid]
        pb = map_b[sid]

        if pa.ground_truth_has_defect is not None and pb.ground_truth_has_defect is not None:
            if pa.ground_truth_has_defect != pb.ground_truth_has_defect:
                raise ValueError(
                    f"Ground-truth mismatch for scenario '{sid}': System A has {pa.ground_truth_has_defect}, "
                    f"System B has {pb.ground_truth_has_defect}."
                )

        if ground_truth is not None:
            if sid not in ground_truth:
                raise ValueError(f"Scenario '{sid}' missing from authoritative ground truth mapping.")
            expected = ground_truth[sid]
            if pa.ground_truth_has_defect is not None and pa.ground_truth_has_defect != expected:
                raise ValueError(
                    f"Ground truth conflict for scenario '{sid}': prediction has {pa.ground_truth_has_defect}, "
                    f"authoritative map has {expected}."
                )

    # Provenance enforcement
    valid_empirical_provenances = {
        PredictionProvenance.EMPIRICAL_EXECUTION,
        PredictionProvenance.VERIFIED_LOG_RECONSTRUCTION,
    }

    if not allow_synthetic_demonstration:
        for p in predictions_a:
            if p.provenance not in valid_empirical_provenances:
                raise ProvenanceValidationError(
                    f"Empirical paired analysis rejected: System '{p.system_name}' scenario '{p.scenario_id}' "
                    f"has non-empirical provenance '{p.provenance.value}'. "
                    "Empirical paired significance testing strictly requires genuine empirical observations "
                    "or verified log reconstructions."
                )
        for p in predictions_b:
            if p.provenance not in valid_empirical_provenances:
                raise ProvenanceValidationError(
                    f"Empirical paired analysis rejected: System '{p.system_name}' scenario '{p.scenario_id}' "
                    f"has non-empirical provenance '{p.provenance.value}'. "
                    "Empirical paired significance testing strictly requires genuine empirical observations "
                    "or verified log reconstructions."
                )


def evaluate_empirical_paired_test(
    predictions_a: List[ScenarioPrediction],
    predictions_b: List[ScenarioPrediction],
    ground_truth: Optional[Dict[str, bool]] = None,
    iterations: int = 10000,
    seed: int = 42,
) -> PairedComparisonResult:
    """
    Executes a methodologically verified empirical paired comparison (McNemar & Paired Bootstrap).
    Strictly requires genuine empirical predictions for both systems.
    """
    validate_paired_empirical_evidence(
        predictions_a=predictions_a,
        predictions_b=predictions_b,
        ground_truth=ground_truth,
        allow_synthetic_demonstration=False,
    )

    map_b = {p.scenario_id: p for p in predictions_b}
    sorted_a = sorted(predictions_a, key=lambda x: x.scenario_id)

    y_true: List[bool] = []
    y_a: List[bool] = []
    y_b: List[bool] = []

    for pa in sorted_a:
        pb = map_b[pa.scenario_id]
        gt = ground_truth[pa.scenario_id] if ground_truth else pa.ground_truth_has_defect
        if gt is None:
            raise ValueError(f"Ground truth label missing for scenario '{pa.scenario_id}'.")
        y_true.append(gt)
        y_a.append(pa.predicted_has_defect)
        y_b.append(pb.predicted_has_defect)

    table = construct_paired_correctness_table(y_true, y_a, y_b)
    mcn = exact_mcnemar_test(table.system_a_only, table.system_b_only)
    boot = run_paired_bootstrap(y_true, y_a, y_b, iterations=iterations, seed=seed)

    return PairedComparisonResult(
        is_empirical=True,
        system_a_name=predictions_a[0].system_name,
        system_b_name=predictions_b[0].system_name,
        scenario_count=len(y_true),
        table=table,
        mcnemar=mcn,
        bootstrap=boot,
        provenance_disclaimer=None,
    )


def evaluate_synthetic_proxy_demonstration(
    predictions_a: List[ScenarioPrediction],
    predictions_b: List[ScenarioPrediction],
    ground_truth: Optional[Dict[str, bool]] = None,
    iterations: int = 10000,
    seed: int = 42,
) -> PairedComparisonResult:
    """
    Executes an explicit non-empirical sensitivity demonstration using a synthetic proxy model.
    Output is clearly stamped as non-empirical.
    """
    validate_paired_empirical_evidence(
        predictions_a=predictions_a,
        predictions_b=predictions_b,
        ground_truth=ground_truth,
        allow_synthetic_demonstration=True,
    )

    map_b = {p.scenario_id: p for p in predictions_b}
    sorted_a = sorted(predictions_a, key=lambda x: x.scenario_id)

    y_true: List[bool] = []
    y_a: List[bool] = []
    y_b: List[bool] = []

    for pa in sorted_a:
        pb = map_b[pa.scenario_id]
        gt = ground_truth[pa.scenario_id] if ground_truth else pa.ground_truth_has_defect
        if gt is None:
            raise ValueError(f"Ground truth label missing for scenario '{pa.scenario_id}'.")
        y_true.append(gt)
        y_a.append(pa.predicted_has_defect)
        y_b.append(pb.predicted_has_defect)

    table = construct_paired_correctness_table(y_true, y_a, y_b)
    mcn = exact_mcnemar_test(table.system_a_only, table.system_b_only)
    boot = run_paired_bootstrap(y_true, y_a, y_b, iterations=iterations, seed=seed)

    return PairedComparisonResult(
        is_empirical=False,
        system_a_name=predictions_a[0].system_name,
        system_b_name=predictions_b[0].system_name,
        scenario_count=len(y_true),
        table=table,
        mcnemar=mcn,
        bootstrap=boot,
        provenance_disclaimer=(
            "NON-EMPIRICAL SYNTHETIC PROXY DEMONSTRATION: Reconstructed from theoretical model. "
            "Cannot be used to assert empirical statistical superiority or equivalence."
        ),
    )


def construct_confusion_matrix(y_true: List[bool], y_pred: List[bool]) -> ConfusionMatrix:
    """Builds and strictly validates a binary confusion matrix."""
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"Length mismatch between ground truth ({len(y_true)}) and predictions ({len(y_pred)})."
        )
    if not y_true:
        raise ValueError("Inputs cannot be empty.")

    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt is True and yp is True)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt is False and yp is True)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt is False and yp is False)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt is True and yp is False)
    total = len(y_true)

    pos_support = tp + fn
    neg_support = tn + fp

    return ConfusionMatrix(
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        positive_support=pos_support,
        negative_support=neg_support,
        total=total,
    )


def compute_metrics_from_confusion_matrix(cm: ConfusionMatrix) -> BinaryMetrics:
    """
    Computes Accuracy, Precision, Recall, and F1 score from a ConfusionMatrix.
    Handles zero-division edge cases deterministically:
    - If total == 0: all metrics 0.0
    - If TP + FP == 0 (no positive predictions): Precision = 1.0 (no false alarms)
    - If TP + FN == 0 (no actual positives): Recall = 0.0
    - If Precision + Recall == 0: F1 = 0.0
    """
    if cm.total == 0:
        return BinaryMetrics(0.0, 0.0, 0.0, 0.0, cm)

    acc = (cm.true_positives + cm.true_negatives) / cm.total

    if (cm.true_positives + cm.false_positives) > 0:
        prec = cm.true_positives / (cm.true_positives + cm.false_positives)
    else:
        prec = 1.0  # Zero false positives when predicting no defects

    if (cm.true_positives + cm.false_negatives) > 0:
        rec = cm.true_positives / (cm.true_positives + cm.false_negatives)
    else:
        rec = 0.0

    if (prec + rec) > 0:
        f1 = (2.0 * prec * rec) / (prec + rec)
    else:
        f1 = 0.0

    return BinaryMetrics(
        accuracy=round(acc, 4),
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
        confusion_matrix=cm,
    )


def compute_binary_metrics(y_true: List[bool], y_pred: List[bool]) -> BinaryMetrics:
    """Convenience helper constructing confusion matrix and computing metrics."""
    cm = construct_confusion_matrix(y_true, y_pred)
    return compute_metrics_from_confusion_matrix(cm)


def reconstruct_empirical_aggregate_confusion_matrix(
    total: int,
    true_positives: int,
    false_positives: int,
    true_negatives: int,
    false_negatives: int,
) -> BinaryMetrics:
    """Reconstructs and verifies empirical metrics directly from validated aggregate counts."""
    pos_support = true_positives + false_negatives
    neg_support = true_negatives + false_positives
    cm = ConfusionMatrix(
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        positive_support=pos_support,
        negative_support=neg_support,
        total=total,
    )
    return compute_metrics_from_confusion_matrix(cm)


def explain_paired_indeterminacy_from_aggregates(
    cm_a: ConfusionMatrix,
    cm_b: ConfusionMatrix,
) -> Dict[str, Any]:
    """
    Demonstrates mathematically why aggregate confusion matrices are insufficient
    for McNemar's test or paired bootstrap testing.
    Calculates the range of possible (a, b, c, d) contingency tables and p-values
    compatible with the exact same marginal confusion matrices.
    """
    if cm_a.total != cm_b.total:
        raise ValueError("Both systems must have identical scenario counts.")

    n = cm_a.total
    k_a = cm_a.true_positives + cm_a.true_negatives  # Total correct in A
    k_b = cm_b.true_positives + cm_b.true_negatives  # Total correct in B

    # Number of scenarios both correct (a) can range from max(0, k_a + k_b - n) to min(k_a, k_b)
    min_a = max(0, k_a + k_b - n)
    max_a = min(k_a, k_b)

    compatible_tables = []
    for a in range(min_a, max_a + 1):
        b = k_a - a
        c = k_b - a
        d = n - a - b - c
        mcn = exact_mcnemar_test(b, c)
        compatible_tables.append({
            "both_correct_a": a,
            "system_a_only_b": b,
            "system_b_only_c": c,
            "both_incorrect_d": d,
            "discordant_pairs": b + c,
            "p_value_exact": mcn.p_value_exact_binomial,
            "statistically_significant_05": mcn.is_significant_at_05,
        })

    p_values = [t["p_value_exact"] for t in compatible_tables]
    significance_statuses = set(t["statistically_significant_05"] for t in compatible_tables)

    return {
        "scenario_count": n,
        "system_a_correct": k_a,
        "system_b_correct": k_b,
        "compatible_table_count": len(compatible_tables),
        "min_possible_p_value": min(p_values),
        "max_possible_p_value": max(p_values),
        "multiple_significance_outcomes": len(significance_statuses) > 1,
        "explanation": (
            f"Given aggregate accuracies {k_a}/{n} and {k_b}/{n}, exactly {len(compatible_tables)} "
            f"distinct paired contingency tables are mathematically possible. Depending on unrecorded "
            f"scenario pairing, the exact McNemar p-value ranges from {min(p_values):.4f} to {max(p_values):.4f}. "
            "Therefore, paired significance testing cannot be performed from aggregate confusion matrices alone."
        ),
        "compatible_tables_sample": [compatible_tables[0], compatible_tables[-1]],
    }


def wilson_score_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """
    Calculates exact Wilson score confidence interval for a binomial proportion.
    Safe against boundary cases (0 successes, total successes, zero total).
    """
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1.0 + (z ** 2) / total
    centre = (p + (z ** 2) / (2.0 * total)) / denom
    radicand = (p * (1.0 - p) / total) + ((z ** 2) / (4.0 * (total ** 2)))
    spread = (z * math.sqrt(max(0.0, radicand))) / denom
    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return (round(lower, 4), round(upper, 4))


def exact_mcnemar_test(b: int, c: int) -> McNemarResult:
    """
    Computes exact two-tailed binomial p-value and continuity-corrected McNemar Chi-Square.
    b: System A correct & System B incorrect
    c: System A incorrect & System B correct
    """
    if b < 0 or c < 0:
        raise ValueError("Discordant counts b and c must be non-negative.")

    discordant = b + c
    if discordant == 0:
        return McNemarResult(
            b=0,
            c=0,
            discordant_pairs=0,
            chi2_continuity_corrected=0.0,
            p_value_chi2=1.0,
            p_value_exact_binomial=1.0,
            odds_ratio=1.0,
            is_significant_at_05=False,
        )

    chi2 = (max(0.0, abs(b - c) - 1.0) ** 2) / discordant
    p_chi2 = math.erfc(math.sqrt(chi2 / 2.0))

    k = min(b, c)
    cum_prob = sum(math.comb(discordant, i) for i in range(k + 1)) * (0.5 ** discordant)
    p_exact = min(1.0, 2.0 * cum_prob)

    if c == 0:
        odds_ratio = (b + 0.5) / 0.5
    else:
        odds_ratio = b / c

    return McNemarResult(
        b=b,
        c=c,
        discordant_pairs=discordant,
        chi2_continuity_corrected=round(chi2, 4),
        p_value_chi2=round(p_chi2, 4),
        p_value_exact_binomial=round(p_exact, 4),
        odds_ratio=round(odds_ratio, 2),
        is_significant_at_05=p_exact < 0.05,
    )


def construct_paired_correctness_table(
    y_true: List[bool],
    y_a: List[bool],
    y_b: List[bool],
) -> PairedCorrectnessTable:
    """
    Constructs the 2x2 paired correctness contingency table:
    a: y_a == y_true AND y_b == y_true
    b: y_a == y_true AND y_b != y_true (System A win)
    c: y_a != y_true AND y_b == y_true (System B win)
    d: y_a != y_true AND y_b != y_true (Both wrong)
    """
    if len(y_true) != len(y_a) or len(y_true) != len(y_b):
        raise ValueError(
            f"Mismatched array lengths: y_true={len(y_true)}, y_a={len(y_a)}, y_b={len(y_b)}."
        )
    if not y_true:
        raise ValueError("Inputs cannot be empty.")

    a_correct = [yt == ya for yt, ya in zip(y_true, y_a)]
    b_correct = [yt == yb for yt, yb in zip(y_true, y_b)]

    a = sum(1 for ca, cb in zip(a_correct, b_correct) if ca and cb)
    b = sum(1 for ca, cb in zip(a_correct, b_correct) if ca and not cb)
    c = sum(1 for ca, cb in zip(a_correct, b_correct) if not ca and cb)
    d = sum(1 for ca, cb in zip(a_correct, b_correct) if not ca and not cb)

    return PairedCorrectnessTable(
        both_correct=a,
        system_a_only=b,
        system_b_only=c,
        both_incorrect=d,
        total=len(y_true),
    )


def percentile(data: List[float], p: float) -> float:
    """Calculates percentile using linear interpolation."""
    if not data:
        raise ValueError("Cannot calculate percentile of empty list.")
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * p
    f = int(k)
    c = f + 1
    if c < len(sorted_d):
        return sorted_d[f] + (k - f) * (sorted_d[c] - sorted_d[f])
    return sorted_d[f]


def run_paired_bootstrap(
    y_true: List[bool],
    y_a: List[bool],
    y_b: List[bool],
    iterations: int = 10000,
    seed: int = 42,
) -> BootstrapResult:
    """
    Executes paired non-parametric bootstrap resampling for F1 and difference metrics.
    Guarantees deterministic results using a fixed seed.
    """
    if len(y_true) != len(y_a) or len(y_true) != len(y_b):
        raise ValueError("Inputs must have identical lengths for paired bootstrap.")
    if iterations <= 0:
        raise ValueError("Bootstrap iterations must be greater than zero.")

    rng = random.Random(seed)
    n = len(y_true)
    indices = list(range(n))

    b_f1_a: List[float] = []
    b_f1_b: List[float] = []
    b_delta_f1: List[float] = []
    b_delta_acc: List[float] = []

    for _ in range(iterations):
        boot_idx = [rng.choice(indices) for _ in range(n)]
        yt_b = [y_true[i] for i in boot_idx]
        ya_b = [y_a[i] for i in boot_idx]
        yb_b = [y_b[i] for i in boot_idx]

        m_a = compute_binary_metrics(yt_b, ya_b)
        m_b = compute_binary_metrics(yt_b, yb_b)

        b_f1_a.append(m_a.f1_score)
        b_f1_b.append(m_b.f1_score)
        b_delta_f1.append(m_a.f1_score - m_b.f1_score)
        b_delta_acc.append(m_a.accuracy - m_b.accuracy)

    return BootstrapResult(
        iterations=iterations,
        seed=seed,
        f1_a_ci=(round(percentile(b_f1_a, 0.025), 4), round(percentile(b_f1_a, 0.975), 4)),
        f1_b_ci=(round(percentile(b_f1_b, 0.025), 4), round(percentile(b_f1_b, 0.975), 4)),
        delta_f1_ci=(round(percentile(b_delta_f1, 0.025), 4), round(percentile(b_delta_f1, 0.975), 4)),
        delta_accuracy_ci=(round(percentile(b_delta_acc, 0.025), 4), round(percentile(b_delta_acc, 0.975), 4)),
    )
