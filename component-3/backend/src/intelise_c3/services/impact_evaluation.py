"""Set-based precision, recall, and F1 for impact-selection scenarios.

The metrics compare selected module paths with a separately supplied label set.
They are calculated, never benchmarked, and say nothing about repair success.
"""

from dataclasses import dataclass
from typing import Literal

from intelise_c3.domain.scoped_regeneration import (
    ImpactScenarioOutcome,
    ImpactSelectionEvaluationReport,
    ImpactSelectionReport,
    ImpactSelectionStatus,
)


@dataclass(frozen=True)
class ImpactScenario:
    scenario_id: str
    expected_status: ImpactSelectionStatus
    expected_modules: frozenset[str]
    observed: ImpactSelectionReport


def evaluate_impact_selection(
    *,
    dataset_id: str,
    dataset_version: str,
    review_status: Literal["NOT_INDEPENDENTLY_REVIEWED"],
    scenarios: tuple[ImpactScenario, ...],
) -> ImpactSelectionEvaluationReport:
    outcomes: list[ImpactScenarioOutcome] = []
    true_positive = false_positive = false_negative = 0
    agreements = 0
    for scenario in scenarios:
        selected = frozenset(item.relative_path for item in scenario.observed.selected_modules)
        tp = selected & scenario.expected_modules
        fp = selected - scenario.expected_modules
        fn = scenario.expected_modules - selected
        true_positive += len(tp)
        false_positive += len(fp)
        false_negative += len(fn)
        agreements += scenario.observed.status is scenario.expected_status
        outcomes.append(
            ImpactScenarioOutcome(
                scenario_id=scenario.scenario_id,
                expected_status=scenario.expected_status,
                observed_status=scenario.observed.status,
                expected_modules=tuple(sorted(scenario.expected_modules)),
                selected_modules=tuple(sorted(selected)),
                true_positive_modules=tuple(sorted(tp)),
                false_positive_modules=tuple(sorted(fp)),
                false_negative_modules=tuple(sorted(fn)),
            )
        )
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1_score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ImpactSelectionEvaluationReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        ground_truth_review_status=review_status,
        scenario_count=len(scenarios),
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        decision_agreement_count=agreements,
        outcomes=tuple(outcomes),
    )
