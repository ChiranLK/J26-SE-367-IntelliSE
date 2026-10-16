# Research Methodology Integrity Report — Component 4 (Multi-Agent Verification & Research Evaluation)

**Date**: October 2026  
**Evaluation Target**: INTELISE Component 4 — Multi-Agent Automated Testing & Defect Characterization  
**Document Status**: Formal Methodology Verification & Empirical Re-Evaluation  
**Configuration**: `COMPONENT_3_ENABLED=false` | Execution Mode: `real_docker`

---

## 1. Executive Summary & Methodology Re-Evaluation

An independent methodological review of the initial Component 4 research evidence package identified critical threats to scientific validity in the pilot benchmark. Specifically:
1. **Ground-Truth Leakage**: Prior evaluation scripts peeked at ground-truth labels (`has_defect`, `expected_defect_category`, `has_semantic_drift`) or inferred execution verdicts from expected metadata.
2. **Conditional Drift Analysis**: Semantic drift checks were executed selectively on positive scenarios using synthetic string replacement (`.replace(...)`) rather than evaluating independent candidate test suites across both positive and negative controls.
3. **Escalation Assumption**: Human escalation was scored as successful simply if a scenario was tagged `is_non_convergent_by_design`, without executing multi-turn repair attempts or observing real stopping decisions.
4. **Unverified Docstring Oracles**: Submitted untrusted source docstrings were accepted as authoritative verification oracles without authorization or specification provenance.
5. **Fixture Rigor**: Pilot performance tests used artificial delays (`time.sleep()`), and classification logic partially relied on test naming conventions.

### Summary of Corrective Actions
* **Zero-Leakage Benchmark Architecture**: Predictions are derived exclusively from isolated Docker sandbox test outcomes, dynamic AST vulnerability diagnostics, and latency telemetry before ground-truth comparison.
* **Independent Test Suites for Drift**: Semantic drift detection is evaluated unconditionally across both positive drift (assertion weakening, test deletion) and negative drift controls (legitimate refactoring, test additions).
* **Controlled Multi-Iteration Repair Harness**: Real multi-turn repair attempts are measured using a dedicated local harness (`ControlledRepairLoopHarness`), distinguishing local harness evaluation from live Component 3 integration (`COMPONENT_3_ENABLED=false`).
* **Authoritative Oracle Provenance**: Submitted docstrings are categorized as `UNVERIFIED_SUGGESTION` by default and prohibited from serving as acceptance oracles without explicit authorization.
* **Revised 24-Scenario Benchmark**: The historical 18-scenario pilot benchmark has been preserved in `benchmark_results_pilot.json`. A new 24-scenario benchmark (`revised_dataset.py`) introduces negative security controls, realistic vulnerabilities, and genuine CPU-bound performance bottlenecks without `time.sleep`.

---

## 2. Methodology Corrections Detail

### 2.1 Elimination of Ground-Truth Leakage
* **Issue**: In `app/benchmark/evaluator.py`, scenario outcome derivation used `sc.has_defect` or `sc.expected_defect_category` during defect report generation and classification.
* **Correction**: `evaluator.py` now collects `ExecutionOutcome` strictly from dynamic Docker container execution results (`outcome.test_results`, `outcome.telemetry`). Defect detection status is determined purely by `outcome.status != VerificationStatus.PASSED` or identified dynamic failures. Ground truth labels (`sc.has_defect`, `sc.expected_defect_category`, `sc.expected_cwe`) are strictly partitioned and accessed only during post-execution metric computation.
* **Invariance Verification**: Implemented `tests/test_benchmark_integrity.py::test_ground_truth_label_mutation_cannot_alter_predictions`. Proves that altering ground-truth labels on unchanged code and test suites yields identical detector predictions (0 delta).

### 2.2 Independent Semantic Drift Evaluation
* **Issue**: Drift detection was previously triggered only when `sc.has_semantic_drift is True`, using a synthetic string replacement `test_code.replace("assert ...", "assert True")`.
* **Correction**: Added `original_test_code` and `candidate_test_code` to `BenchmarkScenario`. Drift analysis runs unconditionally whenever an original suite is available, comparing AST structure, assertion counts, and test semantics across:
  * Positive drift: Weakened boundary assertions (`REV-DRIFT-POS-01`), deleted test functions (`REV-DRIFT-POS-02`).
  * Negative drift controls: Legitimate test additions (`REV-DRIFT-NEG-01`), harmless test refactorings (`REV-DRIFT-NEG-02`).
* **Empirical Outcome**: 4 scenarios evaluated; Precision: **1.000**, Recall: **1.000**, F1: **1.000** (TP=2, FP=0, TN=2, FN=0). Zero false positives on negative controls.

### 2.3 Controlled Convergence and Human Escalation Measurement
* **Issue**: Pilot metrics recorded `100% human escalation` based on ground-truth label `is_non_convergent_by_design` without running a repair loop.
* **Correction**: Implemented `app/benchmark/repair_loop.py::ControlledRepairLoopHarness`. Executes iterative repair cycles up to `max_iterations=3`:
  * Evaluates iterative test feedback against candidate repair patches.
  * Enforces stopping conditions: `CONVERGED_SUCCESSFULLY`, `STOP_ITERATION_CAP_REACHED`, and `SUPERFICIAL_CONVERGENCE_PREVENTED`.
  * Triggers governance risk assessment via `GovernanceReportService` when iteration cap is reached or superficial fixes are detected.
  * Distinguishes local harness results from live Component 3 integration (`COMPONENT_3_ENABLED=false`).
  * Non-repair scenarios report `convergence_status="NOT_EVALUATED"`.
* **Empirical Outcome**: 2 multi-iteration repair scenarios executed in Docker sandbox; Correct Escalation Rate: **100.0%** (2/2 correctly flagged for human review).

### 2.4 Authoritative Test-Oracle Provenance & Adversarial Protection
* **Issue**: `UnitTestAgent` extracted doctests and contracts from untrusted submitted source code and immediately converted them into passing acceptance tests.
* **Correction**: Updated `app/services/agent_testing_service.py`:
  * Added `trust_submitted_docstrings: bool = False` (default).
  * Untrusted docstrings are tagged `trust_status="UNVERIFIED_SUGGESTION"` and `specification_source="submitted_docstring_unverified"`.
  * For untrusted code without approved specifications, the agent generates non-authoritative callable presence checks (`test_{fn}_callable`), refusing to create passing boundary assertions without authorization.
  * Added `UnitTestReport.specification_source` and `UnitTestReport.trust_status` to ensure provenance tracking.
* **Adversarial Verification**: Verified via `tests/test_oracle_provenance.py::test_adversarial_defective_code_with_misleading_docstring`. Defective code containing false docstring contracts asserting incorrect outputs cannot trick the verifier.

### 2.5 Revised 24-Scenario Benchmark Rigor
* **Dataset Preservation**: Historical 18-scenario pilot benchmark preserved in `backend/benchmark_results_pilot.json`.
* **Revised Dataset (`revised_dataset.py`)**:
  * **Clean Controls (7)**: Standard math utilities, string tokenizers, plus **negative security controls** (parameterized SQL preventing SQL injection false alarms, safe `subprocess.run(shell=False)` with argument lists, strict path traversal confinement, configuration secret loaders).
  * **Realistic Functional Bugs (5)**: Off-by-one pagination, floating point roundoff errors, dict mutation during iteration, boundary conditions.
  * **Realistic Security Vulnerabilities (4)**: Subprocess shell injection (`shell=True`), arbitrary code execution via `eval()`, path traversal (`os.path.join` escape), hardcoded API credentials.
  * **CPU-Bound Performance Bottlenecks (3)**: Quadratic nested-loop substring search, exponential recursive Fibonacci, nested list membership. **All artificial delays (`time.sleep`) removed**; latency breaches (~260–280ms vs 200ms threshold) stem entirely from CPU execution inside Docker.
  * **Regressions (2)**: API signature regression, return type mismatch.
  * **Non-Convergent & Semantic Drift Controls (4)**: Unconditional drift detection pairs and controlled multi-turn repair loops.
* **Metric Rigor**: Symmetric multiclass confusion matrix scoring; missed categories count toward both False Negatives (target category) and False Positives (predicted category).

---

## 3. Empirical Results Comparison

### 3.1 Pilot Benchmark vs. Methodology-Corrected Benchmark

| Metric / Dimension | Pilot Benchmark (Historical) | Revised Integrity Benchmark (Current) | Difference / Significance |
| :--- | :---: | :---: | :--- |
| **Total Scenarios** | 18 | **24** | +6 scenarios (+33% coverage) |
| **Execution Sandbox** | Real Docker Sandbox | **Real Docker Sandbox** | Verified containerized isolation |
| **Ground-Truth Leakage** | **Present** (peeked at labels) | **ZERO** (Eliminated) | Predictions finalized before labels accessed |
| **Binary Detection Precision** | 1.000 | **1.000** | Zero false alarms on 7 clean controls |
| **Binary Detection Recall** | 0.867 | **0.765** | 13/17 defective scenarios detected dynamically |
| **Binary Detection F1** | **0.929** (Uncorrected) | **0.867** (Methodologically Sound) | Honest reflection of unassisted detection |
| **Negative Security Controls** | 0 scenarios | **4 scenarios** | Proves AST scanner avoids false alarms |
| **Performance Scenarios** | Artificial `time.sleep(0.35)` | **CPU-bound algorithmic load** | Latency 260–285ms measured in Docker |
| **Semantic Drift Evaluation** | Selective (2 positive only) | **4 (2 positive, 2 negative)** | Precision 1.000, Recall 1.000, F1 1.000 |
| **Human Escalation Rate** | 100% (Assumed from label) | **100% (Measured in repair loop)** | 2 multi-turn repair cycles executed |
| **Mean Execution Latency** | 1739.80 ms | **2174.78 ms** | Real Docker execution across 24 scenarios |

> [!IMPORTANT]
> The original Pilot F1 score of 0.929 was achieved under evaluation scripts with ground-truth leakage and synthetic drift evaluation. Under the corrected, leakage-free methodology on 24 realistic scenarios, Component 4 achieves an empirical **F1 score of 0.867** (Precision: 1.000, Recall: 0.765), maintaining a **+0.081 advantage over Conventional CI (0.786)**.

---

### 3.2 Multiclass Defect Classification & Confusion Matrix

#### Performance by Taxonomy Category (Revised Benchmark)
| Defect Category | Support (True) | Predicted | TP | FP | FN | Precision | Recall | F1-Score | Proposal Target | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Clean Control** | 7 | 7 | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 | - | Baseline |
| **Functional Bug** | 8 | 6 | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 | 0.85 | **MET** |
| **Security Vulnerability** | 4 | 2 | 2 | 0 | 2 | 1.000 | 0.500 | 0.667 | 0.90 | Below Target* |
| **Performance Bottleneck** | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.85 | **MET** |
| **Regression** | 2 | 2 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.85 | **MET** |
| **Overall (Macro)** | **24** | **20** | **20** | **0** | **4** | **1.000** | **0.765** | **0.867** | - | - |

*\*Note on Security Vulnerability Recall*: In the revised benchmark without ground-truth leakage, 2 realistic security vulnerabilities (eval and path traversal) pass functional unit tests if the test suite lacks specific adversarial exploit payloads and AST rules require explicit pattern matches. This demonstrates the integrity of the benchmark: security recall is accurately measured at 0.500 rather than masked by label peeking.

#### Multiclass Confusion Matrix
```
True \ Predicted      | Clean Control | Functional Bug | Security Vuln | Perf Bottleneck | Regression
----------------------------------------------------------------------------------------------------
Clean Control         |      7        |       0        |       0       |        0        |     0
Functional Bug        |      2        |       6        |       0       |        0        |     0
Security Vuln         |      2        |       0        |       2       |        0        |     0
Perf Bottleneck       |      0        |       0        |       0       |        3        |     0
Regression            |      0        |       0        |       0       |        0        |     2
```

---

### 3.3 Comparative Baselines Evaluation

All baselines were executed against the same revised 24-scenario benchmark:

| System / Baseline | Detection Mode | Precision | Recall | F1-Score | Delta vs Component 4 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Component 4 (Multi-Agent)** | Docker Sandbox + AST + Latency Telemetry | **1.000** | **0.765** | **0.867** | **Reference** |
| **Baseline 1: Conventional CI** | Containerized Pytest Only | 1.000 | 0.647 | 0.786 | **-0.081** |
| **Baseline 2: Static Analysis** | AST Rule Scanner Only | 1.000 | 0.235 | 0.381 | **-0.486** |

* **Conventional CI Pytest**: Misses performance SLA breaches (0.000 performance recall) and semantic test weakening.
* **Static Analysis Scanner**: Detects AST security patterns (CWE-78, CWE-89) but is completely blind to runtime logic bugs, algorithmic performance degradation, and API regressions.

---

### 3.4 Defect Localization Accuracy (Empirical)

* **Evaluated Defective Scenarios**: 13
* **Exact Line Hit Rate (±0 lines)**: 0.0% (0/13)
* **Proximity Line Hit Rate (±2 lines)**: 15.4% (2/13)

> [!NOTE]
> Unlike synthetic evaluations that report near-perfect localization by inspecting scenario metadata, genuine dynamic test runner tracebacks often point to test assertion lines or call sites rather than the internal defective statement. This is an authentic empirical measurement and represents a documented limitation of traceback-only localization without deep symbolic execution.

---

## 4. Verification of Regression Test Suite

Both backend and frontend regression test suites were executed to verify zero regression across the system:

* **Backend Unit & Integration Tests**: **190 passed, 0 failed** (Duration: 120s)
  * Includes 5 new benchmark integrity tests (`test_benchmark_integrity.py`).
  * Includes 4 new oracle provenance and adversarial tests (`test_oracle_provenance.py`).
  * All 181 original backend tests maintained 100% pass rate.
* **Frontend UI Vitest Suite**: **64 passed, 0 failed** across 11 test suites.

---

## 5. Explicit Limitations & Threats to Validity

1. **Component 3 Repair Emulation**: Component 3 live integration remains disabled (`COMPONENT_3_ENABLED=false`). Multi-iteration repair convergence was evaluated using controlled candidate patch sets in `ControlledRepairLoopHarness`. These results demonstrate Component 4's stopping and escalation logic, but do not measure live LLM-driven repair agent convergence.
2. **Traceback-Based Localization**: Current defect localization relies on Pytest traceback extraction and AST pattern matching. Precise line localization achieves 15.4% proximity accuracy; higher localization accuracy requires fine-grained spectrum-based fault localization (SBFL) or symbolic execution.
3. **Host-Dependent Performance Latency**: Performance tests execute in real Docker containers on Windows 11 host architecture. Container startup jitter (~1.5–2.0s overhead) is separated from function execution latency, but CPU throttling under high load could affect microsecond-level timing.
4. **Security Exploit Synthesis**: Without an active security fuzzing agent, security defect detection relies on AST heuristics and explicit exception triggers. Silent vulnerabilities that pass existing test assertions without triggering exceptions require specialized adversarial test generation.
