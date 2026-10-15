# INTELISE Component 4 — Technical Feedback Loop Hardening & Integration Contract Readiness

## 1. Overview and Architecture

Component 4 (Intelligent Agentic Testing & Feedback Loop Assistant) operates an auditable, evidence-based defect verification and feedback cycle. When a test suite fails against submitted code, Component 4 synthesizes structured diagnostic feedback derived directly from pytest results.

This document defines the hardened integration contract, payload validation specifications, human explanation isolation rules, delivery lifecycle states, idempotency guarantees, and the 6-point contract readiness checklist required before live outbound transmission to Component 3 (Code Generation & Repair Service) can be enabled.

---

## 2. Technical Feedback Payload Specification

The technical feedback package is formatted as `TechnicalFeedbackPayload` (Schema Version `1.0`). It is strictly derived from actual persisted verification evidence. No source line numbers, file paths, or defect assertions are ever fabricated or guessed.

### Payload Schema

| Field Name | Type | Presence | Description |
| :--- | :--- | :--- | :--- |
| `feedback_id` | `string` | Required | Unique feedback package identifier (`fb-...`) |
| `verification_run_id` | `string` | Required | Associated verification run identifier (`run-...`) |
| `submission_id` | `string` | Required | Associated code submission identifier (`sub-...`) |
| `verification_status` | `string` | Required | Run outcome status (`FAILED` or `ERROR`) |
| `affected_files` | `list[string]` | Required | Confirmed source files involved in failure (from metadata/defects) |
| `failed_tests` | `list[string]` | Required | Specific test case names that failed or encountered errors |
| `failed_assertions` | `list[string]` | Optional | Raw failed assertion statements from pytest output |
| `value_comparisons` | `list[object]` | Optional | Structured `expected` vs `observed` data for assertion failures |
| `error_logs` | `list[string]` | Optional | Bounded traceback excerpts (max 15 lines, max 500 chars per line) |
| `test_failure_details` | `list[object]` | Optional | Detailed test outcome dictionaries including duration and error message |
| `defect_ids` | `list[string]` | Required | Unique defect identifiers (`def-...`) matching persisted defect reports |
| `evidence_references` | `object` | Optional | Deterministic telemetry references (`total_tests`, `exit_code`, etc.) |
| `generated_at` | `string (ISO 8601)` | Required | UTC timestamp when the payload was synthesized |
| `schema_version` | `string` | Required | Contract version (currently `"1.0"`) |

### Validation Rules

1. **Identifier Integrity**: `feedback_id`, `verification_run_id`, and `submission_id` must be non-empty strings. When evaluated against a persisted run, `verification_run_id` and `submission_id` must match the persisted record exactly.
2. **Defect Referencing**: Every item in `defect_ids` must correspond to a persisted `DefectReport` in the verification run. Unpersisted or fabricated defect IDs trigger an immediate rejection.
3. **Test Integrity**: Every item in `failed_tests` must correspond to a verified failed test case from pytest execution.
4. **Graceful Handling of Optional Evidence**: If a failed test does not produce an assertion comparison (e.g., unexpected runtime exception or timeout), `value_comparisons` and `failed_assertions` remain empty lists without invalidating the payload.
5. **No Fabricated Locations**: File names and line numbers are included only if corroborated by pytest tracebacks or submission metadata. Missing line numbers remain `None` rather than fabricated guesses.

---

## 3. Human Explanation Isolation

Human-facing explanations are strictly isolated from machine-directed repair payloads. Component 4 features Explainable AI (XAI) capabilities designed to provide natural language narratives, executive summaries, and investigative suggestions to human engineers. These narratives must **NEVER** leak into machine repair payloads intended for Component 3.

### Forbidden Fields

The following fields and concepts are strictly forbidden in machine-directed feedback:

- Executive summaries (`summary`, `executive_summary`)
- Human recommendations (`recommendation`, `recommendations`)
- XAI narrative interpretations (`xai_explanation`, `what_failed`, `confirmed_observations`, `evidence_based_interpretation`, `narrative`, `internal_reasoning`)
- Investigative suggestions (`suggested_investigations`)
- Provider and model metadata (`provider`, `explanation_method`, `model_name`, `tokens_used`)
- Internal credentials (`api_key`, `token`, `password`, `secret`, `mongodb_uri`)

### Enforcement Mechanisms

1. **Pre-Dispatch Payload Validation**: `TechnicalFeedbackService.validate_technical_feedback_payload()` recursively scans every key in the dictionary representation of the payload. If any forbidden key is detected, it raises an `InvalidInputException`, blocking dispatch.
2. **Outbound Client Sanitization**: `Component3Client.prepare_sanitized_payload()` scrubs all forbidden keys and verifies that only contractually authorized technical fields are serialized.
3. **Automated Regression Tests**: Dedicated tests verify that injected narrative fields, provider metadata, and human recommendations are rejected and scrubbed.

---

## 4. Approval and Dispatch Eligibility

Component 4 enforces strict human governance over technical repair dispatch.

### Eligibility Rules

1. **Failed Runs Only**: Only verification runs in `FAILED` status (or `ERROR` with application code defects) are eligible. Runs in `PASSED`, `PENDING`, or `RUNNING` status are strictly ineligible.
2. **Infrastructure Segregation**: Runs that failed due to Docker isolation, daemon unavailability, or runner image errors are classified as infrastructure failures and are ineligible for code repair feedback.
3. **Explicit Human Approval**: Technical feedback cannot be dispatched without explicit human approval recorded on the iteration record (`approval_status == "APPROVED"`).
4. **Approval Does Not Trigger Dispatch**: Recording human approval updates the iteration's approval status, timestamp, and notes, but leaves `delivery_status` as `NOT_DISPATCHED`. Outbound HTTP transmission requires a separate, explicit dispatch request.
5. **No Duplicate Iterations on Repeated Approval**: Approving an already approved iteration or submitting identical approval requests idempotently updates approval metadata and notes without appending redundant iteration records.
6. **Reviewer Identity**: Reviewer identity (`approver`) is client-supplied for audit trail purposes and is not independently authenticated via cryptographic signatures or SSO in this milestone.

---

## 5. Delivery Lifecycle and State Model

Every feedback cycle is tracked as a `FeedbackIteration` with a well-defined delivery state machine:

```
[NOT_DISPATCHED] (Created upon failure; approved by human)
       │
       ▼ (Dispatch initiated)
[PENDING_DELIVERY] (Atomic lock acquired; persisted to database)
       │
       ├───────────────────────────────┬───────────────────────────────┐
       ▼ (200/201/202 with job_id)     ▼ (4xx/5xx/Refused/Bad Ack)     ▼ (Timeout after transmission)
[ACKNOWLEDGED]                      [FAILED]                        [UNKNOWN]
(Remote receipt verified)           (Confirmed transmission failure) (Outcome ambiguous; retry suppressed)
```

### State Definitions

- **`NOT_DISPATCHED`**: Initial state. Technical feedback is prepared and optionally approved, but outbound transmission has not been executed.
- **`PENDING_DELIVERY`**: Outbound HTTP dispatch is currently in progress. Serves as an atomic in-flight lock to prevent concurrent dispatch requests.
- **`ACKNOWLEDGED`**: Component 3 acknowledged receipt with an HTTP 200/201/202 status and a confirmed, non-empty `job_id` or `task_id`.
- **`FAILED`**: Confirmed transmission failure (DNS error, connection refused, HTTP 4xx/5xx, or invalid/empty acknowledgment identifier).
- **`UNKNOWN`**: Remote outcome cannot be determined (e.g. read timeout after payload transmission). The remote service may have received and begun processing the payload. Automatic retries are suppressed to prevent duplicate repair jobs.

---

## 6. Idempotency and Concurrency Protection

To guarantee safe delivery across repeated clicks, network retries, and concurrent backend requests:

1. **Run-Level Concurrency Serialization**: `VerificationService` maintains an asynchronous concurrency lock per `run_id`. Concurrent dispatch requests for the same run are queued and processed sequentially.
2. **In-Flight Lock Protection**: If an iteration is in `PENDING_DELIVERY` state, concurrent dispatch requests are immediately rejected with an error.
3. **Deduplication on Acknowledged Iterations**: If an iteration is already in `ACKNOWLEDGED` state and `force_retry` is not explicitly set to `True`, dispatch returns the existing iteration without sending duplicate network requests.
4. **Correlation Tracing**: Each dispatch attempt generates an end-to-end tracing correlation identifier (`X-Correlation-ID`) and an `Idempotency-Key` sent in request headers.
5. **Timeout Safety**: Ambiguous timeouts transition the delivery state to `UNKNOWN`. Automated retries are suppressed unless explicit manual retry (`force_retry=True`) is requested.

---

## 7. MongoDB Persistence and Audit Trail

Audit records are stored within the `verification_runs` collection under `feedback_iterations`.

### Audit Fields

- `iteration_id`: Unique cycle identifier (`iter-...`)
- `iteration_number`: Sequential index (1, 2, ...)
- `verification_run_id`: Associated run identifier
- `submission_id`: Associated submission identifier
- `defects_count`: Number of reported defects
- `defect_ids`: List of reported defect IDs
- `approval_status`: `APPROVED`, `NOT_REQUESTED`, `REJECTED`
- `approved_at`: UTC timestamp of human approval
- `approved_by`: Client-supplied reviewer identifier
- `delivery_status`: Current lifecycle state
- `dispatch_attempt_id`: Unique attempt ID (`disp-...`)
- `attempt_count`: Total number of dispatch attempts
- `attempt_timestamps`: Historical array of UTC attempt timestamps
- `last_attempt_at`: UTC timestamp of most recent dispatch attempt
- `correlation_id`: Correlation tracing identifier
- `component_3_job_id`: Remote job ID from acknowledgment
- `component_3_acknowledged`: Boolean receipt confirmation flag
- `error_category`: Categorized error (`COMPONENT_3_DISABLED`, `TIMEOUT`, `CONNECTION_ERROR`, `CONFIG_ERROR`, `INVALID_ACKNOWLEDGMENT`)
- `sanitized_error_message`: Sanitized error message without credentials or stack traces
- `created_at` / `updated_at`: UTC audit timestamps

### Backward Compatibility

All newly introduced fields have default values (`attempt_count=0`, `attempt_timestamps=[]`, `sanitized_error_message=None`). Historical MongoDB documents created in previous milestones load seamlessly without schema validation errors. No destructive migrations or collection modifications are required.

---

## 8. Component 3 Integration Contract Readiness Checklist

Component 3 currently provides an early input validation API (`/api/v1/validate-input`) and health route (`/api/v1/health`), but does not yet expose a verified code-correction feedback receiver endpoint.

Therefore, `COMPONENT_3_ENABLED` remains `False` by default, and live dispatch remains safely disabled.

### The 6-Point Readiness Checklist

Before live outbound dispatch can be enabled in production, the following six conditions must be satisfied:

| # | Readiness Requirement | Status | Verification Criteria |
| :--- | :--- | :--- | :--- |
| **1** | **Verified Receiver URL** | ❌ Blocked | Must be a dedicated external URL. Default `http://127.0.0.1:8000` (Component 4's own host) is treated as a self-referential placeholder and rejected. |
| **2** | **Confirmed Endpoint** | ❌ Pending C3 | Component 3 must publish and confirm a live correction feedback endpoint (e.g. `/api/v1/correction-feedback`). |
| **3** | **Agreed Request Schema** | ❌ Pending C3 | Component 3 team must formally approve the `TechnicalFeedbackPayload` Schema Version `1.0`. |
| **4** | **Agreed Acknowledgment Schema** | ❌ Pending C3 | Component 3 must agree to return a JSON acknowledgment containing a non-empty `job_id` or `task_id` under HTTP 200/201/202. |
| **5** | **Safe Idempotency & Retry Contract** | ❌ Pending C3 | Component 3 must document receiver deduplication behavior for `Idempotency-Key` headers on retried requests. |
| **6** | **Explicit Configuration** | ❌ Disabled | `COMPONENT_3_ENABLED` must be explicitly set to `True` in `.env` after criteria 1–5 are verified. |

---

## 9. Failure Handling and Error Categories

All client interactions fail closed with structured, user-safe error categories:

| Error Category | Trigger Scenario | Delivery State | User-Safe Message |
| :--- | :--- | :--- | :--- |
| `COMPONENT_3_DISABLED` | `COMPONENT_3_ENABLED=False` | `NOT_DISPATCHED` | Component 3 feedback receiver is under development. Outbound delivery is disabled. |
| `CONFIG_ERROR` | Placeholder or self-referential URL (`127.0.0.1:8000`) | `NOT_DISPATCHED` | Configured receiver address is a placeholder. A verified external address is required. |
| `TIMEOUT` | Request timed out during transmission | `UNKNOWN` | Request timed out after transmission. Remote delivery outcome is unknown. |
| `CONNECTION_ERROR` | DNS resolution failure or connection refused | `FAILED` | Cannot establish network connection to external repair service. |
| `INVALID_ACKNOWLEDGMENT`| HTTP 200/202 but missing or empty `job_id` | `FAILED` | Receiver responded but returned an invalid or missing acknowledgment identifier. |
| `COMPONENT_3_ERROR_RESPONSE` | HTTP 4xx or 5xx returned by receiver | `FAILED` | External repair service rejected feedback with HTTP error status. |
| `CLIENT_ERROR` | Internal client or serialization error | `FAILED` | Unexpected error communicating with external repair service. |
