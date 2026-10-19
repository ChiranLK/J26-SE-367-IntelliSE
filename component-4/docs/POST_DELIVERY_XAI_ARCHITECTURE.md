# INTELISE Component 4 — Post-Delivery Code Understanding XAI Architecture

## 1. Executive Summary & Architectural Motivation

In automated software engineering pipelines, particularly within the INTELISE framework, software synthesis and verification are decoupled into distinct collaborative components:
- **Component 3 (Synthesis & Code Generation)**: Generates source code from functional specifications, user requirements, and architecture models.
- **Component 4 (Verification, Evaluation & Governance)**: Executes sandboxed multi-agent verification, detects functional and non-functional defects, evaluates deployment readiness, and delivers explainable artificial intelligence (XAI).

### 1.1 The Architectural Paradigm Shift

Early iterations of Component 4 explored exposing intermediate defect diagnostics and root-cause explanations directly to end users whenever automated verification failed. However, rigorous user-centered analysis and research evaluation revealed a fundamental flaw with that design:

> **Core Axiom**: The end user did not write the generated code and possesses neither the domain context of intermediate LLM synthesis artifacts nor the authorization to manually edit generated modules mid-stream. Exposing transient assertions, raw stack traces, and intermediate repair hypotheses induces **cognitive fatigue** and undermines trust in the autonomous system.

Consequently, human-facing Explainable AI (XAI) within Component 4 is decisively redirected toward **Post-Delivery Code Understanding**:
1. **Internal Verification Workflow (Machine-to-Machine)**: When verification fails, Component 4 generates structured, machine-actionable **Technical Repair Feedback** routed exclusively to Component 3 for automated iterative repair. Human-facing XAI is withheld (`BLOCKED_VERIFICATION_FAILED`) during intermediate repair cycles.
2. **Post-Delivery Code Understanding (Human-Facing)**: Only when candidate code passes all test oracles, clears deployment-readiness governance, and is confirmed delivered to downstream environments does Component 4 unlock rich, multi-dimensional code explanations. This empowers engineers and non-technical stakeholders to comprehend, audit, and confidently operate the final software.

---

## 2. End-to-End System Workflow

The following sequence illustrates the dual-track lifecycle: internal closed-loop automated repair versus gated post-delivery human XAI delivery.

```
       +-----------------------+
       | Component 3 (Synth)   |<------------------------------------+
       +-----------+-----------+                                     |
                   | Generates Candidate Code                        |
                   v                                                 |
       +-----------------------+                                     |
       | Component 4 Sandbox   |                                     |
       | Verification Pipeline |                                     |
       +-----------+-----------+                                     |
                   |                                                 |
         [Tests Passed?]                                             |
          /          \                                               |
       NO             YES                                            |
        |              |                                             |
        v              v                                             |
+---------------+ +-------------------------+                        |
| Defect        | | Governance Policy Engine|                        |
| Analysis Svc  | | (Security, Perf, Drift) |                        |
+-------+-------+ +------------+------------+                        |
        |                      |                                     |
        v                [Gov Passed?]                               |
+---------------+        /           \                               |
| Technical     |      NO             YES                            |
| Feedback Svc  |       |              |                             |
+-------+-------+       |              v                             |
        |               |      +-------------------------------+     |
        +---------------+      | Software Deployed / Delivered |     |
        |                      +---------------+---------------+     |
        | (Machine Feedback)                   |                     |
        +----------------------------->  [Delivery Confirmed?]       |
                                         /                   \       |
                                       NO                     YES    |
                                        |                      |     |
                                        v                      v     |
                             +--------------------+  +----------------------+
                             | Human XAI State:   |  | Post-Delivery XAI    |
                             | PENDING_DELIVERY   |  | Code Understanding   |
                             | (Explanations Held)|  | - 8 Core Dimensions  |
                             +--------------------+  | - Beginner/Tech Views|
                                                     +----------------------+
```

### 2.1 Internal Verification & Repair Workflow (Failed Runs)

When verification fails, Component 4 suppresses user-facing explanations and produces an internal `TechnicalFeedbackPayload` adhering to proposal requirement **FR04** and **SO3**:
- **Execution Telemetry**: Pass/fail statistics, execution duration, and sandbox exit codes.
- **Defect Classifications**: Categorized defect taxonomy (e.g., `FUNCTIONAL_BUG`, `SECURITY_VULNERABILITY`, `REGRESSION_DEFECT`, `SEMANTIC_DRIFT`).
- **Precise Seam Localization**: Implicated file path, AST node, and line number (e.g., `host_service.py:4`).
- **Assertion and Traceback Diagnostics**: Authorized oracle expected vs. observed values, sanitised exception summaries.
- **Traceability Linkages**: Mapping back to Component 3 requirement IDs (`requirement_ids`) to guide scoped localized regeneration.

---

## 3. The 3-Phase Delivery Gate

User-facing code understanding explanations are strictly guarded by a deterministic 3-Phase Delivery Gate implemented in `PostDeliveryXaiService`:

$$\text{Eligible For Post-Delivery XAI} \iff V_{\text{passed}} \land G_{\text{approved}} \land D_{\text{confirmed}}$$

```
+-----------------------------------------------------------------------------------+
|                              3-PHASE DELIVERY GATE                                |
+------------------------+--------------------------+-------------------------------+
| Phase 1: Verification  | Phase 2: Governance      | Phase 3: Downstream Delivery  |
| - 100% Tests Passed    | - No Critical CWEs       | - Deployment confirmation     |
| - Zero Test Failures   | - Performance within SLA | - Artifact hash verification  |
| - Clean Sandbox Exit   | - Zero Semantic Drift    | - Environment registration    |
+------------------------+--------------------------+-------------------------------+
```

### Gate Verdict Evaluation Matrix

| Verification Status | Governance Status | Delivery Confirmation | Delivery Gate Verdict | User-Facing XAI Action |
|:---|:---|:---|:---|:---|
| `FAILED` | Any | Any | `BLOCKED_VERIFICATION_FAILED` | Suppressed; Technical feedback routed to C3. |
| `ERROR` (Infra) | Any | Any | `BLOCKED_INFRASTRUCTURE_ERROR` | Suppressed; Sandbox infrastructure alert. |
| `PASSED` | `REJECTED` | Any | `BLOCKED_GOVERNANCE_REJECTED` | Suppressed; Compliance violations flagged. |
| `PASSED` | `APPROVED` | Missing / False | `PENDING_DELIVERY_CONFIRMATION`| Pending state; Explanations withheld until delivery. |
| `PASSED` | `APPROVED` | Confirmed (`True`) | `CONFIRMED_DELIVERED` | **UNLOCKED**: 8-dimension understanding generated. |

---

## 4. The 8 Dimensions of Post-Delivery Understanding

When an artifact achieves `CONFIRMED_DELIVERED`, Component 4 synthesizes comprehensive documentation across 8 orthogonal dimensions, derived strictly from empirical AST code analysis and execution telemetry:

```
+---------------------------------------------------------------------------------------+
|                       8 DIMENSIONS OF POST-DELIVERY UNDERSTANDING                     |
+-----------------------------+---------------------------------------------------------+
| Dimension                   | Scope & Grounded Evidence                               |
+-----------------------------+---------------------------------------------------------+
| 1. Software Overview        | High-level purpose, primary capabilities, execution     |
|                             | paradigm, and verified runtime environment.             |
| 2. Architecture Explanation | Structural composition, imported standard/third-party   |
|                             | libraries, class hierarchies, and execution entry-point.|
| 3. Module Responsibilities  | Exact breakdown of generated files, AST functions,      |
|                             | classes, and operational purpose of each element.       |
| 4. Important Functions      | Signatures, docstrings, typed parameters, return types,  |
|                             | line boundaries, and verified operational behavior.     |
| 5. API & Data Flow          | Data transformation pipelines, input parameters,        |
|                             | return data structures, and external protocol bindings. |
| 6. Algorithms & Decisions   | Algorithmic patterns, complexity choices, trade-offs,   |
|                             | error-handling paradigms, and state management models.  |
| 7. Setup & Usage            | Prerequisites, dependency installations, invocation     |
|                             | patterns, and verified runnable execution examples.     |
| 8. Limitations & Scope      | Explicit boundaries, unsupported edge conditions,       |
|                             | single-thread vs concurrent scope, and assumptions.     |
+-----------------------------+---------------------------------------------------------+
```

---

## 5. Dual Presentation Levels: Beginner vs. Technical

To cater to diverse organizational stakeholders, post-delivery explanations are presented at two calibrated cognitive levels:

### 5.1 Beginner-Friendly View (`BeginnerExplanation`)
- **Target Audience**: Business analysts, product owners, end-user operators, novice programmers.
- **Stylistic Characteristics**:
  - Conceptual, plain-English summaries avoiding dense compiler terminology.
  - Practical analogies illustrating how data moves through the application.
  - Plain-language walkthroughs of "What it does", "How to try it", and "Things to keep in mind".
  - Code-free interaction demonstrations.

### 5.2 Technical Engineering View (`TechnicalExplanation`)
- **Target Audience**: Software engineers, systems architects, code reviewers, DevOps personnel.
- **Stylistic Characteristics**:
  - Strict AST-grounded function catalogs with line-number locations (`main.py:12-48`).
  - Textual/Mermaid architectural data-flow diagrams.
  - In-depth analysis of algorithmic time/space complexities and state mutability.
  - Explicit error-handling topologies (e.g., exception hierarchies, retry policies).
  - Security considerations (sanitized secrets handling, input validation boundaries).

---

## 6. Grounding Integrity & Zero-Hallucination Guarantee

To prevent LLM hallucination—a recognized failure mode in automated code documentation—Component 4 enforces strict deterministic grounding through `CodeAnalysisService`:

```
              +------------------------------------------+
              |           Submitted Source Code          |
              +--------------------+---------------------+
                                   |
                   +---------------+---------------+
                   |                               |
                   v                               v
    +------------------------------+ +------------------------------+
    |   AST Syntax Tree Parser     | | Multi-Pattern Redaction Svc  |
    | - FunctionDef, AsyncFunction | | - AWS AKIA/ASIA Access Keys  |
    | - Arguments & Type Annotations| | - RSA/EC Private Key PEMs   |
    | - ClassDef & Base Classes    | | - JWT & Bearer Tokens        |
    | - Import & ImportFrom nodes  | | - Hardcoded password strings |
    +--------------+---------------+ +--------------+---------------+
                   |                                |
                   +---------------+----------------+
                                   |
                                   v
             +-------------------------------------------+
             | Grounded Abstract Syntax Model            |
             | - Only functions present in AST are cited |
             | - Line numbers verified against source    |
             | - Secrets completely redacted prior to XAI|
             +-------------------------------------------+
```

1. **AST-Enforced Identity**: The XAI engine will **never** document a function, parameter, or module that does not exist in the parsed Python AST. Tests explicitly assert that fabricated function names never appear in generated explanations.
2. **Secrets & Credentials Sanitization**: Source code and execution traces are subjected to regex redaction filters before ingestion into explanation synthesis. All tokens matching `AKIA[0-9A-Z]{16}`, `-----BEGIN PRIVATE KEY-----`, `Bearer eyJ...`, or credentials assignments are replaced with `[REDACTED_SECRET]`.

---

## 7. Data Models & API Specifications

### 7.1 Delivery Confirmation Schema (`app/schemas/delivery.py`)

```python
class DeliveryConfirmationCreate(BaseModel):
    artifact_id: str
    target_environment: str = Field(default="production")
    delivery_channel: str = Field(default="automated_pipeline")
    recipient_identifier: Optional[str] = None
    notes: Optional[str] = None

class DeliveryConfirmation(BaseModel):
    delivery_id: str
    verification_run_id: str
    submission_id: str
    artifact_id: str
    target_environment: str
    delivery_channel: str
    recipient_identifier: Optional[str]
    is_delivered: bool
    delivered_at: datetime
    notes: Optional[str]
```

### 7.2 REST Endpoints

1. **Confirm Artifact Delivery**:
   - `POST /api/v1/verifications/{run_id}/delivery-confirmation`
   - Unlocks the 3rd phase of the delivery gate for the verified artifact.
2. **Inspect Delivery Confirmation**:
   - `GET /api/v1/verifications/{run_id}/delivery-confirmation`
   - Returns metadata regarding timestamp, environment, and delivery channel.
3. **Retrieve Post-Delivery Explanation**:
   - `GET /api/v1/verifications/{run_id}/post-delivery-explanation`
   - Returns the full 8-dimension explanation or gate denial status.
4. **Standard Explanation Endpoint (Backward-Compatible)**:
   - `GET /api/v1/verifications/{run_id}/explanation`
   - Populates `delivery_gate`, `delivery_status`, and `post_delivery_explanation`.

---

## 8. Alignment with University Research Proposal

This architecture directly addresses and satisfies the formal research objectives:

- **Specific Objective 3 (SO3)**: Establish verifiable automated feedback loops between Component 3 and Component 4 without human interference during intermediate repairs.
- **Functional Requirement 04 (FR04)**: Structure defect reports as machine-actionable traceability payloads rather than open-ended user dialogues.
- **Research Question 3 (RQ3)**: How does post-delivery code explanation impact human developer comprehension and trust compared to intermediate defect alerts? (Evaluated in `POST_DELIVERY_XAI_EVALUATION_PLAN.md`).
