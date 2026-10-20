# Defect-Feedback-Driven Scoped Regeneration

This document defines the Component 3 Task 9 method for the generated React +
Node.js Task Management MVP. Given a structured defect report, Component 3
selects the smallest justified set of generated modules from the **verified**
traceability graph, asks the local model to patch only those modules, verifies
that every other file is byte-identical, and publishes a new immutable
generation run and graph version.

Component 3 never claims that a defect is fixed. Retesting, defect explanation
(XAI), semantic-preservation analysis, convergence, and readiness decisions
belong to Component 4. Component 3 returns a retest handoff whose status is
always `PENDING`.

All defect input used so far is **SIMULATED**. No Component 4 integration
exists yet, and no Component 4 evidence has been used or claimed.

## Boundaries

| Concern | Owner | Task 9 behavior |
|---|---|---|
| Requirements, UML, UI | C1 / C2 | Consumed through the provisional contracts. Never edited. |
| Generation, structural checks, trace graph, scoped patch | C3 | Implemented here. |
| Independent test execution, XAI explanations, semantic preservation, convergence | C4 | Not implemented. Handoff is `PENDING`; `repair_success` is `NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST`. |

Generated JavaScript is never imported, installed, built, started, or executed
by Component 3.

## Endpoints

| Endpoint | Calls the model | Writes |
|---|---|---|
| `POST /api/v1/impact-selections` | No | Nothing. |
| `POST /api/v1/scoped-regenerations` | Only when scope is `SELECTED` | A new workspace and a new graph version, only after full verification. |

Both accept a `ScopedRegenerationRequest`: the `DefectReport`, the source
`GenerationManifest`, its workspace path, and the `DesignContext` used for that
run.

### C4 intake by run ID

`POST /api/v1/c4/defect-reports` takes only `{generation_run_id, defect_report}`
(`contracts/c4_intake.py`), because Component 4 does not hold C3's manifest or
`DesignContext`. C3 then:

1. rejects a request whose `generation_run_id` differs from
   `defect_report.source_generation_run_id` (409 `DEFECT_REPORT_RUN_MISMATCH`);
2. loads the newest stored manifest for that run from the traceability store
   (404 `GENERATION_RUN_NOT_FOUND` if no graph exists for the run);
3. locates the run workspace under the workspace root (404
   `GENERATION_WORKSPACE_NOT_FOUND`, 409 `GENERATION_WORKSPACE_AMBIGUOUS`);
4. loads the persisted `DesignContext` by the manifest's
   `design_context_sha256`, recomputing the digest on load (409
   `DESIGN_CONTEXT_NOT_PERSISTED` for runs generated before persistence existed,
   409 `DESIGN_CONTEXT_DIGEST_MISMATCH` for a tampered file);
5. calls the unchanged `ScopedRegenerationService`, so every check on this page
   (digest, graph version, graph verification, impact scope, patch policy,
   preservation) still applies.

On success the response is the existing `C4RetestHandoff` (`retest_status`
`PENDING`). `REVIEW_REQUIRED` and `FAILED` outcomes have no handoff, so they
return 409 with `REGENERATION_REVIEW_REQUIRED` / `REGENERATION_FAILED` and one
entry per reason code carrying the escalation's required action.

`DesignContextStore` (`services/design_context_store.py`) is written by the
generation routes and the demo baseline, content-addressed under
`<traceability store directory>/design-contexts/<sha256>.json`.

## Defect-report contract

Schema `C4_DEFECT_REPORT_PROVISIONAL_V1`, version `1.0`. It is provisional and
must be re-aligned when Component 4 publishes a real contract. Unknown fields
are rejected.

Required report fields: `defect_report_id`, `reported_at_utc`,
`source_classification` (closed enum: `SIMULATED_C4_FIXTURE` for
implementer-authored fixtures, `C4_AGENT_OUTPUT` for a report submitted by
Component 4; any other value is a 422 and the label never relaxes a check),
`source_generation_run_id`, `source_artifact_digest_sha256` (64 hex),
**`source_graph_version`**, and 1 to 3 defects.

`source_graph_version` is mandatory and must be a strict positive integer. A
missing, `null`, zero, negative, string, boolean, or float value fails schema
validation (HTTP 422). A well-formed value must equal the version of the exact
graph snapshot used for impact selection; otherwise the report is rejected as
`STALE_DEFECT_REPORT` (HTTP 409, field `defect_report.source_graph_version`).
This applies to older versions and to versions that do not exist yet. The
earlier optional behavior (an absent version skipped the check) is removed.

Each defect carries `defect_id`, `category`, `severity`, `title`, 1 to 10
`affected_requirement_ids`, 1 to 10 `failing_tests` (a `TEST_FILE` path or a
`TEST_SEAM` id), optional `api_operation_ids`, **required** `evidence`,
**required** `location` with a **required** safe `relative_path` (`symbol`
stays optional), and a **required** non-blank `explanation` (at most 1200
characters). Defect-context retrieval (RAG A) resolves the module from
`location.relative_path` and queries by `explanation`, so a report without
them is rejected at the schema (422) instead of failing later.

Supported categories are `BUSINESS_LOGIC`, `API_CONTRACT`, `DATA_ACCESS`, and
`UI_BEHAVIOR`. `SECURITY`, `PERFORMANCE`, `CONFIGURATION`, and `OTHER` are
recognized but unsupported and always produce `REVIEW_REQUIRED`.

Trust rules:

- `explanation`, `title`, `evidence`, and `location` are **untrusted text**.
  They are control-character checked at the contract, flattened, bounded, and
  stripped of prompt markers before reaching a prompt, and they are never used
  as instructions or as scope.
- `location` can only **narrow** or **corroborate** a scope the graph already
  justifies. It can never add a module.
- `affected_module_ids` style broad hints are not accepted at all.

## Pre-selection rejections (HTTP 409 unless noted)

| Code | Condition |
|---|---|
| `DEFECT_REPORT_RUN_MISMATCH` | Report run ID differs from the manifest run ID. |
| `DEFECT_REPORT_DIGEST_MISMATCH` | Report artifact digest differs from the manifest digest. |
| `ARTIFACT_HASH_MISMATCH` and other manifest codes | Source files fail `ManifestVerificationService`. |
| `GRAPH_SNAPSHOT_NOT_FOUND` (404) | No persisted graph exists for the project. |
| `STALE_DEFECT_REPORT` | The latest graph was built from a different run, or the report's `source_graph_version` is not the latest snapshot's version. |
| `UNVERIFIED_TRACEABILITY_GRAPH` | The persisted graph does not match, in full, a rebuild from the verified manifest (see "Full graph evidence verification"). |
| `DESIGN_CONTEXT_DIGEST_MISMATCH` | The supplied `DesignContext` is not the one bound to the run. |
| `UNKNOWN_REQUIREMENT_ID`, `UNKNOWN_TEST_HOOK`, `UNKNOWN_API_OPERATION` | A defect references something absent from the verified graph. |
| `422` | Malformed report (schema, enum, safe-path, size, duplicate rules). |

Rejections happen before any model call and before any write.

### Full graph evidence verification

Before selecting a scope, `GraphEvidenceVerifier`
(`traceability/graph_verification.py`) compares the persisted snapshot with the
graph that `TraceabilityGraphBuilder` rebuilds from the already verified source
manifest. The comparison is canonical (`C3_CANONICAL_JSON_V1` hashes of whole
records), per field, and deterministic. For every ACTIVE node and link it
checks, by stable identity (`node_id`, `logical_link_id`):

- source and target node IDs and the relation type;
- resolution status, review requirement, and lifecycle status;
- provenance: evidence kind, mapping rule, evidence references, details;
- node module identity, relative paths, and file hashes (attributes);
- missing, extra, and duplicate ACTIVE nodes or links.

A link whose ID is unchanged but whose resolution, review status, relation,
endpoints, or provenance differ is rejected. It also checks the snapshot header
(schema and direction-policy versions, graph and run IDs, artifact, evidence,
and manifest digests, source identity), recomputes requirement coverage, and
recomputes the graph content digest. The tests re-seal the digest after each
tamper, so detection does not depend on the stored digest alone. The error
message lists static problem labels such as `link-mismatch:<id>:review_status`;
it never echoes stored text.

Legacy handling: the only legacy normalization in the traceability code is the
builder's version-aware C2 reverse-direction normalization, selected by the
manifest's `mapping_policy_version`. Rebuilding reproduces it, so such a graph
verifies against its own manifest. No other legacy shape is accepted. Snapshots
without `relation_direction_policy_version` (written before that policy
existed) are rejected rather than guessed at.

Limits: RETIRED history cannot be re-derived from the current manifest, so it
is only checked for internal consistency and covered by the content digest. The
SQLite store is append-only by application convention, not by database
triggers. Verification is read-only and never mutates SQLite or the snapshots.

## Impact-selection algorithm `C3_IMPACT_SELECTION_V1`

Input: the verified latest graph snapshot, the verified manifest, and the
defect report. Only links that are `ACTIVE`, `RESOLVED`, and review
`NOT_REQUIRED` ("usable" links) can justify scope.

For each defect:

1. **Requirement anchor.** Collect modules with a usable `IMPLEMENTS` link to
   any affected requirement. If none exist, the result is `REVIEW_REQUIRED`
   (`MISSING_TRACE_LINKS`, `INSUFFICIENT_EVIDENCE`).
2. **Failing-test path.** For a `TEST_FILE` hook, collect modules with a usable
   `VERIFIED_BY` link to that test file. For a `TEST_SEAM` hook, collect modules
   with a usable `IMPLEMENTS` or `VERIFIED_BY` link to the hook node.
3. **API path.** For each named API operation, collect modules with a usable
   `EXPOSES` link to it.
4. **Eligibility.** A module is a candidate only if it is on the requirement
   path **and** on a test or API path **and** its artifact type is compatible
   with the defect category:

   | Category | Compatible artifact types |
   |---|---|
   | `BUSINESS_LOGIC` | business logic (service) |
   | `API_CONTRACT` | API definition, controller |
   | `DATA_ACCESS` | repository |
   | `UI_BEHAVIOR` | frontend |

   Every other module receives an explicit exclusion with reason codes
   (`CATEGORY_INCOMPATIBLE`, `NOT_ON_FAILING_TEST_OR_API_PATH`,
   `NOT_REACHED_BY_ANY_TYPED_PATH`).
5. **Location.** A valid manifest path from the report corroborates a candidate
   it matches. If several candidates remain and the location matches one, the
   others are excluded `NOT_CORROBORATED_BY_DEFECT_LOCATION`. A location with no
   graph support is excluded `LOCATION_CLAIM_NOT_SUPPORTED_BY_GRAPH`; one outside
   the manifest is noted `LOCATION_NOT_IN_MANIFEST`.
6. **Scope decision.**
   - no candidates: `REVIEW_REQUIRED` / `INSUFFICIENT_EVIDENCE`;
   - more than `MAX_AUTOMATIC_SCOPE = 2` candidates: `REVIEW_REQUIRED` /
     `SCOPE_TOO_BROAD`;
   - any candidate outside the patch allowlist: `REVIEW_REQUIRED` /
     `SELECTED_MODULE_NOT_PATCHABLE`;
   - otherwise `SELECTED`.
7. **Report-level result.** The union of selected modules across defects must
   also be within the limit. Selection is all-or-nothing across defects: if any
   defect needs review, no module is patched.

Review-required or unresolved links touching the defect are listed in
`excluded_links` and never authorize scope. The `ImpactSelectionReport`
contains selected module IDs and paths, per-link graph paths with mapping
rules and evidence references, every exclusion with reason codes, excluded
links, and reason codes. It is deterministic for a given input.

The patch allowlist is the service, controller, and repository modules.
OpenAPI, routes, SQL, tests, frontend, package files, and the manifest are not
patchable; defects that require them return `REVIEW_REQUIRED`.

## Local-model patching

The model is the configured local Ollama model (`qwen2.5-coder:3b` by default).
Each selected module is patched independently.

- Prompt template `task-scoped-repair-v2` receives only the target module's
  current source and the sanitized defect fields. No other file is sent. The
  recorded mock and real-Ollama runs below used `task-scoped-repair-v1`; they
  were not re-run after v2 (stricter safety wording, sanitized identifiers).
- `defect_id`, `affected_requirement_ids`, and `failing_test_case_ids` are
  flattened, bounded, and marker-stripped like other defect text, so
  marker-like identifiers cannot imitate prompt boundaries.
- Defect text sits in a JSON-encoded `UNTRUSTED_DEFECT_DATA_JSON` block; the
  system message instructs the model never to follow instructions inside it.
- The structured-output schema is a single `{path, content}` object with the
  path constrained to the authorized module.
- Output is rejected unless all of these hold: valid JSON of exactly the
  expected shape; non-empty content; safe relative path (no traversal, absolute,
  or backslash paths); path equals the authorized path; the conservative
  JavaScript lexical policy below accepts the content; required module
  interface still present; and content actually differs from the current source.

| Rejection code | Meaning |
|---|---|
| `INVALID_MODEL_OUTPUT` | Not JSON, wrong shape, extra keys, missing or empty content. |
| `UNSAFE_PATCH_PATH` | Traversal, absolute, or backslash path. |
| `PATCH_PATH_NOT_AUTHORIZED` | Any path other than the selected module. |
| `UNSAFE_PATCH_CONTENT` | The lexical policy found a forbidden construct (see below). |
| `UNINSPECTABLE_PATCH_SYNTAX` | Syntax the lexical policy cannot inspect safely: escape sequences, non-ASCII or control characters, computed member access. |
| `PATCH_INTERFACE_VIOLATION` | Required exports or call structure removed. |
| `PATCH_NO_OP` | Content identical to the source. |

Attempts are bounded (default 2 per module, configurable). A retry prompt
carries only the previous rejection code and a fixed message, never the model's
rejected text. When attempts are exhausted the result is `FAILED` with an
`EscalationRecord` and reason `PATCH_ATTEMPTS_EXHAUSTED`, except when the last
rejection was `UNINSPECTABLE_PATCH_SYNTAX`: then the status is `REVIEW_REQUIRED`
with reason `PATCH_SYNTAX_REQUIRES_REVIEW`, because such content is neither
proven unsafe nor accepted. Nothing is written in either case. There is no
fallback to whole-project regeneration.

### JavaScript lexical policy `C3_JS_CONSERVATIVE_LEXICAL_POLICY_V1`

`generation/js_safety.py` is a conservative **lexical deny-list, not a
JavaScript parser, not a sandbox, and not a proof of safety**. It exists to
reject known obfuscation and host-access patterns early in the narrow MVP
modules (service, controller, repository). The same policy is applied to
template and local-model artifacts for those modules in Task 6 generation
(`UNSAFE_GENERATED_CONTENT`) and to Task 9 patches. The earlier regex list is
still enforced.

UNSAFE (word-boundary matches): `import`, `require`, `process`, `node:`
specifiers, `child_process`, `global`, `window`, `self`, `document`,
`navigator`, `Deno`, `Bun`, `WebAssembly`, `Reflect`, `Proxy`; `globalThis`;
`fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, `Worker`,
`SharedWorker`, `importScripts`; `eval`, `Function` and its async/generator
variants; `.constructor` member access and the string `'constructor'`;
prototype manipulation (`__proto__`, `prototype`, `getPrototypeOf`,
`setPrototypeOf`, accessor-definition helpers); timers and deferred execution
(`setTimeout`, `setInterval`, `setImmediate`, `queueMicrotask`,
`requestAnimationFrame`, `requestIdleCallback`).

The one exception is the exact call `globalThis.crypto.randomUUID()` in the
service module only, because the required service interface mandates it.
Any other `globalThis` use, or that call elsewhere, is rejected.

UNINSPECTABLE (conservative rejection, reviewed by a human): `\u`, `\x`, or
octal escape sequences (including unicode-escaped identifiers such as
`\u0072equire`), non-ASCII or control characters, and computed member access
(`obj[key]`, `obj['a' + 'b']`). Array literals after `return`, `=`, `(`, and
similar are not treated as computed access.

Expected false positives: any listed word inside a comment or string literal
(for example a comment that says "process"), a non-ASCII character in a
comment or message, a `\u` or `\x` escape inside an ordinary string, `obj[key]`
lookups, and identifiers named `self`, `global`, or `Worker`. The shipped
template modules and both simulated fixtures pass the policy, so no
legitimate generated module is currently rejected; a model that writes
`obj[key]` or non-ASCII text will be sent to `REVIEW_REQUIRED` and must be
reviewed or re-prompted.

## Atomic publication

1. Every module patch is validated in memory first.
2. A **new** run ID and workspace are created; source bytes are copied and only
   the patched files are replaced. The source run is never modified.
3. A new manifest is written with `generation_mode = SCOPED_REGENERATION`, a new
   recomputed artifact digest and evidence digest, repair prompt hashes, and
   `LOCAL_LLM` origin for patched files. A `regeneration-record.json` sidecar
   stores lineage and the PENDING retest status outside the manifest.
4. The new workspace is verified with `ManifestVerificationService` and the
   evidence digest.
5. A hash-preservation report compares every file's SHA-256: selected files may
   change, every other file must be byte-identical (`collateral_edit_count`
   must be 0).
6. Task 8 structural verification runs on the new run. A `FAIL` blocks
   publication; `REVIEW_REQUIRED` is acceptable because the verifier always
   emits an explicit limitation finding.
7. `compare` then `update` produce graph version N+1 for the new run. Version N
   remains stored and unchanged. Unchanged links are preserved; links touching
   changed files are revalidated; stale links are retired.
8. The retest handoff is created.

If any step fails, only the candidate directory is deleted, the result is
`FAILED`, and the previous run and graph are untouched. If the graph update
fails or an unexpected error occurs, the candidate directory is removed and the
error is raised.

## Worked example (SIMULATED defect)

Baseline: a deliberately defective generated service whose `update` skips the
missing-task check (`tests/fixtures/simulated/scoped_regeneration/buggy_task_service.js`).
Simulated report: `BUSINESS_LOGIC` defect on `REQ-TASK-002` (update a task),
failing test hook `backend/tests/taskService.test.js`, location
`backend/src/services/taskService.js`.

The verified graph (36 nodes, 99 links) contains this chain for `REQ-TASK-002`:

| Layer | Graph evidence |
|---|---|
| Requirement | `REQUIREMENT:REQ-TASK-002` |
| UML / anchor | `UML_ELEMENT:UML-TASK-SEQUENCE-001` and `DESIGN_ANCHOR:ANCHOR-TASK-002` `DERIVED_FROM` the requirement |
| Code | `taskService.js` `IMPLEMENTS` the requirement (`LINK-B36B3A315388262F`) |
| API | `taskController.js`, `taskRoutes.js`, `openapi.yaml`, `frontend/src/api/tasks.js` `EXPOSE` `API_OPERATION:API-OP-TASK-UPDATE` |
| Database | `schema.sql` `DEFINES` `DB-TABLE-TASKS`; `taskRepository.js` `PERSISTS_TO` `DB-TABLE-TASKS` is `UNRESOLVED` / `REVIEW_REQUIRED` |
| Test hook | `taskService.js` `VERIFIED_BY` `backend/tests/taskService.test.js` (`LINK-D711A972E424E693`); service and repository `IMPLEMENT` `TEST_HOOK:SEAM-TASK-REPOSITORY` |

Selection result: `SELECTED`, one module.

| Module | Decision | Reason |
|---|---|---|
| `backend/src/services/taskService.js` | **Selected** | Requirement `IMPLEMENTS` path plus failing-test `VERIFIED_BY` path; business-logic artifact; location corroborates. |
| `taskController.js`, `taskRoutes.js`, `api/openapi.yaml`, `frontend/src/api/tasks.js` | Excluded | `CATEGORY_INCOMPATIBLE` for `BUSINESS_LOGIC` (they are on the API path but of another artifact type). |
| `frontend/src/App.jsx`, `TaskList.jsx` | Excluded | `NOT_ON_FAILING_TEST_OR_API_PATH`. |
| `taskRepository.js`, `schema.sql`, test file, `app.js`, remaining files | Excluded | `NOT_REACHED_BY_ANY_TYPED_PATH`. |

The two `DERIVED_FROM` UI-wireframe links from `App.jsx` and `TaskList.jsx` are
`REVIEW_REQUIRED` and are listed in `excluded_links`. The unresolved
repository-to-table link did not touch the selected scope and does not
authorize any scope.

## Evidence and metrics

Evidence classes are kept separate. `MOCKED_TEST_DOUBLE` runs use a
deterministic fixture response labeled `SIMULATED-MOCK-MODEL-NOT-OLLAMA` and
prove the pipeline, not model quality. `REAL_LOCAL_OLLAMA` runs use the local
model.

### Recorded runs of this method (single run each, 2026-10-13)

| Metric | Mock model (pipeline check) | Real local Ollama |
|---|---|---|
| Final status | `PATCHED_PENDING_INDEPENDENT_RETEST` | `PATCHED_PENDING_INDEPENDENT_RETEST` |
| Modules selected | 1 (`taskService.js`) | 1 (`taskService.js`) |
| Patch accepted on attempt | 1 | 1 |
| Patch lines added / removed | +1 / -0 | +4 / -1 |
| Unchanged files byte-identical | 17 of 17 | 17 of 17 |
| Collateral edit count | 0 | 0 |
| Source artifact digest | `6490bb3a…` | `6490bb3a…` |
| New artifact digest | `c99e46e4…` | `63ad5d83…` |
| Graph version | 1 to 2 | 1 to 2 |
| Links preserved / revalidated / retired | 89 / 10 / 0 | 89 / 10 / 0 |
| Task 8 structural result | 8 pass, 0 fail, 1 review | 8 pass, 0 fail, 1 review |
| Total latency | 383.7 ms | 12768 ms (12224.5 ms model) |
| Repair success | `NOT_EVALUATED` | `NOT_EVALUATED` |

Observations about the real run, stated without overclaiming: the model added a
`findById` / 404 guard to `update` and also rewrote the existing check in
`remove` into the same two-line form. C3 accepted the patch because it passed
structural and safety checks. Nothing executed it, so whether `update` is now
correct and whether the `remove` rewrite preserved behavior are **not
evaluated**. This is exactly the kind of in-module collateral change that
Component 4's semantic-preservation analysis must examine; Component 3's
byte-identical check covers only files outside the selected scope.

### Metric status

| Metric | Status |
|---|---|
| Impact precision / recall / F1 | Calculated on 8 SIMULATED scenarios, labels authored by the implementer (`NOT_INDEPENDENTLY_REVIEWED`): 4 true positives, 0 false positives, 0 false negatives, and 8 of 8 decisions agree. This confirms the algorithm matches its own specification on a small set. It is **not** a benchmark and says nothing about real defects. |
| Unchanged-file preservation | Measured by SHA-256 on the recorded runs and in tests. |
| Patch validity rate | Measured per run (accepted attempts over total attempts). One real-model run is not a rate estimate. |
| Collateral edit count | Measured outside the selected scope only. |
| Latency | Measured for the two runs above. |
| Repair success | `NOT_EVALUATED` until Component 4 retests independently. |
| Semantic preservation within a patched module | `NOT_EVALUATED` (Component 4). |

The scenario set has eight cases: four `SELECTED` (service, controller with
location, repository seam, misleading location) and four `REVIEW_REQUIRED`
(controller whose location does not resolve to a manifest module is too broad,
UI has no resolved evidence,
unsupported category, non-patchable OpenAPI module).

## C3 structural verification versus C4 retesting

The Task 8 gate checks structure only: interface presence, layering, API and
repository contract shape, and file integrity. It cannot show that a defect is
fixed, that behavior is correct, or that no regression occurred. Component 4
must rerun the failing tests and regression checks against the new run and
return its own evidence. Until it does, the handoff reads:

```json
{
  "retest_status": "PENDING",
  "repair_verification": "NOT_ASSERTED_PENDING_INDEPENDENT_C4_RETEST",
  "independent_c4_evidence": "NONE"
}
```

The handoff names the new run ID, artifact digest, graph version, changed
modules, tests to rerun, and requirement IDs to retest.

## Running it

```powershell
# Deterministic pipeline check (mock model, clearly labeled)
python -m intelise_c3.scripts.scoped_regeneration_experiment --model mock

# Real local Ollama (requires the local model to be running)
python -m intelise_c3.scripts.scoped_regeneration_experiment --model ollama

# Optional real-model invariant test (skipped by default)
$env:RUN_OLLAMA_REPAIR_INTEGRATION = "1"
python -m pytest tests/test_scoped_regeneration.py -k real_local_model
```

Output goes to git-ignored `generated-workspaces/experiments/` and
`runtime/traceability/experiments/`.

## Limitations and human-review requirements

### Trigger C RAG integration (provisional)

The real local-Ollama repair path now builds one versioned prompt with two
separate evidence sections:

- `DEFECT_CONTEXT_EVIDENCE_JSON`: RAG A chunks retrieved only from the
  graph-scoped, current module versions using the simulated C4 explanation.
- `BEST_PRACTICE_RULES`: RAG B rule cards filtered for the Node.js module
  layer. These are configured engineering-policy assumptions, not defect
  evidence.

The result and `regeneration-record.json` record the RAG A backend, embedding
model and chunk IDs; RAG B backend, embedding model and rule IDs; old/new
artifact digests; changed files/symbols; and graph versions. Prompt hashes in
the new manifest bind these exact sections to the new run without changing the
historical manifest schema.

`changed_symbols` preserves only a graph-corroborated C4 location claim and is
labelled `GRAPH_CORROBORATED_C4_LOCATION_CLAIM`. It is not an AST-derived
symbol diff.

The deterministic demo endpoint does **not** use RAG and is labelled
`DETERMINISTIC_TEST_DOUBLE`. Only the local-Ollama endpoint may be described as
AI/RAG-driven repair. Test coverage that exercises the RAG orchestration with a
model double is separately labelled `SIMULATED_RAG_TEST_DOUBLE`.

The provisional C4 contract still has no `module_id` and no per-module digest. As an interim adapter, C3 validates the
whole-application digest against the graph, resolves the module from the
location path, and uses the verified manifest file SHA-256 for stale chunk
filtering. Missing or stale RAG A context stops automatic patching with
`INSUFFICIENT_DEFECT_CONTEXT`; C3 does not patch from graph scope alone.

Current acceptance scope:

- C3-06: matching simulated defect evidence can produce one scoped new run,
  digest and graph version, pending independent C4 re-test.
- C3-07: unknown modules and stale/mismatched digests are rejected with an
  explicit request to re-verify the current artifact.
- C3-08: the within-request attempt limit produces a human-review package with
  the defect report, attempt records, rejection reasons and source version.
- C3-09 and C3-10 deployment-readiness decisions are intentionally deferred.

Cross-round repair history, Component 4 non-convergence signals, and Component
4 semantic-preservation flags remain deferred until an approved C4 contract is
available. C3 never edits or executes Component 4's frozen tests and never
treats a C4 suggestion as authoritative defect truth.

- Defect reports are simulated and the contract is provisional.
- Impact precision is only as good as the traceability links. In the current
  graph the generated test file links to the service module only, so controller,
  routes, and client defects need API-operation plus location evidence, and
  broader scopes return `REVIEW_REQUIRED`.
- The traceability evidence mappings are template and capability derived. A
  patch changes file hashes but not these mappings, so no links were retired in
  the recorded runs. Retirement is implemented and unit-tested at the graph
  layer but is not exercised by a real patch.
- Only the service, controller, and repository can be patched. Multi-module
  repairs are capped at two modules. Defects needing OpenAPI, SQL, routes,
  frontend, or test changes need human review.
- Patch checks are lexical and structure based, not a parser or sandbox. They
  reduce risk but do not make model output trusted, and they do not claim
  formal JavaScript security. `app.js` and the frontend are outside the policy
  (they legitimately need `import`, `process.env`, and `fetch`) and are not
  patchable in this task.
- Full graph verification cannot prove the authenticity of historical RETIRED
  records, and the SQLite store has no tamper-evident trigger or signature.
- The real-Ollama experiment recorded below was run with prompt v1 and has not
  been repeated with the v2 prompt and stricter policy.
- The model can also change behavior inside the selected module beyond the
  reported defect. Only Component 4 can judge this.
- The local model is small. One real-model run shows the pipeline works, not
  that repair is reliable.
- A researcher or maintainer must review any `REVIEW_REQUIRED` outcome, any
  `FAILED` escalation, the real diff of any accepted patch, and Component 4
  retest results before the new run is treated as a repair.
- Angular, Spring Boot, cloud deployment, and any non-Task-Management project
  are out of scope.
