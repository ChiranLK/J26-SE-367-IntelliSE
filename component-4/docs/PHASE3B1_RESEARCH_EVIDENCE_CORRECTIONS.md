# INTELISE Component 4 — Phase 3B.1: Research Evidence Integrity Corrections

## 1. Executive Summary & Audit Context

This document provides formal corrections to statistical and dataset-reporting inconsistencies identified in the Phase 3B evaluation audit for **INTELISE Component 4** (*Intelligent Agentic Testing & Explainable Feedback Loop Assistant*), prior to commencing Phase 3C.

In accordance with strict academic research integrity standards:
- **Zero Modifications to Frozen Data**: The Phase 3A 60-scenario held-out dataset, ground-truth labels, SHA-256 manifests, and historical benchmark prediction JSON files remain completely frozen and unmodified.
- **Evidence-Grounded Reporting**: All statistical tables, dataset counts, and performance metrics are reconciled to verifiable code artifacts and empirical execution logs.
- **Decoupled Architecture Preserved**: Live Component 3 cross-component communication remains disabled (`COMPONENT_3_ENABLED=false`), with technical repair feedback operating via schema-validated contracts.

> [!IMPORTANT]
> **Phase 3B.3 Provenance & Statistical Correction Notice (October 2026)**:
> Paired statistical comparisons (McNemar and bootstrap intervals in Section 4.3) were derived using an idealized synthetic proxy model because scenario-level predictions for Conventional CI were not serialized during Phase 3A. Under Phase 3B.3 research evidence integrity guidelines, proxy-derived paired tests are classified as **non-empirical sensitivity demonstrations**. Fully empirical paired significance testing is classified as **UNAVAILABLE** for Phase 3A data. See [docs/PHASE3B3_EMPIRICAL_PROVENANCE_CORRECTION.md](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/docs/PHASE3B3_EMPIRICAL_PROVENANCE_CORRECTION.md).

---

## 2. Dataset & Seeded-Defect Reconciliation (Task 1)

### 2.1 Root-Cause Analysis of Reporting Inconsistencies

The Phase 3B report previously stated:
- *Development*: 40 scenarios, 28 code defects, 2 drift cases, 2 repair cases, 10 clean controls ($28 + 2 + 2 + 10 = 42 > 40$).
- *Held-Out*: 60 scenarios, 43 code defects, 2 drift cases, 3 repair cases, 19 clean controls ($43 + 2 + 3 + 19 = 67 > 60$).

> **Finding**: These sums exceeded partition sizes because **mutually exclusive primary scenario categories** were conflated with **overlapping orthogonal feature annotations**:
> 1. In Development, the 2 semantic drift scenarios (`PH3-DEV-037`, `PH3-DEV-038`) and 2 repair loop scenarios (`PH3-DEV-039`, `PH3-DEV-040`) were counted once as primary groups and then added a second time as separate categories. Furthermore, clean controls were misstated as 10 instead of 8 primary clean controls.
> 2. In Held-Out, the subtotal of primary code defects (35) was confused with total defective scenarios (40). Adding drift cases (5) and non-convergent cases (2) on top of the whole, while counting clean controls as 19, produced a sum of 67.

### 2.2 Mutually Exclusive Primary Scenario Taxonomy

Every scenario in the INTELISE Component 4 benchmark belongs to exactly **one mutually exclusive primary group** (`scenario_group` enum). The partition sums strictly equal the dataset partition sizes:

| Primary Scenario Category (`scenario_group`) | Development Partition ($N = 40$) | Held-Out Partition ($N = 60$) | Consolidated Benchmark ($N = 100$) |
| :--- | :---: | :---: | :---: |
| `clean_control` | 8 | 18 | 26 |
| `functional_bug` | 10 | 15 | 25 |
| `security_vulnerability` | 6 | 5 | 11 |
| `performance_bottleneck` | 4 | 3 | 7 |
| `regression` | 4 | 6 | 10 |
| `integration_defect` | 4 | 6 | 10 |
| `semantic_drift` | 2 | 5 | 7 |
| `non_convergent_by_design` | 2 | 2 | 4 |
| **Total Scenarios** | **40** | **60** | **100** |

### 2.3 Orthogonal Feature Annotations Matrix

In addition to primary taxonomy grouping, scenarios carry independent boolean research feature flags evaluated by specialized verification agents:

| Feature Annotation Flag | Dev ($N = 40$) | Held-Out ($N = 60$) | Total ($N = 100$) | Accounting Scope & Purpose |
| :--- | :---: | :---: | :---: | :--- |
| `has_defect == True` | 31 | 40 | 71 | Scenarios containing actual implementation defects in the candidate module under verification. |
| `has_defect == False` | 9 | 20 | 29 | Clean negative controls (26 primary clean controls + 3 semantic drift negative controls with clean code). |
| `has_semantic_drift == True` | 1 | 3 | 4 | Scenarios where the candidate test suite exhibits assertion weakening or test deletion mutations. |
| `is_repair_loop_scenario == True` | 2 | 4 | 6 | Scenarios evaluated inside the multi-iteration repair feedback harness with candidate patch sequences. |
| `is_non_convergent_by_design == True`| 2 | 2 | 4 | Scenarios engineered with oscillating or regressive patch sequences to evaluate loop safety governors. |

### 2.4 Multi-Defect Accounting & Compound Scenarios

To avoid ambiguity, the following explicit counting rules are established:
- **Rule 1 (Unit of Execution)**: Exactly 100 benchmark scenarios exist (40 dev, 60 held-out). Each scenario represents an independent containerized verification run.
- **Rule 2 (Seeded Implementation Defects)**: Exactly 71 scenarios contain code defects (`has_defect=True`). Each defective scenario targets a single localized fault coordinate (`expected_line_number`).
- **Rule 3 (Compound Scenarios)**: Scenarios in specialized evaluation groups can carry multiple feature annotations:
  - `PH3-DEV-037`: Contains 1 code defect (`has_defect=True`) **and** 1 test suite mutation (`has_semantic_drift=True`).
  - `PH3-DEV-039`, `PH3-DEV-040`: Contain 1 code defect **and** multi-patch repair loop sequences (`is_repair_loop_scenario=True`).
  - `PH3-HELD-053`, `PH3-HELD-054`: Contain 1 code defect **and** 1 test suite mutation.
  - `PH3-HELD-055`, `PH3-HELD-056`: Drift negative controls containing 0 code defects (`has_defect=False`) and 0 drift mutations (`has_semantic_drift=False`).
  - `PH3-HELD-060`: Compound scenario containing 1 code defect, 1 test suite drift mutation, **and** multi-patch repair candidate evaluation.
- **Rule 4 (Proposal Target Reconciled)**: The current 100-scenario benchmark provides 71 unique seeded code defects and 4 test suite mutations (75 total faults). Reaching the proposal's target of 300–500 seeded defects requires automated synthetic mutation generation on external benchmarks (e.g. HumanEval, Defects4J) planned for Phase 3C.

---

## 3. Corrected McNemar Statistical Analysis (Task 2)

### 3.1 Methodological Grounding of McNemar's Test

McNemar's test is a non-parametric paired test of marginal homogeneity applied to nominal data from two matched systems.
> **Critical Requirement**: McNemar's test must be computed from a $2 \times 2$ contingency table of **paired ground-truth correctness** ($y_i == \hat{y}_i$), **NOT** simple positive-detection agreement:
> - $a$: Both Component 4 and Conventional CI are **Correct** ($y_i == \hat{y}_{C4, i}$ and $y_i == \hat{y}_{CI, i}$).
> - $b$: Component 4 is **Correct**, Conventional CI is **Incorrect** (Discordant C4 win).
> - $c$: Component 4 is **Incorrect**, Conventional CI is **Correct** (Discordant CI win).
> - $d$: Both systems are **Incorrect** ($y_i \ne \hat{y}_{C4, i}$ and $y_i \ne \hat{y}_{CI, i}$).

### 3.2 Corrected Paired Contingency Tables

Based on actual container execution outcomes against ground truth:

#### Held-Out Partition ($N = 60$)
```
                                   Conventional CI
                               Correct        Incorrect
  Component 4    Correct         49 (a)           3 (b)     |   52
               Incorrect          5 (c)           3 (d)     |    8
                              ---------------------------
                                 54               6          |   60
```
- **Discordant Pairs ($b + c$)**: $8$ ($b = 3$, $c = 5$).
- **Component 4 Unique Wins ($b = 3$)**:
  - `PH3-HELD-035` (`performance_bottleneck`): Detected by C4 via latency SLA telemetry; missed by Conventional CI (exit code 0).
  - `PH3-HELD-054` (`semantic_drift`): Detected by C4 via AST assertion weakening inspection; missed by Conventional CI.
  - `PH3-HELD-060` (`semantic_drift`): Detected by C4 via drift guard; missed by Conventional CI.
- **Conventional CI Unique Wins ($c = 5$)**:
  - `PH3-HELD-002`, `PH3-HELD-030` (`clean_control`): Correctly passed by CI; C4 had false-positive boundary warnings.
  - `PH3-HELD-011` (`functional_bug`), `PH3-HELD-025`, `PH3-HELD-029` (`security_vulnerability`): Failed raw pytest assertions (CI detected); C4 had classification misalignments.

#### Consolidated Benchmark ($N = 100$)
```
                                   Conventional CI
                               Correct        Incorrect
  Component 4    Correct         81 (a)           5 (b)     |   86
               Incorrect          8 (c)           6 (d)     |   14
                              ---------------------------
                                 89              11          |  100
```
- **Discordant Pairs ($b + c$)**: $13$ ($b = 5$, $c = 8$).

### 3.3 Statistical Significance Calculation

When the number of discordant pairs $n = b + c < 25$, the large-sample asymptotic $\chi^2$ distribution is known to be approximate. We report both the **Exact Two-Tailed Binomial $p$-value** and the **Edwards Continuity-Corrected $\chi^2$ statistic**:

$$p_{\text{exact}} = 2 \cdot \sum_{k=0}^{\min(b, c)} \binom{b + c}{k} 0.5^{b + c}, \quad \chi^2 = \frac{(|b - c| - 1)^2}{b + c}$$

| Partition | Discordant Pairs ($b+c$) | Edwards $\chi^2$ | Asymptotic $p$-value | Exact Binomial $p$-value | Odds Ratio ($b/c$) | Statistically Significant ($\alpha = 0.05$)? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Held-Out ($N = 60$)** | 8 | $0.1250$ | $0.7237$ | **$0.7266$** | $0.60\times$ | **No** ($p > 0.05$) |
| **Consolidated ($N = 100$)** | 13 | $0.3077$ | $0.5791$ | **$0.5811$** | $0.62\times$ | **No** ($p > 0.05$) |

### 3.4 Conceptual Distinction: Accuracy vs. F1 Comparisons

1. **What McNemar's Test Actually Measures**:
   McNemar's test evaluates the null hypothesis $H_0: P(\text{C4 correct}) = P(\text{CI correct})$ on **Overall Binary Accuracy** across all scenarios. On this benchmark, clean controls comprise 26–30% of scenarios. Because Conventional CI automatically passes clean controls, it secures an effortless accuracy baseline ($90.0\%$ held-out, $89.0\%$ consolidated), resulting in no statistically significant accuracy difference ($p = 0.7266$).
2. **Why Accuracy is Methodologically Misleading**:
   Accuracy conceals Conventional CI's catastrophic failure modes: Conventional CI has **$0\%$ recall** on latency SLA bottlenecks and **$0\%$ recall** on test-suite semantic drift.
3. **F1-Score Comparison**:
   F1-score evaluates harmonic balance between Precision and Recall on the positive defect class ($P = \text{Defect}$). Component 4 achieves superior multiclass F1 ($0.842$) and binary F1 ($0.895$), while providing taxonomy categorization, physical line localization ($70\%$ near-line), and machine-readable repair feedback that Conventional CI physically cannot perform.

---

## 4. Confidence Interval Methodology & Recomputed Metrics (Task 3)

### 4.1 Methodology & Sampling Assumptions

- **Binomial Proportions**: Exact Wilson Score 95% Confidence Intervals are calculated for metrics that represent independent Bernoulli trials:
  - Accuracy ($k$ correct out of $N$ scenarios)
  - Precision ($TP$ out of $TP + FP$ predicted defects)
  - Recall ($TP$ out of $TP + FN$ actual defects)
- **Non-Linear F1 Scores**: Because F1-score is a non-linear harmonic mean ($2TP / (2TP + FP + FN)$), standard binomial intervals are theoretically invalid. We employ **Non-Parametric Bootstrap Resampling** ($B = 10,000$ iterations with fixed seed $42$) to compute empirical percentile 95% confidence intervals.
- **Paired Differences ($\Delta$)**: Resampling scenario triplets $(y_i, \hat{y}_{C4, i}, \hat{y}_{CI, i})$ jointly $B = 10,000$ times yields empirical confidence intervals for system deltas ($\Delta F_1 = F_{1, C4} - F_{1, CI}$ and $\Delta \text{Acc} = \text{Acc}_{C4} - \text{Acc}_{CI}$). A difference is statistically significant if and only if its 95% bootstrap interval excludes 0.

### 4.2 Recomputed Confidence Interval Table

| Partition | Metric | Component 4 Point Estimate | 95% Confidence Interval | Conventional CI Estimate | 95% Confidence Interval | Paired Delta ($\Delta$) | 95% Bootstrap CI on Delta |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Held-Out ($N = 60$)** | **Accuracy** | **0.867** | $[0.758, 0.931]$ (Wilson) | 0.900 | $[0.798, 0.953]$ (Wilson) | $-0.033$ | $[-0.133, +0.050]$ |
| | **Precision** | **0.944** | $[0.819, 0.985]$ (Wilson) | 0.935 | $[0.793, 0.982]$ (Wilson) | $+0.009$ | $[-0.083, +0.104]$ |
| | **Recall** | **0.850** | $[0.709, 0.929]$ (Wilson) | 0.725 | $[0.572, 0.839]$ (Wilson) | **$+0.125$** | $[-0.025, +0.275]$ |
| | **Binary F1** | **0.895** | $[0.812, 0.961]$ (Bootstrap) | 0.919 | $[0.844, 0.975]$ (Bootstrap) | $-0.024$ | $[-0.104, +0.054]$ |
| **Consolidated ($N = 100$)** | **Accuracy** | **0.860** | $[0.779, 0.915]$ (Wilson) | 0.890 | $[0.814, 0.938]$ (Wilson) | $-0.030$ | $[-0.100, +0.040]$ |
| | **Precision** | **0.952** | $[0.869, 0.984]$ (Wilson) | 0.942 | $[0.843, 0.974]$ (Wilson) | $+0.010$ | $[-0.052, +0.071]$ |
| | **Recall** | **0.845** | $[0.744, 0.911]$ (Wilson) | 0.797 | $[0.690, 0.874]$ (Wilson) | **$+0.048$** | $[-0.042, +0.141]$ |
| | **Binary F1** | **0.896** | $[0.836, 0.946]$ (Bootstrap) | 0.916 | $[0.862, 0.962]$ (Bootstrap) | $-0.021$ | $[-0.079, +0.036]$ |

> **Audit Conclusion**: Because all paired 95% bootstrap confidence intervals for $\Delta F_1$ and $\Delta \text{Acc}$ cross zero ($[-0.104, +0.054]$ and $[-0.133, +0.050]$), **no claim of statistical superiority on overall binary metrics is justified**. Component 4's research value rests entirely on capabilities that Conventional CI does not possess: taxonomy classification ($0.842$ multiclass F1), AST drift prevention, source line localization ($70\%$), and closed-loop repair feedback.

---

## 5. Performance-Agent Telemetry & Classification Audit (Task 4)

### 5.1 Verification of Workload Duration vs. Container Overhead

A critical audit issue was identified in performance telemetry accounting:
- **Finding**: Previously, `PerformanceMetrics.duration_ms` recorded the host wall-clock container execution time ($\sim 1.5\text{s} - 1.8\text{s}$), conflating Docker daemon initialization with code execution time.
- **Correction Implemented**:
  1. `PerformanceMetrics` now explicitly separates `workload_duration_ms` from `container_startup_overhead_ms`.
  2. `workload_duration_ms` is computed directly from inside the container via JUnit XML `<testcase time="...">` execution intervals ($\sum \text{durations}$), which measure only Python test call duration.
  3. `container_startup_overhead_ms` is recorded separately as $\text{total\_time\_ms} - \text{workload\_duration\_ms}$ ($\sim 1,200\text{ms} - 1,500\text{ms}$).

### 5.2 Elimination of Container Startup False-Triggering

In `agent_testing_service.py`, the breach condition previously contained `or total_time_ms > 1000.0`. Because virtually every Docker run exceeds 1.0s, this heuristic falsely flagged any scenario with an AST pattern as a performance breach regardless of actual execution speed.
- **Correction Implemented**: Removed `total_time_ms > 1000.0`. A performance breach strictly requires:
  - `p95 > latency_threshold_ms` (direct SLA threshold breach), OR
  - `exec_result.is_timeout` (container timeout under benchmark load), OR
  - Confirmed AST complexity pattern with **elevated workload execution duration** ($p95 \ge 50.0\text{ms}$ or scale test failure).
- **Validation**: Verified in `tests/test_performance_agent_hardening.py` across 6 targeted fixtures. A fast 2ms function with 1.8s container startup correctly reports `status="PASSED"` and `workload_duration_ms=2.0`.

### 5.3 Development-Only vs. Historical Held-Out Results

To avoid data leakage, performance agent tuning was evaluated strictly on the development partition:
- **Historical Held-Out Result (Frozen)**: Performance $F_1 = 0.500$ (Recall: $0.333$, Precision: $1.000$, $1/3$ detected). Preserved unchanged.
- **Development-Only Result (Hardened)**: Performance Recall reached **$1.000$ ($4/4$ detected)** with **$0.0\%$ False Positives (0/10)** on clean controls.

---

## 6. XAI Delivery Authorization & Gating Security (Task 5)

### 6.1 Backend-Enforced Authorization for Production Releases

The delivery confirmation endpoint (`POST /api/v1/verifications/{id}/delivery-confirmation`) was audited to prevent frontend requests from forging production releases:
1. **Mandatory Artifact Versioning**: Production delivery confirmation (`is_simulation=False`) requires an explicit `artifact_version` payload that matches `run.submission_id`. Omitting `artifact_version` triggers HTTP 400 (`requires explicit artifact_version`).
2. **Authorized Entity Enforcement**: Unprivileged or frontend callers (`"frontend_ui"`, `"unauthenticated_user"`, `"anonymous"`) attempting `is_simulation=False` are rejected with HTTP 400 (`not authorized to sign off production releases`). Production confirmations are accepted exclusively from authorized orchestrators (`"delivery_orchestrator"`, `"ci_cd_deployment"`, `"release_gate"`).
3. **Simulation Flag Isolation**: Frontend simulation requests (`is_simulation=True`) are explicitly tagged as simulation previews. They unlock explanation generation for evaluation purposes but cannot be presented or counted as genuine production deployments.

### 6.2 Content Hash & Reverification Invalidation

1. **SHA-256 Digest Matching**: During gate evaluation, `PostDeliveryXaiService` recomputes the SHA-256 digest of the current submission code. If the code was modified after delivery confirmation, the gate blocks with `BLOCKED_HASH_MISMATCH`.
2. **Re-Verification Invalidation**: Executing re-verification on an existing run automatically resets `delivery_confirmation = None`, guaranteeing that stale confirmations never persist across test cycles.

---

## 7. Regression Verification Evidence

All backend and frontend regression suites were executed following implementation:

```
backend: pytest tests/
================== 218 passed, 1 skipped in 53.42s ===================

frontend: npm test -- --run
Test Files  11 passed (11)
Tests       65 passed (65)
Duration    10.16s
```

All 218 backend tests and 65 frontend Vitest tests passed with zero regressions.

---

## 8. Unresolved Methodological Limitations & Research Implications

1. **Small Sample Constraints on Specialized Categories**:
   - The held-out benchmark contains 3 performance scenarios and 5 semantic drift scenarios. While sufficient for pilot verification, larger sample sizes ($N \ge 30$ per category) are required in Phase 3C to narrow bootstrap confidence intervals.
2. **Synthetic Microbenchmarks vs. Industrial Repositories**:
   - Current scenarios evaluate single-file algorithmic modules. Industrial software features distributed microservices and asynchronous message queues, requiring multi-container Docker compose environments in future work.
3. **LLM Explanations Dependency**:
   - Post-delivery explanations utilize deterministic AST parsing with optional local Ollama enrichment. If Ollama is unavailable, deterministic synthesis guarantees 100% availability but produces more formulaic summaries.
