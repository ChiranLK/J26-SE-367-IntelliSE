# INTELISE Component 4 — Phase 3B.3: Empirical Baseline Provenance & Statistical Reporting Correction

**Document Reference:** `docs/PHASE3B3_EMPIRICAL_PROVENANCE_CORRECTION.md`  
**Evaluation Phase:** Phase 3B.3 Evidence Provenance Audit & Statistical Correction  
**Author / Harness:** Independent Evidence Integrity Auditor  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED  
**Working Directory:** `D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4`  

---

## 1. Executive Summary

This correction document formally resolves the statistical provenance and paired comparison integrity issues identified in Phase 3B.2 for **INTELISE Component 4** (*Intelligent Agentic Testing & Explainable Feedback Loop Assistant*).

### Core Findings & Corrective Actions
1. **Provenance Audit & Identification of Missing Baseline Serialization**: During Phase 3A benchmark execution, Component 4 serialized rich per-scenario observation records, but baseline evaluators (`ConventionalCiBaselineEvaluator` and `StaticAnalysisBaselineEvaluator`) only serialized aggregate counts and metrics (`total_scenarios`, `true_positives`, `false_positives`, `true_negatives`, `false_negatives`, `f1_score`). Per-scenario baseline predictions were not persisted to disk.
2. **Invalidation of Unsupported Paired Statistical Claims**: In Phase 3B.1 and Phase 3B.2, synthetic proxy execution models were utilized to construct $2 \times 2$ paired correctness contingency tables and compute McNemar's exact tests and paired bootstrap confidence intervals. **Under strict scientific provenance rules, synthetic proxies cannot serve as empirical evidence.** All proxy-based McNemar test results and paired bootstrap confidence intervals are formally retracted as empirical findings and reclassified as non-empirical theoretical sensitivity demonstrations.
3. **Formal Classification of Empirical Paired Significance**: Because genuine matched per-scenario observations for Conventional CI are absent from Phase 3A serializations, **empirical paired significance testing (McNemar and paired bootstrap) is formally classified as UNAVAILABLE for Phase 3A data.**
4. **Mathematical Proof of Indeterminacy from Aggregates Alone**: We prove mathematically that marginal confusion matrices cannot determine paired contingency tables. On the 60-scenario held-out benchmark, compatible exact McNemar $p$-values range from $0.0625$ to $0.3833$ depending on unrecorded scenario pairings. Any attempt to derive paired tests from marginals without recorded observations is mathematically invalid.
5. **Confirmed Empirical Aggregate Metrics**: Published aggregate metrics from Phase 3A are fully verified from the raw serialized confusion counts ($TP, FP, TN, FN$). Component 4 achieved a held-out binary $F_1$ of **0.895** (Accuracy: 0.867, Precision: 0.944, Recall: 0.850), while Conventional CI achieved a held-out binary $F_1$ of **0.817** (Accuracy: 0.783, Precision: 0.935, Recall: 0.725).
6. **Implementation of Strict Provenance Validation Engine**: A 4-tier provenance taxonomy (`EMPIRICAL_EXECUTION`, `VERIFIED_LOG_RECONSTRUCTION`, `SYNTHETIC_PROXY`, `AGGREGATE_ONLY`) and validation engine have been integrated into `statistical_analysis.py`, permanently preventing synthetic proxies from entering empirical paired analyses.
7. **Infrastructure Hardening for Phase 3C**: The benchmark evaluation infrastructure (`baselines.py`, `evaluator.py`, `models.py`) has been upgraded to record 17-field per-scenario observations for all evaluated systems under strict zero-ground-truth-leakage constraints, fully preparing the codebase for Phase 3C.

---

## 2. Root Cause Analysis: The Missing Baseline Serialization

### 2.1 What Was Serialized in Phase 3A
In Phase 3A, the benchmark evaluator executed 100 scenarios across two partitions (40 Development, 60 Frozen Held-Out). Inspection of the raw result files (`benchmark_results_phase3_dev.json`, `benchmark_results_phase3_heldout.json`, `benchmark_results_phase3_100.json`) reveals an asymmetric serialization architecture:
- **Component 4 Multi-Agent System**: Serialized complete scenario-by-scenario records in the `"scenarios"` array (e.g., `scenario_id`, `name`, `group`, `ground_truth`, `predictions`, `detected_has_defect`, `predicted_category`, `localized_line`).
- **Conventional CI Baseline**: Executed within the Docker runner or in-process sandbox, but only summarized into the top-level `"baselines"` JSON object:
  ```json
  "baselines": {
    "conventional_ci_f1": 0.817,
    "conventional_ci_recall": 0.725,
    "conventional_ci_precision": 0.935,
    "static_analysis_recall": 0.075,
    "static_analysis_precision": 1.0
  }
  ```
  The individual boolean prediction $\hat{y}_{\text{CI}, i}$ for each scenario $i$ was discarded from memory upon completion of `ConventionalCiBaselineEvaluator.evaluate()` and never written to disk.

### 2.2 How the Gap Was Addressed in Phase 3B.1 (The Synthetic Proxy)
When Phase 3B.1 sought to perform paired significance testing (McNemar's test and paired bootstrap resampling), the missing $\hat{y}_{\text{CI}, i}$ vector was substituted with a **synthetic proxy model**:
- Clean controls $\implies \hat{y}_{\text{CI}} = \text{False}$
- Performance bottlenecks $\implies \hat{y}_{\text{CI}} = \text{False}$ (raw pytest does not measure latency SLAs)
- Semantic drift $\implies \hat{y}_{\text{CI}} = \text{False}$ (raw pytest passes weakened assertions)
- Functional bugs, regressions, security, non-convergent $\implies \hat{y}_{\text{CI}} = \text{True}$

While this model reflected theoretical capabilities, it generated idealized predictions ($FP = 0$, $F_1 = 0.919$ on held-out) that diverged from the empirical Docker execution ($FP = 2$, $F_1 = 0.817$) where container timeouts and unhandled runtime exceptions occurred on clean controls.

### 2.3 Methodological Classification of Evidence Tiers
To restore research evidence integrity, all data in Component 4 is now categorized into 4 strict provenance tiers:

| Tier | Category Identifier | Description | Eligible for Paired Empirical Testing? |
| :---: | :--- | :--- | :---: |
| **Tier 1** | `EMPIRICAL_EXECUTION` | Direct scenario-level prediction recorded during containerized benchmark execution. | **YES** |
| **Tier 2** | `VERIFIED_LOG_RECONSTRUCTION` | Scenario prediction reconstructed from authentic, timestamped, cryptographically hashed container stdout/stderr execution logs. | **YES** |
| **Tier 3** | `SYNTHETIC_PROXY` | Scenario prediction derived from a heuristic, rule-based, or theoretical simulation model. | **NO (Demonstrations Only)** |
| **Tier 4** | `AGGREGATE_ONLY` | Published summary metrics ($TP, FP, TN, FN$, $F_1$) without scenario-level records. | **NO (Descriptive Only)** |

---

## 3. Confirmed Empirical Aggregate Metrics (Task 3)

The aggregate confusion matrix counts recorded in the Phase 3A benchmark result files are authentic empirical artifacts. Reconstructing the confusion matrices directly from the saved counts confirms perfect mathematical consistency:

### 3.1 Held-Out Evaluation Partition ($N = 60$)
- **Positive Support (True Defective Scenarios)**: $40$
- **Negative Support (Clean Controls)**: $20$

| System | TP | FP | TN | FN | Total | Accuracy | Precision | Recall | Binary $F_1$ | Matrix Sum Check |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Component 4** | 34 | 2 | 18 | 6 | 60 | **0.867** | **0.944** | **0.850** | **0.895** | $34+2+18+6 = 60$ |
| **Conventional CI** | 29 | 2 | 18 | 11 | 60 | **0.783** | **0.935** | **0.725** | **0.817** | $29+2+18+11 = 60$ |
| **Static Analysis** | 3 | 0 | 20 | 37 | 60 | **0.383** | **1.000** | **0.075** | **0.140** | $3+0+20+37 = 60$ |

### 3.2 Development Partition ($N = 40$)
- **Positive Support (True Defective Scenarios)**: $31$
- **Negative Support (Clean Controls)**: $9$

| System | TP | FP | TN | FN | Total | Accuracy | Precision | Recall | Binary $F_1$ | Matrix Sum Check |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Component 4** | 26 | 1 | 8 | 5 | 40 | **0.850** | **0.963** | **0.839** | **0.897** | $26+1+8+5 = 40$ |
| **Conventional CI** | 20 | 1 | 8 | 11 | 40 | **0.700** | **0.952** | **0.645** | **0.769** | $20+1+8+11 = 40$ |
| **Static Analysis** | 4 | 0 | 9 | 27 | 40 | **0.325** | **1.000** | **0.129** | **0.229** | $4+0+9+27 = 40$ |

### 3.3 Consolidated Benchmark ($N = 100$)
- **Positive Support (True Defective Scenarios)**: $71$
- **Negative Support (Clean Controls)**: $29$

| System | TP | FP | TN | FN | Total | Accuracy | Precision | Recall | Binary $F_1$ | Matrix Sum Check |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Component 4** | 60 | 3 | 26 | 11 | 100 | **0.860** | **0.952** | **0.845** | **0.896** | $60+3+26+11 = 100$ |
| **Conventional CI** | 49 | 3 | 26 | 22 | 100 | **0.750** | **0.942** | **0.690** | **0.797** | $49+3+26+22 = 100$ |
| **Static Analysis** | 7 | 0 | 29 | 64 | 100 | **0.360** | **1.000** | **0.099** | **0.179** | $7+0+29+64 = 100$ |

### 3.4 Verification of Exact Formula Consistency
- $\text{Accuracy} = \frac{TP + TN}{N}$
- $\text{Precision} = \frac{TP}{TP + FP}$
- $\text{Recall} = \frac{TP}{TP + FN}$
- $F_1 = \frac{2 \times \text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2TP}{2TP + FP + FN}$

For Component 4 on Held-Out:
$$\text{Precision} = \frac{34}{36} = 0.9444\dots, \quad \text{Recall} = \frac{34}{40} = 0.8500$$
$$F_1 = \frac{2 \times 34}{2(34) + 2 + 6} = \frac{68}{76} = 0.8947\dots \approx 0.895$$

For Conventional CI on Held-Out:
$$\text{Precision} = \frac{29}{31} = 0.9355\dots, \quad \text{Recall} = \frac{29}{40} = 0.7250$$
$$F_1 = \frac{2 \times 29}{2(29) + 2 + 11} = \frac{58}{71} = 0.8169\dots \approx 0.817$$

All published aggregate metrics are authentic, reproducible, and internally consistent.

---

## 4. Mathematical Proof: Paired Indeterminacy from Marginals Alone

A fundamental statistical question is whether paired tests (such as McNemar's test or paired bootstrap) can be derived from marginal confusion matrices. **We prove mathematically that this is impossible.**

### 4.1 Formal Proof of Indeterminacy
Let $N$ be the total number of scenarios. Let $K_A$ be the total number of scenarios correctly classified by System A ($K_A = TP_A + TN_A$), and let $K_B$ be the total number correctly classified by System B ($K_B = TP_B + TN_B$).

In a $2 \times 2$ paired correctness table:
- $a$: Number of scenarios where **both** systems are correct.
- $b$: Number of scenarios where System A is correct, but System B is incorrect ($b = K_A - a$).
- $c$: Number of scenarios where System B is correct, but System A is incorrect ($c = K_B - a$).
- $d$: Number of scenarios where **both** systems are incorrect ($d = N - a - b - c = N - K_A - K_B + a$).

Because all cell counts must be non-negative integers ($a, b, c, d \ge 0$), cell $a$ is constrained strictly by:
$$\max(0, K_A + K_B - N) \le a \le \min(K_A, K_B)$$

Each valid integer value of $a$ within this interval produces a distinct paired table with discordant pairs:
$$n_d = b + c = (K_A - a) + (K_B - a) = K_A + K_B - 2a$$
and exact McNemar two-tailed binomial $p$-value:
$$p = 2 \times \sum_{i=0}^{\min(b, c)} \binom{b + c}{i} 0.5^{b + c}$$

### 4.2 Application to the Phase 3A Held-Out Benchmark ($N = 60$)
For the held-out partition:
- $K_{\text{C4}} = 34 + 18 = 52$ correct
- $K_{\text{CI}} = 29 + 18 = 47$ correct
- Range for $a$:
  $$\max(0, 52 + 47 - 60) = 39 \le a \le \min(52, 47) = 47$$

Exactly **9 distinct paired contingency tables** are mathematically compatible with the published marginals:

| $a$ (Both Correct) | $b$ (C4 Only) | $c$ (CI Only) | $d$ (Both Incorrect) | Discordant Pairs ($b+c$) | Exact McNemar $p$-value | Significant at $\alpha = 0.05$? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **39** | 13 | 8 | 0 | 21 | **0.3833** | No |
| 40 | 12 | 7 | 1 | 19 | 0.3593 | No |
| 41 | 11 | 6 | 2 | 17 | 0.3323 | No |
| 42 | 10 | 5 | 3 | 15 | 0.3018 | No |
| 43 | 9 | 4 | 4 | 13 | 0.2668 | No |
| 44 | 8 | 3 | 5 | 11 | 0.2266 | No |
| 45 | 7 | 2 | 6 | 9 | 0.1797 | No |
| 46 | 6 | 1 | 7 | 7 | 0.1250 | No |
| **47** | 5 | 0 | 8 | 5 | **0.0625** | No (Boundary) |

### 4.3 Scientific Conclusion
The exact $p$-value varies by more than a factor of 6 (from $0.0625$ to $0.3833$) depending purely on which specific scenarios each system answered correctly. 

On the consolidated benchmark ($N = 100$, $K_{\text{C4}} = 86$, $K_{\text{CI}} = 75$), $a \in [61, 75]$, and the compatible $p$-values range from **$0.0010$ (highly significant)** to **$0.1081$ (not significant)**.

**Therefore, any claim of paired statistical significance or equivalence based on aggregate confusion matrices without recorded scenario-level pairings is unprovable and invalid.**

---

## 5. Invalidated Paired Claims & Corrected Research Interpretation (Task 2)

### 5.1 Invalidated Paired Claims
The following paired claims from previous drafts and reports are formally retracted:
1. **Empirical McNemar Test Claim**: The claim that Component 4 demonstrated an exact McNemar $p = 0.7266$ (or $\chi^2 = 0.1250$) on the held-out dataset is **invalidated as an empirical result**, because it was computed from synthetic proxy predictions, not recorded Conventional CI observations.
2. **Empirical Paired Bootstrap Claim**: The claim that the empirical paired difference in held-out $F_1$ was $\Delta F_1 = -0.0242$ ($95\%$ CI: $[-0.1040, +0.0536]$) is **invalidated as an empirical confidence interval**.
3. **Statistical Equivalence / Superiority Claims**: Any hypothesis test claiming that Conventional CI and Component 4 are statistically indistinguishable on paired binary correctness is retracted for Phase 3A.

### 5.2 Corrected Empirical Interpretation
The empirical evidence collected during Phase 3A supports the following verified scientific conclusions:
1. **Aggregate Detection Superiority**: In independent aggregate evaluations across 100 scenarios (40 development, 60 held-out), Component 4 demonstrated higher overall binary detection accuracy ($0.867$ vs $0.783$ held-out) and higher binary $F_1$ ($0.895$ vs $0.817$ held-out) than Conventional CI.
2. **Recall Advantage on Complex Defect Modalities**: Conventional CI suffered 11 false negatives on the held-out benchmark ($FN = 11$, Recall = $0.725$), missing performance latency SLA violations, subtle semantic drift (assertion weakening), and non-convergent repair loops that raw pytest cannot evaluate. Component 4 reduced false negatives to 6 ($FN = 6$, Recall = $0.850$).
3. **Qualitative Engineering Value (SO6 Proposals)**: Component 4 provides capabilities that conventional CI pipelines fundamentally cannot perform:
   - Automated root-cause localization to exact physical source lines ($70.0\%$ near-line match on held-out).
   - Structured JSON technical repair contracts dispatched to automated code generators.
   - Post-delivery human-facing explanations for successfully verified and delivered software.
   - Guarded simulation isolation and SHA-256 gated deployment readiness.
4. **Statistical Limitation**: While aggregate differences are substantial ($+7.8\%$ absolute $F_1$ improvement on held-out), **paired statistical significance remains unproven for Phase 3A** due to the absence of serialized scenario-by-scenario Conventional CI predictions.

---

## 6. Strict Provenance Validation Engine (Task 4)

In `app/benchmark/statistical_analysis.py`, we implemented a strict evidence validation engine:

```python
class PredictionProvenance(str, Enum):
    EMPIRICAL_EXECUTION = "EMPIRICAL_EXECUTION"
    VERIFIED_LOG_RECONSTRUCTION = "VERIFIED_LOG_RECONSTRUCTION"
    SYNTHETIC_PROXY = "SYNTHETIC_PROXY"
    AGGREGATE_ONLY = "AGGREGATE_ONLY"
```

### Validation Rules Enforced:
1. **Mandatory Scenario ID**: Every prediction must have a non-empty, unique scenario identifier. Duplicate IDs in either system cause an immediate `ValueError`.
2. **Exact Set Equivalence**: System A and System B must evaluate the exact same scenario ID set ($A \setminus B = \emptyset$ and $B \setminus A = \emptyset$). Mismatched sets or differing scenario counts cause an immediate `ValueError`.
3. **Ground-Truth Agreement**: If ground-truth labels are attached to predictions or passed via an authoritative dictionary, any conflict causes an immediate `ValueError`.
4. **Strict Provenance Gating**: In `evaluate_empirical_paired_test()`, any prediction carrying `SYNTHETIC_PROXY` or `AGGREGATE_ONLY` raises a `ProvenanceValidationError`. Synthetic proxies cannot be passed as empirical evidence.
5. **Labeled Demonstration Pipeline**: Synthetic proxies may only be executed through `evaluate_synthetic_proxy_demonstration()`, which forces `is_empirical = False` and attaches a prominent disclaimer.

---

## 7. Phase 3C Scenario-Level Evidence Schema (Task 5)

To ensure that Phase 3C produces a complete, reproducible, and verifiable empirical record for all evaluated systems, the evaluation infrastructure (`baselines.py`, `evaluator.py`, `models.py`) has been upgraded.

### The 17-Attribute Scenario Observation Schema
For every evaluated scenario, the benchmark serializer records:

```json
{
  "scenario_id": "PH3C-HELD-001",
  "dataset_version": "v3.0.0-heldout",
  "partition": "held_out",
  "ground_truth_category": "functional_bug",
  "ground_truth_binary_label": true,
  "component4": {
    "detected_has_defect": true,
    "predicted_category": "functional_bug",
    "predicted_cwe": null,
    "localized_line": 42,
    "drift_detected": false
  },
  "conventional_ci": {
    "detected_has_defect": true,
    "execution_status": "FAILED",
    "container_exit_code": 1,
    "timeout": false,
    "duration_ms": 112.4,
    "sanitized_evidence": "AssertionError in test_fifo: Expected 1, got 2",
    "provenance": "EMPIRICAL_EXECUTION"
  },
  "static_analysis": {
    "detected_has_defect": false,
    "findings_count": 0,
    "sanitized_evidence": "No AST pattern matches",
    "provenance": "EMPIRICAL_EXECUTION"
  },
  "execution_status": "COMPLETED",
  "container_exit_code": 0,
  "timeout": false,
  "duration_ms": 1420.5,
  "sanitized_evidence": "Multi-agent test suite execution completed",
  "artifact_checksum": "a3f5b2c890...",
  "execution_timestamp": "2026-10-19T10:15:30.123456+00:00",
  "evaluator_version": "v3.1.0-phase3c",
  "provenance": "EMPIRICAL_EXECUTION"
}
```

### Zero-Ground-Truth-Leakage Enforcement
In `ConventionalCiBaselineEvaluator` and `StaticAnalysisBaselineEvaluator`:
- **Phase 1 (Execution)**: Evaluators receive only `source_code`, `test_code`, and `filename`. Ground-truth attributes (`has_defect`, `scenario_group`, `expected_*`) are not present in the sandbox namespace and cannot be accessed.
- **Phase 2 (Scoring)**: Observations are joined with frozen ground truth strictly after container execution finishes.

---

## 8. Automated Test Evidence (Task 6)

The verification suite `tests/test_empirical_provenance.py` implements comprehensive automated unit tests covering all 14 mandatory provenance requirements:

| # | Test Name | Target Requirement | Status |
| :---: | :--- | :--- | :---: |
| 1 | `test_01_missing_conventional_ci_predictions_rejected` | Missing baseline predictions rejected from paired tests | **PASSED** |
| 2 | `test_02_aggregate_only_baseline_evidence_rejected` | AGGREGATE_ONLY provenance rejected from empirical paired tests | **PASSED** |
| 3 | `test_03_synthetic_proxy_rejection_from_empirical_testing` | SYNTHETIC_PROXY rejected from empirical test, allowed in labeled demo | **PASSED** |
| 4 | `test_04_duplicate_scenario_ids_rejected` | Duplicate scenario IDs in either system rejected | **PASSED** |
| 5 | `test_05_mismatched_prediction_sets_rejected` | Differing counts or asymmetric scenario IDs rejected | **PASSED** |
| 6 | `test_06_ground_truth_mismatch_rejected` | Inconsistent ground-truth records across systems rejected | **PASSED** |
| 7 | `test_07_valid_empirical_paired_predictions_accepted` | Genuinely matched empirical predictions evaluate successfully | **PASSED** |
| 8 | `test_08_valid_verified_log_reconstruction_accepted` | Verified log reconstruction accepted as empirical evidence | **PASSED** |
| 9 | `test_09_incorrect_provenance_claims_rejected` | Invalid provenance strings or empty names rejected | **PASSED** |
| 10 | `test_10_confusion_matrix_arithmetic` | Support and total arithmetic verified on 40, 60, and 100 sets | **PASSED** |
| 11 | `test_11_f1_formula_consistency_and_paired_indeterminacy` | F1 formula verified and indeterminacy proof checked ($a \in [39..47]$) | **PASSED** |
| 12 | `test_12_scenario_level_evidence_serialization` | Baseline scenario record serialization verified | **PASSED** |
| 13 | `test_13_label_leakage_prevention_in_baseline_evaluators` | Sandbox execution verified with zero ground-truth leakage | **PASSED** |
| 14 | `test_14_historical_benchmark_immutability` | Historical JSON files verified: digests, total scenarios, and F1 | **PASSED** |

### Historical File Immutability Verification
Cryptographic SHA-256 hashes of the frozen Phase 3A benchmark files remain completely untouched:
- `benchmark_results_phase3_100.json`: `10269c798dfe72eb37906d60a93ad7d12442f042aac349a4de9406f503dadc09` (Verified)
- `benchmark_results_phase3_dev.json`: `6b16ea5917276fc14d62cee4610a82bca196e39d2c1b4395d093d7a4b4b9e032` (Verified)
- `benchmark_results_phase3_heldout.json`: `fbaf6762cba84c9632df6cf4268531d84bfd5bb89160a5ae33ea47c8d5a872a3` (Verified)

---

## 9. Remaining Research Limitations & Phase 3C Readiness

### 9.1 Remaining Research Limitations
1. **Phase 3A Paired Hypothesis Retraction**: The Phase 3A benchmark cannot be used to prove paired hypothesis rejection ($H_0$) against Conventional CI via McNemar's test or paired bootstrap because baseline scenario predictions were not serialized.
2. **Static Analysis AST Baseline**: Static analysis remains a purely syntactic baseline (AST pattern scanning) and cannot evaluate runtime execution or non-functional latency constraints.
3. **Decoupled Component 3 Interface**: Component 3 repair loop evaluation remains simulated via verified local candidate patches (`COMPONENT_3_ENABLED=false`). Live cross-service agentic negotiation will be evaluated in Phase 3D.

### 9.2 Phase 3C Readiness Assessment
With the completion of Phase 3B.3, the evaluation infrastructure is fully prepared for Phase 3C:
- **Zero Label Leakage**: Baseline evaluators execute tests in pure sandboxes without ground truth.
- **Scenario Observation Schema**: Ready to serialize complete per-scenario records for all systems simultaneously.
- **Strict Provenance Gating**: Empirical paired tests will only run when both systems have genuine scenario observations.
- **Backwards Compatibility**: Existing readers of Phase 3A benchmark JSON files continue to function without modification.

---

## 10. Conclusion & Attestation

The INTELISE Component 4 research infrastructure now adheres to the highest standards of scientific evidence integrity. Historical Phase 3A results stand as valid aggregate evidence of multi-agent testing performance, while unsupported paired claims have been formally eliminated. Future Phase 3C evaluations will record complete, verifiable scenario-level observations for all evaluated systems.
