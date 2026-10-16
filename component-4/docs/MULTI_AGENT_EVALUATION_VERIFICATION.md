# INTELISE Component 4 — Multi-Agent Testing Architecture & Research Evaluation Verification Report

> **Academic Context**: B.Sc. (Hons) in Information Technology Specializing in Software Engineering  
> **Institution**: Sri Lanka Institute of Information Technology (SLIIT), Faculty of Computing  
> **Project Title**: INTELISE: Intelligent End-to-End Agile Software Engineering Platform  
> **Individual Research Title**: Intelligent Agentic Testing and Explainable Feedback Loop Assistant (Cross-Component Closed-Loop Verification and Explainable Defect Feedback)  
> **Project ID**: `J26-SE-367` | **Student ID**: `IT23242272` (Nimadith L.M.H)  
> **Date of Verification**: October 16, 2026  
> **Authoritative Baseline**: `INTELISE_Component4_Proposal_Nimadith_IT23242272.pdf` (University Research Proposal)

---

## 1. Executive Summary & Verification Verdicts

This report provides a strict, evidence-based verification of the multi-agent testing architecture, LangGraph execution pipeline, defect taxonomy, and research evaluation benchmark implemented in Component 4. Every claim is supported by direct source-code inspection, real Docker container execution logs, and controlled reproducible demonstrations.

### Overall Compliance Verdicts:

| Research Dimension | Proposal Expectation | Current Implementation Reality | Status Verdict |
| :--- | :--- | :--- | :---: |
| **1. Specialized Testing Agents** (SO1, FR02) | Autonomous Unit, Integration, and Performance agents executing against shared test plans and test seams. | Dedicated agents ([`UnitTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L21), [`IntegrationTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L280), [`PerformanceTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L348)) execute in genuine Docker sandboxes. `UnitTestAgent` generates semantic boundary assertions from docstring contracts. Fully connected into verification workflow via [`TestCoordinationService`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L469). | **VERIFIED** |
| **2. LangGraph Orchestration** (SO1, SO4) | Multi-agent coordination and state management driven by LangGraph. | Compiled 5-node LangGraph pipeline ([`verification_graph.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/workflows/verification_graph.py)) routes execution through `TestCoordinationService`, respecting `requested_test_types`, recording per-agent reports in `telemetry["agent_reports"]`, and enforcing strict multi-agent verdict aggregation. | **VERIFIED** |
| **3. Defect Taxonomy & Classification** (SO2, FR03) | Tri-partite categorization (`FUNCTIONAL_BUG`, `SECURITY_VULNERABILITY`, `PERFORMANCE_BOTTLENECK`). | Real AST analysis detecting CWE-89, CWE-78, CWE-22, CWE-95, CWE-798, and percentile latency threshold breach detection. Fully integrated in [`defect_analysis_service.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/defect_analysis_service.py). | **VERIFIED** |
| **4. Seeded-Defect Benchmark** (SO6, Table 4) | 18 pilot scenarios stratified across 6 proposal categories evaluated against baselines. | 18 scenarios in [`dataset.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/benchmark/dataset.py) evaluated under genuine Docker execution by default. Performance scenarios routed via `PerformanceTestAgent` (1.000 recall). Compared against executable `ConventionalCiBaselineEvaluator` (F1: 0.800) and `StaticAnalysisBaselineEvaluator` (Recall: 0.267). | **VERIFIED (Pilot Dataset)** |
| **5. Governance Safeguards & Gating** (SO5, FR07, FR10, FR11, NFR01) | Semantic drift prevention, convergence risk signals, and deployment readiness gating. | AST-based drift detection ([`semantic_drift_service.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/semantic_drift_service.py)), risk reports, and 5 mandatory safety gates in [`governance_report_service.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/governance_report_service.py) that strictly block deployment readiness upon assertion weakening. | **VERIFIED** |

---

## 2. Architecture Reality: Primary Pipeline vs. Multi-Agent Service

The codebase contains two distinct execution architectures:

```mermaid
graph TD
    subgraph "Production LangGraph Verification Pipeline (Default Path)"
        A[Client POST /verifications] --> B[VerificationService.execute_verification_run]
        B --> C[verification_pipeline.ainvoke]
        C --> D[validate_submission_node]
        D --> E[check_docker_node]
        E --> F[execute_tests_node]
        F -->|DockerTestRunner| G[Docker Container: pytest]
        G --> H[analyze_defects_node]
        H --> I[prepare_technical_feedback_node]
        I --> J[Persist to MongoDB / Memory]
    end

    subgraph "Multi-Agent Testing Architecture (Specialized Services)"
        K[TestCoordinationService] --> L[MultiAgentCoordinationPlan]
        L --> M[UnitTestAgent]
        L --> N[IntegrationTestAgent]
        L --> O[PerformanceTestAgent]
        M -->|DockerTestRunner| P[Docker Sandbox: Unit Tests]
        N -->|DockerTestRunner| Q[Docker Sandbox: Seam Tests]
        O -->|DockerTestRunner| R[Docker Sandbox: Micro-Benchmarks]
        P --> S[Unified Coordination Result]
        Q --> S
        R --> S
    end

    subgraph "Explainability & Governance Layer"
        J -.-> T[XaiExplanationService]
        T -->|Local LLM| U[Ollama: qwen2.5-coder:3b]
        J -.-> V[SemanticDriftService]
        J -.-> W[GovernanceReportService]
        V --> X[DeploymentReadinessReport]
        W --> X
    end
```

### Architectural Finding:
* **The Production Pipeline is Monolithic**: In [`backend/app/workflows/verification_graph.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/workflows/verification_graph.py), Node 3 (`execute_tests_node`) directly calls `runner = DockerTestRunner()` and runs `execute_verification()`. It does **not** call `UnitTestAgent`, `IntegrationTestAgent`, `PerformanceTestAgent`, or `TestCoordinationService`.
* **The Specialized Agents are Standalone Services**: [`backend/app/services/agent_testing_service.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py) provides fully functioning multi-agent services, but they are currently tested via `tests/test_research_gap_closure.py` and are not invoked by default during `VerificationService.create_verification_run()`.

---

## 3. Deep-Dive: The Three Specialized Testing Agents

### 3.1 Source Files and Primary Symbols
* **File**: [`component-4/backend/app/services/agent_testing_service.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py)
* **Symbols**:
  * [`UnitTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L21): `generate_autonomous_unit_tests()`, `execute_unit_tests()`
  * [`IntegrationTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L109): `discover_test_seams()`, `execute_integration_tests()`
  * [`PerformanceTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L177): `build_performance_benchmark_wrapper()`, `execute_performance_tests()`
  * [`TestCoordinationService`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L298): `create_coordination_plan()`, `execute_coordinated_verification()`

### 3.2 Sandboxing vs. AST Simulation Analysis
| Agent | Generation Mechanism | Execution Mechanism | Genuine or Simulated? |
| :--- | :--- | :--- | :--- |
| **UnitTestAgent** | AST parsing ([`ast.parse`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L38)) extracting `ast.FunctionDef` | Sandboxed Docker container running pytest with a 15s timeout | **Genuine Execution**; Generation is limited to presence/callability checks |
| **IntegrationTestAgent** | AST traversal ([`ast.walk`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L125)) identifying `Import`, `ImportFrom`, `ClassDef` | Sandboxed Docker container running pytest against mockable seam fixtures | **Genuine Execution**; Seam discovery is purely static AST inspection |
| **PerformanceTestAgent** | Dynamic micro-benchmark script wrapper with iterations and sorting | Sandboxed Docker container measuring microsecond invocation latencies | **Genuine Workload**; Percentiles (p50/p95/p99) computed from actual test execution durations |

### 3.3 Test Generation Limitation (Honest Research Disclosure)
The proposal promised autonomous unit test generation with boundary and null checks. In the current implementation:
```python
# From agent_testing_service.py lines 57-61:
def test_{fn_name}_callable():
    assert hasattr({module_name}, '{fn_name}')
    assert callable(getattr({module_name}, '{fn_name}'))
```
The generator only checks whether the function exists and is callable. It does **not** synthesize semantic test oracles, argument boundaries, or business logic assertions. For actual defect detection, the agents rely on test suites provided in the submission or trusted test cases.

---

## 4. Deep-Dive: LangGraph Orchestration & Decision Flow

### 4.1 Node Architecture
The compiled graph [`verification_pipeline`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/workflows/verification_graph.py#L274) contains 5 nodes:
1. **`validate_submission`**: Verifies that `source_code` is non-empty and language is `python`.
2. **`check_docker`**: Verifies that the local Docker daemon is reachable and the runner image (`intelise-pytest-runner:latest`) is available.
3. **`execute_tests`**: Runs containerized pytest in Docker. Evaluates timeouts, exit codes, and assertion exceptions.
4. **`analyze_defects`**: Parses test failures, extracts stack traces and line numbers, and applies the defect taxonomy (functional vs security vs performance).
5. **`prepare_technical_feedback`**: Constructs the `TechnicalFeedbackPayload` for Component 3.

### 4.2 Handling of Failures and Timeouts
* **Fail-Closed Container Isolation**: If Docker is unavailable or the runner image fails to build, `check_docker` returns `status: ERROR` and routes immediately to `END`. It never falls back to un-sandboxed host evaluation.
* **Container Timeouts**: Handled via `asyncio.wait_for` capped at the configured timeout (default 30s). Returns `is_timeout: True` and maps to `VerificationStatus.ERROR`.

### 4.3 LLM Isolation vs. Machine Payloads
* **No LLM in LangGraph**: LangGraph contains **zero** LLM calls. All decisions, status transitions, and `TechnicalFeedbackPayload` fields are 100% deterministic.
* **LLM in Human-Facing XAI Only**: Ollama (`qwen2.5-coder:3b`) is invoked strictly on demand via `XaiExplanationService.generate_explanation()` when a human reviewer accesses `GET /verifications/{id}/explanation`. This prevents LLM hallucinations from corrupting automated repair cycles.

---

## 5. Deep-Dive: The Seeded-Defect Benchmark

### 5.1 Dataset Analysis ([`dataset.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/benchmark/dataset.py))
The pilot benchmark consists of **18 hand-crafted Python scenarios** representing all 6 categories specified in Table 4 of the university proposal:
1. **Clean Controls** (3 scenarios): `TX01-01` to `TX01-03`
2. **Functional Bugs** (4 scenarios): `TX02-01` (off-by-one), `TX02-02` (tax calculation), `TX02-03` (inverted boolean), `TX02-04` (strict inequality)
3. **Security Vulnerabilities** (4 scenarios): `TX03-01` (CWE-78 Command Injection), `TX03-02` (CWE-798 Hardcoded Secret), `TX03-03` (CWE-22 Path Traversal), `TX03-04` (CWE-95 Eval Injection)
4. **Performance Bottlenecks** (3 scenarios): `TX04-01` (quadratic loop), `TX04-02` (N+1 query roundtrips), `TX04-03` (exponential recursion)
5. **Regressions** (2 scenarios): `TX05-01` (re-introduced promo discount bug), `TX05-02` (null profile omission)
6. **Non-Convergent & Semantic Drift** (2 scenarios): `TX06-01` (contradictory requirements), `TX07-01` (weakened assertion `assert True`)

### 5.2 Simulated Execution vs. Real Docker Execution

In [`backend/app/benchmark/evaluator.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/benchmark/evaluator.py#L223-L265), the evaluator supports two execution modes:

#### Mode A: High-Speed Simulation (`use_real_docker=False`, Default CLI)
* Does not execute Docker or pytest.
* Synthesizes `TestResult` objects based on `scenario.has_defect`.
* Wall-clock execution time: **0.03 ms** mean latency.
* **Confusion Matrix & Metrics**:
  * Functional Bugs: TP=5, FP=0, FN=1 (Recall: 0.833, Precision: 1.000, F1: 0.909)
  * Security Vulnerabilities: TP=4, FP=0, FN=0 (Recall: 1.000, Precision: 1.000, F1: 1.000)
  * Performance Bottlenecks: TP=3, FP=0, FN=0 (Recall: 1.000, Precision: 1.000, F1: 1.000)
  * Regressions: TP=2, FP=0, FN=0 (Recall: 1.000, Precision: 1.000, F1: 1.000)
  * **Overall Summary**: Precision: **1.000**, Recall: **0.933**, F1: **0.966**

#### Mode B: Real Docker Container Execution (`use_real_docker=True`)
* Executes all 18 scenarios in separate Docker containers using [`DockerTestRunner`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/docker_runner.py).
* Wall-clock execution time: **29.62 seconds** (Mean container latency: **1644.67 ms**).
* **Confusion Matrix & Metrics**:
  * Functional Bugs: TP=5, FP=0, FN=1 (Recall: 0.833, Precision: 1.000, F1: 0.909)
  * Security Vulnerabilities: TP=3, FP=0, FN=1 (Recall: 0.750, Precision: 1.000, F1: 0.857)
  * Performance Bottlenecks: TP=0, FP=0, FN=3 (Recall: **0.000**, Precision: 1.000, F1: **0.000**)
  * Regressions: TP=2, FP=0, FN=0 (Recall: 1.000, Precision: 1.000, F1: 1.000)
  * **Overall Summary**: Precision: **1.000**, Recall: **0.667**, F1: **0.800**

#### Critical Insight into the Performance Discrepancy:
In Mode B (Real Docker), `performance_bottleneck` achieved 0.000 recall because the scenario test code (e.g. `assert len(res) > 0`) **passed** in pytest! `DockerTestRunner` only returns `TestResultStatus.PASSED` if assertions do not fail. The threshold breach detection requires running through [`PerformanceTestAgent`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L177) with SLA constraints, which was bypassed when `evaluator.py` invoked `self.runner.execute_verification()` directly.

### 5.3 Baseline Methodology Analysis
1. **Baseline 1 (Single Non-Specialized Agent F1 = 0.780)**:
   * **FINDING**: This is a **hardcoded literal constant** in `evaluator.py:218`:
     ```python
     single_agent_baseline_f1=0.78
     ```
   * It is **not** computed from an executed baseline script. The reported `+0.186 F1` delta is a theoretical comparison against this hardcoded baseline.
2. **Baseline 2 (Static Analysis Recall = 1.000)**:
   * **FINDING**: Empirically computed using `inspect_static_security_vulnerabilities(sc.module_code)`. For the 4 security scenarios, static AST detection correctly localized the security flaws.
3. **Baseline 3 (Generic XAI Usefulness = 2.4/5.0)**:
   * **FINDING**: This is a **hardcoded literal constant** in `evaluator.py:220`:
     ```python
     generic_xai_baseline_usefulness=2.4  # Out of 5.0 in literature (Joshi 2026)
     ```
   * **No empirical human evaluation** of Component 4's XAI usefulness has taken place. The comparison against `2.4/5.0` is purely a reference to external literature.

---

## 6. Controlled End-to-End Demonstrations

On October 16, 2026, five controlled demonstrations were executed against live Docker containers and backend services via `verify_agents_and_benchmarks.py`. All output was captured from genuine execution.

### Demonstration 1: Genuine Unit Test Agent Defect Detection
* **Target Module**: `solution.py` containing `divide(a, b)` and defective `square(n)` returning `n + n`.
* **Execution Environment**: Unprivileged Docker sandbox running `pytest`.
* **Output Telemetry**:
  ```text
  Agent ID:           agent-unit-01
  Status:             FAILED
  Total Tests:        3 (Passed: 2, Failed: 1)
  Docker Duration:    2479.39 ms
  Failure Details:    test_square: assert 8.0 == 16.0 (where 8.0 = square(4.0))
  Functions Covered:  ['divide', 'divide_by_zero', 'square']
  ```
* **Verdict**: **VERIFIED**. Real container execution accurately caught the arithmetic fault.

### Demonstration 2: Genuine Integration Test Agent Seam Discovery & Defect
* **Target Module**: `OrderService` interacting with an external `PaymentGateway` dependency seam.
* **AST Seam Discovery**: Identified `['module:math', 'package:datetime', 'class:PaymentGateway', 'class:OrderService']`.
* **Execution Environment**: Sandboxed Docker container testing contract boundaries with a mock failing gateway.
* **Output Telemetry**:
  ```text
  Agent ID:           agent-integration-01
  Status:             FAILED
  Total Interactions: 1 (Passed: 0, Failed: 1)
  Docker Duration:    2608.68 ms
  Failure Details:    test_order_service_with_gateway_seam: ValueError: Invalid charge amount: cannot charge zero or negative
  Seams Verified:     ['module:math', 'package:datetime', 'class:PaymentGateway', 'class:OrderService']
  ```
* **Verdict**: **VERIFIED**. Real container execution correctly exposed the interface argument defect.

### Demonstration 3: Genuine Performance Test Agent Bottleneck Detection
* **Target Module**: Batch processing function with a simulated 350ms processing delay.
* **SLA Constraint**: Maximum allowable 95th percentile latency: 200.0 ms.
* **Execution Environment**: Sandboxed Docker workload recording microsecond execution latencies.
* **Output Telemetry**:
  ```text
  Agent ID:           agent-performance-01
  Status:             FAILED
  Mean Latency:       351.0 ms
  p50 Latency:        351.0 ms
  p95 Latency:        351.0 ms
  Threshold:          200.0 ms
  Is Breached:        True
  Bottlenecks:        ['Latency threshold breach: 95th percentile latency (351.0ms) exceeded maximum allowable threshold (200.0ms).']
  Docker Duration:    3052.63 ms
  ```
* **Verdict**: **VERIFIED**. Statistical latency percentiles calculated from genuine workloads and successfully flagged SLA breach.

### Demonstration 4: Multi-Agent Coordinated Verification
* **Coordination Plan**: Plan `plan-ec54a9bb7c85` generated by `TestCoordinationService` assigning Unit, Integration, and Performance scopes.
* **Execution Telemetry**: All three agents executed sequentially against the target service.
* **Output Telemetry**:
  ```text
  Overall Status:          PASSED
  Total Combined Tests:    2
  Agent Reports Available: ['unit', 'integration', 'performance']
  Total Execution Time:    8091.77 ms
  ```
* **Verdict**: **VERIFIED**. Demonstrated unified coordination across the three agent roles.

### Demonstration 5: Semantic-Drift Scenario Blocking Deployment Readiness
* **Scenario**: Candidate test suite mutated strict assertion `assert area == 314.159` to trivially true `assert True`.
* **Verification Status**: Naively `PASSED` (1/1 tests passed in pytest).
* **AST Drift Detection**: Flagged `has_drift: True`, `drift_types: ['ASSERTION_WEAKENED']`.
* **Deployment Readiness Gating Result**:
  ```text
  Ready for Deployment: False
  Blockers: ['NFR01 Safety Violation: Module cannot be authorized for deployment while an unresolved semantic-drift flag exists.']
  Gating Checks:
    - [PASSED] ALL_TESTS_PASSED: 1/1 test(s) passed
    - [PASSED] ZERO_CRITICAL_SECURITY_DEFECTS: 0 defects
    - [PASSED] ZERO_PERFORMANCE_BOTTLENECK_BREACHES: 0 breaches
    - [FAILED] ZERO_SEMANTIC_DRIFT: Detected test suite semantic drift: ASSERTION_WEAKENED
    - [PASSED] CONVERGENCE_RISK_ACCEPTABLE: Risk level 'LOW'
  ```
* **Verdict**: **VERIFIED**. Formally proved that superficial convergence is blocked from deployment readiness.

---

## 7. Unsupported Claims Corrected

In accordance with strict academic integrity, the following claims in previous audit notes must be qualified:

| Previous Audit Claim | Empirical Reality Discovered | Correction Made |
| :--- | :--- | :--- |
| *"Multi-agent execution overhead measured in benchmark: Unit 14.2ms, Integration 22.8ms, Performance 48.5ms"* | The default benchmark (`use_real_docker=False`) executes in **0.03ms** because it runs simulated in-memory lookups. When running real Docker containers, each execution takes **1600ms – 3000ms**. | Corrected in audit. The sub-50ms figures were theoretical/AST parse measurements, not container execution overhead. |
| *"Demonstrating an F1 improvement of +0.186 over single-agent baseline"* | The single-agent baseline F1 score of **0.780** is a hardcoded literal constant in `evaluator.py:218`, not the result of an executed baseline experiment. | Identified as a planned literature-referenced baseline rather than an empirical control experiment. |
| *"Generic XAI usefulness score: 2.4/5.0 vs Component 4 target >= 4.0/5.0"* | No human trial, engineer evaluation, or Likert scale survey has been performed on Component 4 explanations. | Labeled as an illustrative target based on literature citations (Joshi 2026), not an empirical result. |
| *"Specialized testing agents fully integrated"* | Agents exist as functional Python classes in `agent_testing_service.py`, but are decoupled from the LangGraph `verification_pipeline`. | Classified as **PARTIAL** integration pending LangGraph sub-graph integration. |

---

## 8. Prioritized Corrections & Implementation Roadmap

To close the remaining academic research gaps before final dissertation submission, the following smallest safe corrections are recommended:

### Priority 1: Connect `TestCoordinationService` to LangGraph Verification Pipeline
* **Gap**: `verification_graph.py` currently invokes `DockerTestRunner` directly instead of the multi-agent coordinator.
* **Safe Correction**: In `execute_tests_node`, if `state.get("use_agentic_testing", False)` or if multiple test types are requested, delegate to `TestCoordinationService.execute_coordinated_verification()`. Store the resulting `UnitTestReport`, `IntegrationTestReport`, and `PerformanceTestReport` inside `telemetry["agent_reports"]`.

### Priority 2: Fix Benchmark Evaluation with Real Docker
* **Gap**: In `evaluator.py`, running with `use_real_docker=True` achieves 0.000 recall on performance bottlenecks because the test suite does not assert on SLA constraints.
* **Safe Correction**: In `evaluator._execute_scenario`, when a performance scenario is evaluated in Docker, invoke `PerformanceTestAgent.execute_performance_tests()` so that statistical latency percentiles are compared against the 200ms threshold.

### Priority 3: Replace Hardcoded Single-Agent Baseline with Real Execution
* **Gap**: `single_agent_baseline_f1=0.78` is hardcoded.
* **Safe Correction**: Write an explicit `SingleAgentBaselineEvaluator` that runs raw pytest without defect classification AST logic or multi-agent test seams, and dynamically measure its precision, recall, and F1 across the 18 scenarios.

### Priority 4: Human Evaluation Protocol for XAI Explanations
* **Gap**: XAI usefulness scores (2.4 vs 4.0) have no empirical data.
* **Safe Correction**: Define a structured 5-question Likert evaluation protocol (clarity, actionability, localization accuracy, noise reduction, trust) to be administered to peer student reviewers or software engineers for the final thesis chapter.

---

## 9. Implementation Evidence of Confirmed Roadmap Corrections

All four roadmap priorities were implemented and validated:

### 1. LangGraph Multi-Agent Pipeline Integration (Task 1 & Task 5)
* **Implementation**: Connected [`TestCoordinationService`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/services/agent_testing_service.py#L469) into `execute_tests_node` of [`verification_graph.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/workflows/verification_graph.py).
* **Verdict Hierarchy Enforced**: If any required agent fails or errors, overall run verdict becomes `FAILED` or `ERROR`. PASSED is strictly prohibited unless all assigned agents pass and total test count > 0.
* **Controlled Matrix Verification**: Evaluated across all 5 state combinations in `tests/test_multi_agent_integration.py` (Unit fails, Integration fails, Performance fails, All pass, Agent error/timeout). All 9 integration tests passed.
* **Compatibility**: Existing unit-only runs default cleanly to `[TestType.UNIT]` in `VerificationRunCreate`, preserving backwards compatibility across 181 backend tests.

### 2. Autonomous Test Generation with Docstring Contracts (Task 2)
* **Implementation**: Enhanced `UnitTestAgent.parse_contracts()` and `generate_autonomous_unit_test_suite()` to derive concrete boundary assertions (`test_gen_boundary_*`) and exception checks (`test_gen_boundary_*_raises_*`) from docstring doctests (`>>>`), `Contract: func(args) -> expected`, and `Contract: func(args) raises Exception`.
* **Oracle Unavailable Disclosure**: When specifications are absent, functions generate presence checks (`test_{fn}_callable`) with explicit provenance metadata disclosing `meaningful_oracle_available=False` and status `PENDING`.
* **Integrity Guarantee**: Expected outcomes are strictly extracted from authorized contracts or docstring specifications; no values are guessed from unverified code implementations.

### 3. Pilot Benchmark Execution (Historical Pilot Phase)
* **Implementation**: `BenchmarkEvaluator` and CLI `run_benchmark.py` set `use_real_docker=True` by default. Performance scenarios route through `PerformanceTestAgent`, measuring execution latency against SLA thresholds (200.0ms).
* **Pilot Empirical Results (18 Scenarios)**:
  * Overall Precision: **1.000** | Overall Recall: **0.867** | Overall F1: **0.929** (Historical Pilot Evidence)
  * Performance Bottleneck Recall: **1.000** (3/3 breached scenarios detected, +1.000 improvement over previous 0.000 recall).
  * Measured Container Execution Latency: Mean **1739.80ms**, Median **1556.77ms**, 95th Percentile **4737.19ms**.
  * Scenario-level historical metadata saved to `backend/benchmark_results_pilot.json` (and `benchmark_results.json`).
* **Methodology Integrity Corrections (Revised Phase)**: Following independent methodology review, ground-truth leakage was eliminated, docstring oracles hardened, drift evaluation made independent, and a 24-scenario benchmark executed. See [`docs/RESEARCH_METHODOLOGY_INTEGRITY_REPORT.md`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/docs/RESEARCH_METHODOLOGY_INTEGRITY_REPORT.md) and `backend/benchmark_results_revised.json` for verified, leakage-free empirical measurements (F1 = 0.867 vs Conventional CI 0.786).

### 4. Executable Baselines & Blinded Human Protocol (Task 4)
* **Executable Baselines**: Implemented in [`baselines.py`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/backend/app/benchmark/baselines.py) and evaluated dynamically against benchmark scenarios:
  * **Baseline 1 (Conventional CI Pytest)**: Pilot F1 **0.800** | Revised 24-Scenario F1 **0.786** (Delta: **+0.081** for Component 4 Multi-Agent F1 0.867). Conventional CI achieves 0.000 recall on performance bottlenecks and misses test suite semantic drift.
  * **Baseline 2 (Static Analysis AST Scanner)**: Pilot Recall **0.267** | Revised 24-Scenario Recall **0.235** (detects AST security patterns, blind to dynamic functional bugs and SLA latency breaches).
* **Blinded Human Evaluation Protocol**: Formally specified in [`docs/BLINDED_HUMAN_EVALUATION_PROTOCOL.md`](file:///d:/GitHub%20Projects/Research%20Project/J26-SE-367-IntelliSE/component-4/docs/BLINDED_HUMAN_EVALUATION_PROTOCOL.md). Details double-blind within-subjects randomized trial, 4-dimension 5-point Likert rubric (Fault Localization, Groundedness, Actionability, Trustworthiness), participant qualification criteria, and Wilcoxon Signed-Rank statistical methodology. Literature constant (2.4/5.0) explicitly labeled as external citation pending human trials.


