# INTELISE Component 4 — Phase 3C.2
## Large-Scale Defect Benchmark Construction, Oracle Validation and Dataset Freezing

### Document Information
- **Project**: INTELISE — Intelligent Agentic Testing & Explainable Feedback Loop Assistant
- **Component**: Component 4 (Testing, Defect Reasoning & Explainable Feedback)
- **Phase**: 3C.2 (Dataset Construction, Oracle Validation & Freezing)
- **Date**: October 20, 2026
- **Status**: DATASET_FROZEN / READY_FOR_PHASE3C3
- **Dataset Version**: `v3.2.0-phase3c2-large`
- **Location**: `component-4/benchmark/phase3c2/`

---

## 1. Dataset Design & Architecture

Phase 3C.2 constructs, validates, and seals a comprehensive, large-scale empirical evaluation dataset for Component 4. The dataset design directly addresses the empirical requirements of the research proposal:
1. **Scale**: Exactly 500 total scenarios comprising 400 distinct, independently validated seeded defects and 100 clean controls.
2. **Strict Sealing (Zero-Leakage Architecture)**:
   - `Phase3C2EvaluationInput`: Public evaluation representation containing only executable source code, authorized test code, and requirements. Strictly devoid of defect labels, CWE numbers, mutation operators, expected line numbers, and ground-truth answers.
   - `Phase3C2SealedGroundTruth`: Quarantined ground truth store containing physical defect locations, mutation lineage, expected versus observed behaviors, and oracle validation evidence. Joined only post-hoc for benchmark scoring.
3. **Partition Isolation**: Partitioned strictly at the **Source Project Family** level into Development (50%), Validation (20%), and Frozen Held-Out (30%) to eliminate near-duplicate and template leakage.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Phase 3C.2 Benchmark Architecture                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ 10 Independent Source Families ] ──────────► [ Independent Oracles ]    │
│   - FAM-01: Booking Workflows                    (AST Valid + Clean PASS    │
│   - FAM-02: Inventory Systems                     + Mutated FAIL)           │
│   - FAM-03: Payment Systems                              │                  │
│   - FAM-04: Authentication & RBAC                        ▼                  │
│   - FAM-05: Content Management                    [ 500 Scenarios ]         │
│   - FAM-06: API Gateway & Routing                400 Defects / 100 Controls │
│   - FAM-07: Metrics Reporting                            │                  │
│   - FAM-08: Job Scheduling                              ├──────────────────┐
│   - FAM-09: Data Pipelines                              ▼                  ▼
│   - FAM-10: Caching & KV Stores              [ Public Eval Input ]  [ Sealed GT ]
│                                              (No labels / clues)    (Answer Key)
│                                                         │                  │
│                                                         ▼                  ▼
│                                               Phase 3C.3 Evaluators    Scorer
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Actual Validated Defect Count

- **Target**: 400 distinct seeded code defects.
- **Actual Validated Count**: **400 distinct, independently validated seeded defects**.
- **Excluded / Discarded**:
  - Repeated executions: 0 counted.
  - Failed mutations / syntax errors: 0 counted.
  - Controls counted as defects: 0 counted.
  - Near-duplicate mutations across files: 0 counted (verified via `test_08_near_duplicate_detection`).
- **Defect ID Range**: `DEF-P3C2-001` through `DEF-P3C2-500` (assigned strictly to defective scenarios; clean controls possess `None`).

---

## 3. Actual Clean-Control Count

- **Target**: 100 clean controls.
- **Actual Validated Count**: **100 clean control scenarios**.
- **Representation**:
  - Clean controls represent verified, production-grade implementations spanning all 10 project families (exactly 10 clean controls per family).
  - Clean controls undergo the same oracle execution to guarantee zero false failures.
  - In `Phase3C2SealedGroundTruth`, clean controls have `defect_id = None`, `expected_cwe_id = None`, `expected_line_number = None`, `mutation_operator = None`, and `mutated_source == original_clean_source`.

---

## 4. Category Distribution

The 500 scenarios cover all 7 research defect categories plus clean controls:

| Category | Defect Count | Control Count | Total Scenarios | Share of Defects (%) | Share of Dataset (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Functional Bug** | 120 | 0 | 120 | 30.0% | 24.0% |
| **Security Vulnerability** | 60 | 0 | 60 | 15.0% | 12.0% |
| **Performance Bottleneck** | 50 | 0 | 50 | 12.5% | 10.0% |
| **Regression Defect** | 50 | 0 | 50 | 12.5% | 10.0% |
| **Integration Defect** | 50 | 0 | 50 | 12.5% | 10.0% |
| **Semantic Drift** | 40 | 0 | 40 | 10.0% | 8.0% |
| **Non-Convergent by Design** | 30 | 0 | 30 | 7.5% | 6.0% |
| **Clean Control** | 0 | 100 | 100 | N/A | 20.0% |
| **TOTAL** | **400** | **100** | **500** | **100.0%** | **100.0%** |

### Category Ground-Truth Details:
- **Security Vulnerabilities (60 scenarios)**: Span 6 major CWE classes:
  - CWE-89: SQL Injection (10 scenarios)
  - CWE-78: OS Command Injection (10 scenarios)
  - CWE-22: Path Traversal (10 scenarios)
  - CWE-79: Cross-Site Scripting / Unescaped Reflection (10 scenarios)
  - CWE-306: Missing Authentication (10 scenarios)
  - CWE-862: Missing Authorization / Broken Access Control (10 scenarios)
- **Semantic Drift (40 scenarios)**: Each scenario incorporates an explicit behavioral contract specification and verifiable drift evidence where the implementation quietly drops business requirements, alters rounding precision, or returns invalid status transitions.
- **Non-Convergent Defects (30 scenarios)**: Formally constructed with oscillating boundary operators, mutually exclusive constraints, or cyclic state transition tables where iterative repair loops cannot reach convergence without human intervention.

---

## 5. Difficulty Distribution

The dataset balances straightforward defects with complex, multi-line, state-dependent bugs:

| Difficulty Level | Defect Scenarios | Clean Controls | Total Scenarios | Percentage |
| :--- | :---: | :---: | :---: | :---: |
| **Easy** | 206 | 60 | 266 | 53.2% |
| **Medium** | 144 | 30 | 174 | 34.8% |
| **Hard** | 50 | 10 | 60 | 12.0% |
| **TOTAL** | **400** | **100** | **500** | **100.0%** |

- **Easy**: Localized boundary operator mutations, dropped prefixes, relational inequalities.
- **Medium**: Guard clause removals, unescaped string interpolations, missing normalization, quadratic search substitutions.
- **Hard**: Memoization removals leading to exponential recurrences, cyclic state machines, mutually exclusive contract specifications, subtle authentication bypasses.

---

## 6. Independent Source-Project Families

Ten distinct, independent source-project families were developed to prevent template homogeneity:

| Family ID | Domain Description | Total Scenarios | Defects | Controls | Partition |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **FAM-01-BOOKING** | Reservation, pricing, room inventory & booking workflows | 50 | 40 | 10 | Development |
| **FAM-02-INVENTORY** | Stock tracking, reorder thresholds, warehouse allocation | 50 | 40 | 10 | Development |
| **FAM-03-PAYMENT** | Card processing, fee calculations, reconciliation, ledger | 50 | 40 | 10 | Development |
| **FAM-04-AUTH** | JWT parsing, role-based access control, session expiry | 50 | 40 | 10 | Development |
| **FAM-05-CONTENT** | Article publishing, slugification, workflow approvals | 50 | 40 | 10 | Development |
| **FAM-06-API** | Gateway routing, rate limiting, header verification | 50 | 40 | 10 | Validation |
| **FAM-07-REPORT** | Analytics aggregation, CSV generation, metric trends | 50 | 40 | 10 | Validation |
| **FAM-08-SCHEDULE** | Cron parsing, recurrence scheduling, job queues | 50 | 40 | 10 | Frozen Held-Out |
| **FAM-09-PIPELINE** | ETL batch transformations, schema validation, ingestion | 50 | 40 | 10 | Frozen Held-Out |
| **FAM-10-CACHE** | Key-value store, LRU eviction, TTL invalidation | 50 | 40 | 10 | Frozen Held-Out |

---

## 7. Mutation Operators

Over 60 distinct mutation operators were applied across the 400 defective scenarios, avoiding reliance on single-pattern arithmetic swaps:
- **Relational & Arithmetic**: `RELATIONAL_OPERATOR_SUBSTITUTION`, `BOUNDARY_CONDITION_MUTATION`, `ARITHMETIC_OPERATOR_REPLACEMENT`, `OPERAND_ORDER_INVERSION`, `MIN_MAX_INVERSION`.
- **Security & Injection**: `SQL_STRING_INJECTION`, `SHELL_COMMAND_INTERPOLATION`, `UNSANITIZED_PATH_JOIN`, `MISSING_HTML_ESCAPING`, `AUTH_CHECK_REMOVAL`, `AUTHORIZATION_BYPASS`.
- **Performance & Algorithmic**: `REMOVAL_OF_MEMOIZATION`, `QUADRATIC_STRING_CONCATENATION`, `LINEAR_SEARCH_SUBSTITUTION`, `REDUNDANT_REGEX_COMPILATION`, `QUADRATIC_NESTED_FILTER`.
- **Regression & Defensive**: `GUARD_CLAUSE_REMOVAL`, `DROPPED_NEGATIVE_CHECK`, `DROPPED_CODE_PREFIX`, `REMOVAL_OF_SANITIZATION`, `NULL_POINTER_DEREFERENCE`.
- **Integration & Contracts**: `SCHEMA_KEY_MUTATION`, `RETURN_TYPE_ALTERATION`, `DROPPED_AUTH_HEADER`, `DATE_FORMAT_MISMATCH`, `CASING_MUTATION`.
- **Semantic Drift & Invariants**: `SPECIFICATION_ASSERTION_WEAKENING`, `CONTRACT_REQUIREMENT_DROPPED`, `INVARIANT_REMOVAL`, `ROUNDING_PRECISION_TRUNCATION`.
- **Non-Convergence**: `MUTUALLY_EXCLUSIVE_REQUIREMENTS`, `OSCILLATING_BOUNDARY_OPERATOR`, `CYCLIC_STATE_TRANSITION`.

---

## 8. Oracle Validation Methodology

Every scenario underwent automated dual-execution validation via `ScenarioOracleRunner`:
1. **Compilation Check**: `ast.parse()` verifies clean code, mutated code, and oracle code.
2. **Clean Baseline Execution**: The oracle is executed against the original clean implementation. The oracle must **PASS** cleanly without exceptions or assertion errors.
3. **Defective Execution**: The oracle is executed against the mutated implementation. For defective scenarios, the oracle must **FAIL** with an `AssertionError`, `ValueError`, `KeyError`, or expected regression exception. For clean controls, the oracle must **PASS**.
4. **Attributability**: The failure is verified to stem directly from the seeded mutation.
5. **Runtime Measurement**: Oracle execution wall-clock time is captured and recorded in `validation_evidence`.

---

## 9. Accepted and Rejected Mutations

- **Total Mutations Proposed**: 500
- **Initial Verification Failures / Bugs**: 3
  - Scenario `P3C2-019`: Substring check in AST matched parameter type hint — *corrected oracle assertion*.
  - Scenario `P3C2-027`: `int(" 08 ")` automatically stripped spaces in Python — *corrected to timestamp colon parsing regression*.
  - Scenario `P3C2-258`: Key expiration check allowed negative elapsed time — *added expired key assertion*.
  - Scenario `P3C2-269`: Substring match matched `in supported_headers_list` — *restricted oracle to require `set` and forbid loops*.
  - Scenario `P3C2-324`: Oracle caught `ZeroDivisionError` fallback — *restricted oracle to `ValueError`*.
- **Final Validation Pass Rate**: **500 / 500 (100.0%)**
- **Quarantined Scenarios**: 0

---

## 10. Partition Counts & Split Proportions

| Partition | Share (%) | Scenarios | Defects | Controls | Families Assigned |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Development (`dev`)** | 50.0% | 250 | 200 | 50 | `FAM-01`, `FAM-02`, `FAM-03`, `FAM-04`, `FAM-05` |
| **Validation (`val`)** | 20.0% | 100 | 80 | 20 | `FAM-06`, `FAM-07` |
| **Frozen Held-Out (`held_out`)** | 30.0% | 150 | 120 | 30 | `FAM-08`, `FAM-09`, `FAM-10` |
| **TOTAL** | **100.0%** | **500** | **400** | **100** | **10 Families** |

---

## 11. Anti-Leakage Audit

Strict automated leakage checks were implemented and verified in `test_phase3c2_dataset_integrity.py`:
- **Interface Segregation**: `Phase3C2EvaluationInput` contains zero ground-truth fields.
- **Content Inspection**: No scenario names, test codes, or module codes contain `CWE-`, `DEF-P3C2-`, `MUTATION_OPERATOR`, or answers.
- **Family Isolation**: 0% overlap between Dev, Val, and Held-out project families.
- **Frozen Status**: `held_out` is cryptographically sealed and untouched by any Component 4 detection code.

---

## 12. Dataset Checksums Manifest

Generated on: `2026-10-20T04:22:38.645362+00:00` (stored in `dataset_checksums.json`):

| File Name | Size (Bytes) | SHA-256 Digest |
| :--- | :---: | :--- |
| `evaluation_inputs.json` | 379,990 | `2902d09e0f3d62b81f0974a5aa3e500e742ade58acabba76f9b83bdc990cd1fb` |
| `sealed_ground_truth.json` | 753,293 | `535ea5a76e0d7959817e4f10c6dd14344df259ecf98b29cc4d3d8d8af9074ada` |
| `manifest.json` | 23,680 | `02edbcd1ca20226d0389c6d728ffc9dbf020da13429a4bd8776fb5425c604b4c` |
| `oracle_validation_report.json` | 338,472 | `8852a36aa631606c064fd83d20c6fe00d9841e8285ace6aa744dc7144262ff0c` |
| `partition_integrity_report.json` | 954 | `cc8c5c0440b39d891e1f489d9c129007d577add6197d0e50b163de7893a627b0` |
| `diversity_report.json` | 4,055 | `49aa203c9e6194f4b95a0fc001c7818e43b813784068a407e2ed71cf57632495` |

---

## 13. Reproducibility Instructions

The entire dataset can be regenerated or verified in a clean environment:
```powershell
# 1. Activate Python virtual environment
cd "D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4"
.\.venv\Scripts\Activate.ps1

# 2. Run dataset generator & oracle verification runner
python backend\scripts\generate_phase3c2_dataset.py

# 3. Execute automated dataset integrity and loader test suites
python -m pytest backend\tests\test_phase3c2_dataset_integrity.py backend\tests\test_phase3c2_dataset_loader.py -v
```

---

## 14. Storage & Execution Cost Estimates

| Evaluation Mode | Scenarios Evaluated | Estimated Per-Scenario Latency | Total Estimated Runtime | Compute Resources |
| :--- | :---: | :---: | :---: | :--- |
| **Deterministic C4** | 500 | ~150 ms | ~1.25 minutes | Local CPU (single core) |
| **LLM-Assisted C4** | 500 | ~9.5 s | ~75–85 minutes | Local Ollama (Qwen2.5-Coder 3B) |
| **Conventional CI Baseline** | 500 | ~120 ms | ~1.0 minute | In-process pytest runner |
| **Static Analysis Baseline** | 500 | ~50 ms | ~25 seconds | AST / Flake8 / Bandit parser |

Total benchmark storage footprint: **~1.5 MB** across all 7 artifact files.

---

## 15. Automated Test Results

- `test_phase3c2_dataset_integrity.py`: **17 / 17 passed**.
- `test_phase3c2_dataset_loader.py`: **5 / 5 passed**.
- Existing backend test suite: **338 / 338 passing preserved**.
- Total active test count: **360 passing tests**.

---

## 16. Known Limitations

1. **Synthetic Seeded Defects**: While spanning 10 realistic domain families and realistic architectural patterns, seeded defects remain synthetic mutations and cannot substitute for empirical studies on in-the-wild industrial codebases.
2. **In-Process Performance Measurement**: Micro-benchmarking execution timing can experience OS scheduling jitter; performance bottleneck oracles combine structural algorithmic checks with runtime bounds to maintain deterministic stability.
3. **Pending Live Component 3 Validation**: As dictated by Phase 3C boundaries, Component 3 interactions remain simulated against the approved API contract (`COMPONENT_3_ENABLED=false`).

---

## 17. Readiness for Phase 3C.3

- [x] 400 distinct, independently validated defects constructed.
- [x] 100 clean control scenarios constructed and verified.
- [x] All 500 scenarios validated by independent executable oracles (0 quarantined).
- [x] 10 independent project families implemented.
- [x] 7 defect categories + clean controls represented.
- [x] Evaluation inputs strictly segregated from sealed ground truth.
- [x] Partitions isolated at family level (Dev 50%, Val 20%, Held-out 30%).
- [x] Held-out partition frozen with SHA-256 digests.
- [x] Zero detector tuning against held-out partition conducted.
- [x] Repair evaluation protocol fully documented.
- [x] Automated integrity test suite passes with 100% success.

**FINAL VERDICT: READY_FOR_PHASE3C3**
