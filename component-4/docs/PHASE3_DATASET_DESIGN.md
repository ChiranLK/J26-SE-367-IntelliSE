# INTELISE Component 4 — Phase 3A: 100-Scenario Research Benchmark Dataset Design

**Document ID:** INTELISE-C4-PHASE3-DATASET-01  
**Project:** INTELISE (Intelligent End-to-End Agile Software Engineering Platform)  
**Component:** Component 4 (Autonomous Multi-Agent Dynamic Testing & Evidence-Grounded Verification)  
**Author / Student:** Nimadith L.M.H (Student ID: `IT23242272`)  
**Supervisors:** Ms. Suriyaa Kumari (Academic Supervisor), Mr. Eishan Weerasinghe (Co-Supervisor)  
**Date:** October 19, 2026  
**Dataset Version:** `v3.0.0-heldout`  
**Dataset Architecture:** 40 Development Scenarios (`PH3-DEV-001` .. `PH3-DEV-040`) + 60 Frozen Held-Out Scenarios (`PH3-HELD-001` .. `PH3-HELD-060`)  
**Overall Manifest SHA-256 Digest:** `8cc6d38221d62faea0aebb084d80967ed769e1e7382609b52e8679b0cb85109f`  
**Dev Partition SHA-256 Digest:** `56638e4172a8f074f51eceb1db44a4a0e96654d9428a2a89b9930ee95a5c082e`  
**Held-Out Partition SHA-256 Digest:** `e766bd3ab03bd9a5721fec86f2a2b97ab12702508afad0d8a95549a0027b7465`  
**Operational Gating:** `COMPONENT_3_ENABLED=false`, Docker Sandbox Isolation (`python:3.12-slim`), Ephemeral In-Memory Fallback.

---

## 1. Executive Summary & Proposal Alignment

Following the approved university research proposal (Section 3.8, SO6, Table 4, Table 15), this document defines the first independently evaluable 100-scenario research benchmark for INTELISE Component 4.

The primary objective of this Phase 3A expansion is to rigorously evaluate **generalization, reproducibility, and real comparative detection efficacy**, rather than optimizing an artificially elevated F1 score on a small development set.

### 1.1 Progression from Historical Baselines
- **Historical Milestone (Pilot):** 18 pilot scenarios (`TX01-01` to `TX07-01`) provided initial feasibility proof.
- **Phase 2 Validation:** 24 revised scenarios (`REV-CLEAN-01` to `REV-FUNC-05`) established zero-ground-truth leakage, isolated semantic drift discrimination, and identified coordinate conventions. These 24 scenarios remain permanently frozen and untouched as historical development evidence.
- **Phase 3A Expansion:** 100 newly authored, substantive, fully executable benchmark fixtures spanning all 8 proposal-mandated defect and control categories.

### 1.2 Core Methodological Safeguards
1. **Physical Partition Separation:** Scenarios are separated into 40 Development fixtures (`phase3_dev.py`) and 60 Held-Out fixtures (`phase3_heldout.py`).
2. **Cryptographic Freeze:** Both subsets and the unified dataset are immutably bound to SHA-256 checksums recorded in `phase3_manifest.json`.
3. **Zero Ground-Truth Leakage:** Ground-truth labels (`has_defect`, `expected_defect_category`, `expected_cwe_id`, `has_semantic_drift`) are NEVER accessed by detectors, agents, or test runners during execution. Scoring occurs exclusively *after* all empirical predictions are finalized.
4. **Physical Line Number Attribution:** Every defective scenario documents the exact physical line number in the source file, accounting for Python AST and container runtime line indexing conventions.
5. **Executable Comparative Baselines:** Component 4 is directly benchmarked against Conventional CI (raw pytest in Docker) and Static AST Analysis on identical inputs under real execution.

---

## 2. Dataset Architecture & Split Strategy

The 100 scenarios are divided into two distinct partitions following empirical machine learning and software engineering research protocols:

```
+-----------------------------------------------------------------------------------------+
|                                100-SCENARIO BENCHMARK                                  |
|                                (v3.0.0-heldout)                                         |
+--------------------------------------------+--------------------------------------------+
|        40 Development Scenarios            |          60 Held-Out Scenarios             |
|        (PH3-DEV-001 - PH3-DEV-040)         |        (PH3-HELD-001 - PH3-HELD-060)       |
+--------------------------------------------+--------------------------------------------+
| Purpose:                                   | Purpose:                                   |
| - Rule calibration & diagnostic validation | - Unbiased final generalization evaluation |
| - Defect taxonomy boundary checks          | - Comparative baseline performance proof   |
| - Repair harness workflow verification     | - Zero threshold or heuristic tuning       |
|                                            |                                            |
| Share: 40%                                 | Share: 60%                                 |
| Manifest Hash: 56638e4172a8...             | Manifest Hash: e766bd3ab03b...             |
+--------------------------------------------+--------------------------------------------+
```

### 2.1 The Development Partition (40 Scenarios)
The development set was used exclusively for diagnostic identification, syntax verification, and baseline infrastructure testing. For instance, execution on the dev set surfaced:
- A dictionary key discrepancy in baseline breakdown reporting (`KeyError: 'correct'`), which was corrected prior to held-out evaluation.
- The behavior of AST assertion counting when assertions are encapsulated in helper functions outside `test_` functions.

### 2.2 The Held-Out Evaluation Partition (60 Scenarios)
The held-out set was frozen *before* final evaluation. No detector heuristics, regex patterns, AST rules, or latency thresholds were altered based on held-out results. The held-out set provides an authentic, unbiased empirical measure of how Component 4 performs on unseen software constructs.

---

## 3. Proposal-Aligned Defect Categories & Proportions

The dataset distribution directly reflects Proposal Table 4 ("Seeded-Defect Benchmark Scenario Groups"):

| Category | Proposal Target Share | Dev Set (40) | Held-Out Set (60) | Total Count (100) | Actual Benchmark Share |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Clean Controls & Safe Negative Controls** | ~20% | 8 | 18 | 26 | 26.0% |
| **Functional Defects & Boundary Cases** | 25–30% | 10 | 15 | 25 | 25.0% |
| **Security Vulnerabilities** | 15–20% | 6 | 5 | 11 | 11.0% |
| **Performance Bottlenecks** | 10–15% | 4 | 3 | 7 | 7.0% |
| **Integration & API Compatibility Defects** | ~10% | 4 | 6 | 10 | 10.0% |
| **Regression Defects** | ~10% | 4 | 6 | 10 | 10.0% |
| **Semantic Drift Cases (Positive & Negative)** | 5–10% | 2 | 5 | 7 | 7.0% |
| **Non-Convergent Repair Loops** | ~5% | 2 | 2 | 4 | 4.0% |
| **Total** | **100%** | **40** | **60** | **100** | **100.0%** |

*Note: In the classification taxonomy, negative security controls and normal performance controls are evaluated under `CLEAN_CONTROL` (ground truth `has_defect=False`), establishing rigorous negative control baselines that prove detectors do not fire false alarms on safe patterns.*

---

## 4. Detailed Category Definitions & Ground Truth Methodology

### 4.1 Functional Defects & Boundary Cases
- **Definition:** Deterministic runtime logic errors, off-by-one boundary conditions, numerical precision truncations, inverted conditional branches, or unhandled exceptions under edge-case inputs.
- **Seeding Method:** Derived from common real-world algorithmic defects (e.g. pagination boundary slice, century leap year calculation, median integer division truncation, binary search upper bound indexing, date interval inclusion).
- **Ground Truth Grounding:** Independently specified functional contracts; trusted test suites containing boundary assertions that fail with explicit `AssertionError` or runtime exceptions.

### 4.2 Security Vulnerabilities & Safe Negative Controls
- **Definition:** Code patterns exhibiting high-severity security vulnerabilities from the OWASP Top 10 / MITRE CWE taxonomy:
  - **CWE-78:** OS Command Injection (via `os.system`, `os.popen`, or `subprocess.run(shell=True)`).
  - **CWE-89:** SQL Injection (via dynamic string formatting in database queries).
  - **CWE-22:** Path Traversal (via unvalidated dynamic path concatenation in `open()`).
  - **CWE-95:** Dynamic Code Execution (via unsafe `eval()` on user formulas).
  - **CWE-798:** Hardcoded Sensitive Credentials (private tokens, API keys in source code).
- **Safe Negative Controls:** Syntactically similar safe implementations:
  - Parameterized SQL queries using `?` placeholders.
  - Subprocess invocations with argument lists and `shell=False`.
  - Path confinement using `os.path.basename` or `Path.resolve().is_relative_to()`.
  - Safe math parsing via `ast.literal_eval`.
  - Credential retrieval via `os.environ.get()`.
- **Ground Truth Grounding:** Validated against MITRE CWE definitions and AST pattern inspection.

### 4.3 Performance Bottlenecks & Normal Performance Controls
- **Definition:** Algorithmic complexity defects causing execution latency to exceed the agreed SLA threshold ($T > 200.0\text{ ms}$):
  - $O(N^2)$ pairwise distance calculations over large datasets.
  - Exponential $O(2^N)$ naive recursive Fibonacci without memoization.
  - Exponential $O(3^{M+N})$ naive recursive Levenshtein distance.
  - Repeated uncompiled regex evaluation inside large iteration loops.
  - Quadratic string buffer re-allocation in loops.
- **Normal Performance Controls:** Optimized implementations ($O(N)$ or DP-based) executing identical problem domains in $< 20\text{ ms}$.
- **Ground Truth Grounding:** Profiled container execution duration against proposal threshold $200.0\text{ ms}$.

### 4.4 Integration & API Compatibility Defects
- **Definition:** Inter-service contract violations between Component 3 code and external API/database specifications:
  - Envelope mismatches: Returning raw array instead of mandated `{"status": "success", "data": [...]}` envelope.
  - HTTP status code violations: Returning `200 OK` on resource-not-found instead of `404`.
  - Type serialization mismatches: Emitting float epoch timestamps instead of ISO-8601 strings.
  - Webhook contract violations: Omitting required `X-Webhook-Token` or `X-Hub-Signature-256` headers.
  - Schema mismatches: Emitting flat error strings instead of GraphQL `errors: [{message: ...}]` arrays.
- **Ground Truth Grounding:** Derived from OpenAPI/JSON-Schema contract specifications.

### 4.5 Regression Defects
- **Definition:** Previously passing functionality broken by a secondary requirement change or refactoring:
  - Renaming serialized fields (`full_name` -> `display_name`) breaking legacy consumer integrations.
  - Applying new surcharge fees to zero-rated tax items.
  - Dropping multi-tenant prefixes from cache keys causing cross-tenant cache pollution.
  - Bucket grouping inverting secondary FIFO ordering for equal priority items.
- **Ground Truth Grounding:** Historical regression test suites specifying backwards-compatible behavior.

### 4.6 Semantic Drift Cases (Positive & Negative Controls)
- **Definition:** Modifications to test suites across repair iterations that degrade verification rigor (Proposal FR07, SO5):
  - **Positive Drift:** Weakening strict assertions (`assert res == 42.0` replaced with `assert res is not None` or `assert True`); deleting failure-inducing test cases.
  - **Negative Drift Control:** Legitimate test suite refactoring (variable assignment, parameterization, adding new assertions) that preserves or strengthens semantic rigor.
- **Ground Truth Grounding:** AST comparison of original authoritative test suite against candidate suite via `SemanticDriftService`.

### 4.7 Non-Convergent Repair Loops
- **Definition:** Multi-iteration verification scenarios that fail to achieve clean convergence:
  - Mutually contradictory requirements causing oscillation between alternating patches.
  - Deadlock/timeout patches causing iteration failure.
  - Superficial convergence attempts where candidate patches modify tests rather than source code.
- **Ground Truth Grounding:** Observable multi-iteration execution history in `ControlledRepairLoopHarness`, evaluated against mandatory governance escalation criteria (SO5).

---

## 5. Physical Source-File Line Number Attribution Methodology

Following Phase 2 forensic analysis, physical line numbers in Phase 3 are rigorously grounded in CPython AST and runtime traceback frame coordinates:

1. **CPython AST Coordinate Rule:** In Python, multiline triple-quoted strings declared as `"""\ndef func():..."""` contain a leading newline at line 1. Statement line numbers reported by `ast.parse` and runtime tracebacks are 1-indexed from the first character of the string.
2. **Deterministic Statement Mapping:** The `expected_line_number` in every defective scenario refers to the exact 1-indexed physical line of the defective statement within `module_code`.
3. **Automated Conformance Testing:** Live test `test_phase3_physical_line_numbers_integrity` validates that every non-null `expected_line_number` points to a valid, non-blank statement in the source text.

---

## 6. Cryptographic Manifest & Freeze Attestation

To guarantee complete immutability and reproducibility, the entire Phase 3 dataset is serialized into a machine-readable manifest with SHA-256 checksums:

- **Manifest File:** `component-4/backend/app/benchmark/phase3_manifest.json` (mirrored to `component-4/docs/phase3_manifest.json`)
- **Dataset Version:** `v3.0.0-heldout`
- **Total Scenarios:** 100
- **Overall Manifest SHA-256 Digest:**
  ```
  8cc6d38221d62faea0aebb084d80967ed769e1e7382609b52e8679b0cb85109f
  ```
- **Development Partition (40 Scenarios) SHA-256 Digest:**
  ```
  56638e4172a8f074f51eceb1db44a4a0e96654d9428a2a89b9930ee95a5c082e
  ```
- **Held-Out Partition (60 Scenarios) SHA-256 Digest:**
  ```
  e766bd3ab03bd9a5721fec86f2a2b97ab12702508afad0d8a95549a0027b7465
  ```

Automated test `test_phase3_manifest_hash_stability` verifies at runtime that all in-memory scenario definitions match these exact cryptographic digests.
