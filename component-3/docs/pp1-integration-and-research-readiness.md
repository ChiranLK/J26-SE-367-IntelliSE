# PP1 integration and research readiness

Audit completed: 2026-10-16. Target presentation: 2026-10-21.

This is an evidence map and operator runbook, not a claim that the research is
complete. C1/C2/C4 integration remains unproven, C4 retesting is `PENDING`, and
deployment is `BLOCKED`.

## 1. Repository and integration audit

The audited Component 3 commit was
`b3f96c570ca53da1ad94a9225adf75a199f09c74` on
`component-3/07-progress-demo`. Task 10 is present in `origin/develop` through
merge commit `95c6fd8aeebf3f907de410653735baed70eec7a2` (PR 35). The later
`frontend/` and `backend/` organization commits are on the feature branch and
not yet in that integration commit. This document does not authorize or perform
a merge.

### C1 -> C3: `BLOCKED_BY_UPSTREAM`

The checked-out C1 API exposes projects with status `draft` and extraction runs
whose candidates have `review_status: unreviewed`:

- `../component-1/backend/src/intelise_c1/api/project_schemas.py`
- `../component-1/backend/src/intelise_c1/api/extraction_schemas.py`
- `../component-1/backend/src/intelise_c1/api/extractions.py`

C1 does preserve generated requirement UUIDs, a source discussion hash, model
identifier, and prompt version. It does not currently expose an approved SRS
release with authoritative approval state/provenance and SRS version. C3 must
not convert `unreviewed` candidates into `APPROVED` requirements.

C1 must provide or approve a versioned handoff containing:

- stable `project_id`, `srs_version`, and contract/schema version;
- non-empty stable requirement IDs, titles/text, and per-requirement approved
  state;
- approved release state plus an approval provenance reference and validation
  report identity;
- issuer/trust and artifact-identity rules, not only opaque JSON strings; and
- one agreed API or signed/exported artifact plus representative accepted and
  rejected examples.

### C2 -> C3: `BLOCKED_BY_UPSTREAM`

The inspected C2 implementation at `origin/main`
`12f4c8580b4ed8ed2f9040e494768db373f993a0` exposes `/generate`, `/validate`,
`/runs`, and `/runs/{id}`. A run preserves project text, diagram type, rounds,
PlantUML, validator feedback, and `valid_final`. Its sample SRS has requirement
IDs. It does not emit C3's required design-release envelope: release version,
source SRS version, stable UML element IDs, stable requirement-to-UML anchor
IDs, structured UI artifact identities, validation report identity, and
`VALIDATED` release status. A syntax-valid round is not automatically an
approved design release.

C2 must provide or approve:

- `project_id`, `source_srs_version`, `uml_version`, and contract version;
- release status `VALIDATED`, validation state, and validation report identity;
- stable UML element IDs with diagram type/name and exact PlantUML source;
- stable anchor IDs mapping exact C1 requirement IDs to exact UML IDs;
- stable structured UI/wireframe IDs, artifact types, and resolvable source
  references; and
- one frozen handoff fixture and an endpoint/export ownership agreement.

Until those fields exist, C3's package in
`backend/src/intelise_c3/contracts/provisional_input.py` remains explicitly
provisional and simulated. No adapter is implemented because filling missing
approval, release, identity, or provenance data would fabricate evidence.

### C4 -> C3: `NOT_VERIFIED`

The inspected C4 branch has a provisional outbound client, but its own
`Component3Client.get_status()` marks the endpoint, request schema,
acknowledgment schema, and retry/idempotency behavior unconfirmed. C3 currently
accepts only `SIMULATED_C4_FIXTURE` in
`backend/src/intelise_c3/contracts/defect_report.py`. A real C4 handoff needs a
jointly approved versioned schema, exact run/graph identities, authentication,
idempotency semantics, acknowledgment contract, and an independent retest
response. C3 must not claim C4 readiness before that contract exists.

## 2. Novelty 1: living requirement traceability evidence

The local Task 10 store
`runtime/traceability/task10-acceptance-20261015.sqlite3` contains graph
`GRAPH-80F188453F830E9D`, versions 1 through 6. This is real C3 algorithm output
over **simulated C1/C2 inputs**, not real upstream integration evidence.

Version 6 is tied to generation run
`0694de03-d8bd-4ac3-bc9f-c6d261e09182` and has:

- 36 active typed nodes and 99 active typed links;
- 3 requirements classified `VERIFIED` by the C3 trace-evidence coverage rule;
- 4 active `UNRESOLVED` / `REVIEW_REQUIRED` links; and
- graph content digest
  `daa712fb2a34611cba9d9c197d29d5eba848337616b79c0fb0ab2a5ad6895364`.

`VERIFIED` here means the graph contains resolved `IMPLEMENTS` and
`VERIFIED_BY` evidence. It does not mean tests were executed, C4 approved the
result, or the requirement is semantically correct.

A reviewable example chain is:

```text
DESIGN_ANCHOR:ANCHOR-TASK-001
  DERIVED_FROM -> REQUIREMENT:REQ-TASK-001
UML_ELEMENT:UML-TASK-CLASS-001
  DERIVED_FROM -> REQUIREMENT:REQ-TASK-001
CODE_MODULE:FILE-017F30BBE617 (backend/src/services/taskService.js)
  IMPLEMENTS -> REQUIREMENT:REQ-TASK-001
CODE_MODULE:FILE-017F30BBE617
  VERIFIED_BY -> CODE_MODULE:FILE-F8399082BF7B (taskService.test.js)
CODE_MODULE:FILE-017F30BBE617
  VERIFIED_BY -> TEST_HOOK:SEAM-TASK-REPOSITORY
```

The API and database branches are separately typed: controller/route/OpenAPI
modules `EXPOSE` exact `API-OP-TASK-*` identities, while `schema.sql` `DEFINES`
the `DB-TABLE-TASKS` table and columns. Runtime repository
`PERSISTS_TO DB-TABLE-TASKS` remains unresolved because persistence is
`IN_MEMORY`. Three UI-to-wireframe links are also review-required because the
provisional input has no authoritative UI-to-file mapping.

Versions 4 -> 5 -> 6 show the same stable file identity for the service while
its SHA-256 and graph digest change. The other 17 file hashes remain identical.
History is append-only; it is not overwritten.

Measurable outputs include node/link counts by type and status, dangling nodes,
coverage status counts, graph-update added/changed/removed/unchanged sets,
retired links, deterministic rebuild equality, and precision/recall/F1 only
against a genuinely human-reviewed ground truth. The current simulated unit
oracle is not independently reviewed, so research precision/recall/F1 remains
`NOT_VERIFIED`.

## 3. Novelty 2: graph-guided scoped regeneration evidence

Task 10's reviewable sequence is:

1. baseline local run `c9d24a07-4272-463d-8134-93427dc215ff`, artifact digest
   `20d1ceda...a74c65`;
2. simulated defective baseline `ad217cf7-d9f9-49a2-a602-24a289d78e80`, digest
   `6490bb3a...934ec4`; and
3. scoped repaired candidate `0694de03-d8bd-4ac3-bc9f-c6d261e09182`, digest
   `c99e46e4...5b39b6`.

For baseline -> defective and defective -> candidate, only
`backend/src/services/taskService.js` changed and all other 17 manifest files
retained identical SHA-256 values. The selected module is justified through the
intersection of resolved requirement, failing-test/API, artifact-category, and
optional corroborating location evidence. Unreached, category-incompatible,
review-required, or over-broad modules are returned with exclusion reasons.

The repair adds the missing not-found guard before repository update. C3 can
claim only that the patch was scope-authorized, output-policy accepted,
hash-preserving for unselected files, structurally inspected, and recorded as a
new immutable run and graph version. It cannot claim the defect was fixed. The
C4 handoff remains `PENDING`; deployment remains `BLOCKED`.

## 4. Manual evaluation dataset and baseline plan

Use `docs/templates/pp1-evaluation-dataset-template.json`. The researcher and
an independent reviewer must inspect the source requirement/UML, expected typed
links, defect evidence, expected affected modules, and edge directions. Reviewer
identity/date, disagreements, adjudication, and final approval must be recorded
by real people.

Compare these policies on the same frozen cases:

1. full regeneration baseline: authorize every generated module;
2. defect-location-only baseline: authorize only the reported location; and
3. C3 graph-guided selection: current typed-path intersection policy.

Report selection precision/recall/F1 against the approved affected-module set,
selected scope size, collateral edit count, unchanged-file ratio, LLM calls,
latency, and review-required rate. Defect-resolution rate is reported only after
real C4 retesting. The template contains no scores or approvals.

## 5. Code-understanding map for panel defense

### 5.1 Input validation

- **Source/function:** `backend/src/intelise_c3/services/input_validation.py` —
  `InputValidationService.validate()` and `_normalize()`.
- **Input:** strict immutable `ProvisionalInputPackage`.
- **Algorithm:** check all three contract versions; project and SRS equality;
  approved C1 package/requirements; non-empty provenance/report refs; unique
  requirement/UML/anchor IDs; passed/validated C2 states; and known anchor
  endpoints. Then preserve identities in `GenerationContext`.
- **Output:** immutable versioned `GenerationContext`.
- **Failures:** Pydantic HTTP 422 for malformed shape; structured HTTP 409 for
  semantic/version/approval/reference conflicts.
- **Safe experiment:** in the Inputs UI validate the SIMULATED fixture, change
  one requirement to `DRAFT`, validate again, then restore it.
- **Likely question:** “Does a provenance string prove client approval?” No; it
  is an opaque preserved reference pending authoritative upstream verification.

### 5.2 Design understanding and stack selection

- **Sources/functions:** `services/design_understanding.py` —
  `DesignUnderstandingService.build()` / `_parse_class_diagram()`;
  `services/stack_selection.py` — `StackSelectionService.select()` /
  `_evaluate()`.
- **Inputs:** accepted `GenerationContext`; then `DesignContext` plus explicit
  technology criteria/evidence/confidence.
- **Algorithm:** parse only the documented PlantUML class subset without
  inventing members; preserve provenance; evaluate exactly four candidates;
  apply hard constraints; calculate each criterion as
  `raw_score * confidence * weight`; sum and round to six decimals; break ties
  in canonical order.
- **Outputs:** `DesignContext` diagnostics and a fully inspectable
  `StackSelectionReport` with selected/rejected candidates.
- **Failures:** missing/unsupported PlantUML, undefined classes, no compatible
  stack, and unimplemented selected generator at generation time.
- **Safe experiment:** use equal evidence and REST-SPA settings to show the
  deterministic tie order, then require Spring Boot and show no silent React +
  Node substitution.
- **Likely question:** “Are the weights scientifically validated?” No; they are
  approved only as provisional MVP research-policy assumptions.

### 5.3 Local Ollama generation

- **Sources/functions:** `llm/ollama.py` — `OllamaLLMClient.generate()`;
  `services/code_generation.py` — `CodeGenerationService.generate()`,
  `_parse_model_artifact()`, and `_validate_artifact_set()`.
- **Input:** versioned prompt request, local settings, consistent contexts,
  explicit provisional stack approval, and `LOCAL_LLM` mode.
- **Algorithm:** verify `/api/show` resolves to a local model; send structured,
  non-streaming `/api/chat`; validate response metadata and JSON; accept only
  the allowlisted TaskService path/content; combine with reviewed templates;
  hash and atomically publish a manifest.
- **Output:** 18-file workspace, one accepted `LOCAL_LLM` TaskService, run
  evidence, artifact/evidence digests, and status `NOT_EXECUTED`.
- **Failures:** non-loopback/cloud model config, unavailable/missing model,
  timeout, malformed/empty output, unsafe JavaScript/path, inconsistent
  contexts, unsupported stack, or workspace collision. There is no template
  fallback from failed local inference.
- **Safe experiment:** run the UI `LOCAL_LLM` generation after `ollama list`,
  then inspect model ID, prompt version, one file origin, and hashes without
  executing the workspace.
- **Likely question:** “Is the entire app AI-generated?” No; one constrained
  business-logic module is local-model generated and 17 files are templates.

### 5.4 Traceability graph construction

- **Sources/functions:** `traceability/verification.py` —
  `ManifestVerificationService.verify()`; `traceability/builder.py` —
  `TraceabilityGraphBuilder.build()` and `coverage()`.
- **Input:** a manifest plus its safe relative workspace path.
- **Algorithm:** verify evidence digest, stored-manifest equality, safe paths,
  every size/hash, and aggregate digest; create nodes from exact manifest
  identities; translate evidence links; validate relation direction/types;
  sort nodes/links; calculate coverage and canonical content digest.
- **Output:** deterministic `TraceGraphBuild`, later an immutable snapshot.
- **Failures:** tampering, unsafe/missing files, duplicate identities, absent
  endpoints, invalid resolved evidence, or invalid relation direction.
- **Safe experiment:** build a graph from a verified UI generation, inspect an
  evidence chip, then copy a workspace separately and alter one byte to show
  rejection without modifying the real run.
- **Likely question:** “Are links inferred from filenames?” No; builder input is
  typed manifest evidence and documented deterministic mapping rules.

### 5.5 Traceability version updates

- **Sources/functions:** `services/traceability.py` —
  `TraceabilityService.compare()`, `update()`, and `_prepare_update()`;
  `traceability/store.py` — `SQLiteTraceabilityStore.append()`.
- **Input:** latest graph/version, new verified manifest/workspace, optional
  explicitly approved source-transition evidence.
- **Algorithm:** verify new run; reject stale base; classify file IDs as
  added/removed/changed/unchanged; diff nodes and logical links; preserve
  unchanged links, revalidate links touching changed modules, retire stale
  nodes/links with history; append under `BEGIN IMMEDIATE` with version-race
  detection.
- **Output:** new immutable snapshot and `GraphChangeReport`.
- **Failures:** stale/concurrent version, project mismatch, unapproved source
  identity transition, manifest integrity failure, or SQLite error.
- **Safe experiment:** compare the known defective and repaired manifests and
  show one changed plus 17 unchanged files and a new graph version.
- **Likely question:** “Why keep old snapshots?” They provide reproducible
  lineage and prevent regeneration from silently rewriting prior evidence.

### 5.6 Defect impact selection

- **Sources/functions:** `traceability/impact.py` — `ImpactSelector.select()`,
  `_select_defect()`, `_requirement_paths()`, `_test_paths()`, `_api_paths()`.
- **Input:** verified manifest, verified matching graph, and a structured
  provisional defect report bound to exact run/digest/graph version.
- **Algorithm:** reject unknown/stale references; traverse only active resolved
  and not-review-required typed links; intersect requirement evidence with
  failing test/API paths, defect-category policy, patch allowlist, and optional
  location corroboration; cap automatic scope at two modules.
- **Output:** selected modules with evidence paths plus explicit exclusions, or
  `REVIEW_REQUIRED` with no automatic scope.
- **Failures:** stale graph/run/digest, unknown requirement/test/API, insufficient
  evidence, unsupported category, broad scope, or non-patchable candidate.
- **Safe experiment:** compare the single TaskService defect scenario with the
  “too broad” simulated scenario; the second must not patch anything.
- **Likely question:** “Can C4's file path authorize a patch?” No; location only
  corroborates a module already supported by resolved graph paths.

### 5.7 Scoped regeneration

- **Source/function:** `services/scoped_regeneration.py` —
  `ScopedRegenerationService.regenerate()`, `_patch_modules()`,
  `_materialize()`, and `_preservation()`.
- **Input:** verified source run/design/graph and selected defect scope; local
  Ollama or an explicitly labeled demo test double.
- **Algorithm:** verify source structure; prompt per authorized module; validate
  exact path and constrained patch behavior; use bounded attempts; create a new
  run; copy unselected bytes; verify new manifest; compare hashes; structurally
  verify; append graph update; emit pending C4 handoff.
- **Output:** patch records, new run/digests, preservation report, graph-version
  evidence, metrics, and C4 status `PENDING`.
- **Failures:** review-required impact, invalid source structure, model/output
  rejection, attempt exhaustion, collateral edit, structural failure, or graph
  update failure. Failed candidates are not published as successful runs.
- **Safe experiment:** use MOCK for a deterministic five-minute demo and use
  `REAL_LOCAL_OLLAMA` only on a fresh baseline, reporting rejection honestly.
- **Likely question:** “Who decides the defect is fixed?” Only independent C4
  retesting; C3 never self-approves repair success.

### 5.8 Artifact hash preservation

- **Sources/functions:** `generation/evidence.py` — `canonical_json_bytes()`,
  `compute_evidence_digest()`, `verify_manifest_evidence()`;
  `scoped_regeneration.py` — `_artifact_digest()` and `_preservation()`.
- **Input:** canonical context/prompt/model/version evidence and per-file bytes.
- **Algorithm:** canonical sorted-key compact UTF-8 JSON; bind run/context/prompt/
  model/artifact evidence while excluding the evidence digest itself; aggregate
  sorted path + NUL + SHA lines; recompute every unselected file hash.
- **Output:** input hashes, evidence digest, artifact digest, and per-file
  byte-identical report.
- **Failures:** any evidence-field, file-size/hash, manifest, or aggregate digest
  mismatch.
- **Safe experiment:** compare manifests before/after scoped repair and show the
  single changed path and 17 equal hashes.
- **Likely question:** “Does SHA-256 prove authenticity?” No; it detects changes
  against recorded evidence, but an attacker able to rewrite everything can
  recompute plain hashes. Trusted signing/issuers are future integration work.

### 5.9 Docker generated-app preview

- **Sources/functions:** `runtime-preview/verify_copy.py` — `main()`;
  `run-isolated-preview.ps1`; `entrypoint.sh`;
  `preview-backend-proxy.mjs`; `crud-smoke.ps1`.
- **Input:** safe workspace-relative path and a new execution ID.
- **Algorithm:** perform C3 manifest verification; copy only manifest-listed
  files to a never-overwritten execution folder; read-only mount; install and
  run inside a limited non-root container; publish loopback ports; perform HTTP
  CRUD smoke.
- **Output:** local UI/API plus ignored execution metadata/logs/smoke JSON.
- **Failures:** manifest/hash mismatch, unsafe/existing execution ID, missing
  Docker, build/dependency failure, port conflict, backend timeout, CORS/network
  failure, or CRUD mismatch.
- **Safe experiment:** follow `generated-app-preview.md` with a fresh execution
  ID, run API smoke, then browser create/update/delete. Never run generated npm
  or Node on Windows.
- **Likely question:** “Does Docker success authorize deployment?” No; it is an
  isolated runtime demonstration. Dependency audit, C4 retest, and deployment
  authorization remain separate gates.

## 6. LangGraph decision

**Recommendation: do not add LangGraph for PP1.** Current orchestration is a
small, deterministic sequence implemented by FastAPI services and immutable
Pydantic models. Graph snapshots refer to requirement traceability, not an
agent-execution framework. Adding LangGraph now would add a dependency and
migration/test surface without improving the measured novelty evidence or
resolving missing C1/C2/C4 contracts.

LangGraph could become useful in PP2 for a durable C3 <-> C4 loop with explicit
states such as receive verified feedback, select impact, request patch, validate,
submit to C4, await idempotent callback, retry/escalate, and terminate. Before
that, the team needs an approved C4 request/acknowledgment/retest contract,
correlation and idempotency keys, authentication, durable checkpoints, timeout
semantics, and recovery rules. The present custom services should remain the
domain operations even if a workflow engine later coordinates them.

## 7. Five-minute browser walkthrough

Use a fresh `TRACEABILITY_STORE_PATH` and `GENERATED_WORKSPACE_ROOT` as described
in `ui-research-demo.md`; never delete historical artifacts.

1. **0:00-0:30 Overview:** show FastAPI healthy, local Ollama status, and visible
   SIMULATED/NOT_INTEGRATED labels.
2. **0:30-1:05 Inputs:** validate the simulated package; make one requirement
   draft and show the real rejection; restore.
3. **1:05-1:40 Design/Stack:** parse UML, inspect four scored candidates,
   acknowledge provisional policy, approve React + Node.js.
4. **1:40-2:40 Generation:** select `LOCAL_LLM`; show run ID, model/prompt,
   one local-model file, 17 template files, digests, read-only preview, and
   structural report.
5. **2:40-3:20 Traceability:** build graph; show Requirement -> UML/Anchor ->
   Code/API/Database/Test evidence and unresolved links.
6. **3:20-4:35 Scoped repair:** create SIMULATED defective baseline; preview
   selected/excluded modules; run MOCK; show TaskService-only diff, 17 unchanged
   hashes, and graph version increment.
7. **4:35-5:00 Readiness:** show C4 retest `PENDING`, repair success not evaluated,
   and deployment `BLOCKED`.

For generated-app CRUD, start the Docker preview before the talk and open it in
a separate tab. Browser UI is the primary demo; Swagger/terminal is backup only.

## 8. Two-minute backup script

If Ollama is slow or the live generation fails, do not relabel a template run as
AI output. Use an already verified LOCAL_LLM workspace through the Research UI's
workspace loader and state that it is a previous local-model run.

1. **0:00-0:20:** Overview — real C3 API, real local-model status, simulated
   upstream labels.
2. **0:20-0:45:** open verified prior LOCAL_LLM manifest — show run/model/prompt,
   one LLM origin, 17 templates, hashes.
3. **0:45-1:10:** graph — show one typed chain and four unresolved links.
4. **1:10-1:40:** scoped-regeneration record — show selected TaskService,
   excluded modules, one-file diff, 17 unchanged hashes, new graph version.
5. **1:40-2:00:** readiness — C4 `PENDING`, deployment `BLOCKED`, real C1/C2
   handoff `BLOCKED_BY_UPSTREAM`.

## 9. High-priority actions before PP1

1. Obtain at least one frozen, owner-approved C1 or C2 handoff matching the
   exact fields listed above; otherwise present integration as blocked.
2. Rehearse local Ollama generation on the presentation machine without hiding
   model rejection or latency.
3. Start the Docker preview with a fresh execution ID and prove API plus browser
   CRUD in the current session.
4. Rehearse the graph and scoped-repair evidence using a fresh isolated graph DB
   and workspace root.
5. Have a human independently review at least a small evaluation subset before
   presenting precision/recall/F1 as research measurements.
6. Keep C4 retest pending and deployment blocked until genuine C4 evidence and
   authorization exist.

## 10. Fresh Task 11 verification evidence

These results were produced during this audit, not copied from an earlier
summary:

- backend: 344 passed, 3 optional real-model tests skipped, one upstream
  Starlette deprecation warning;
- frontend: 35 passed; production build succeeded with 49 transformed modules;
- real local generation: run `2f1c1270-ea92-4664-8cbe-7c40b086dc51`,
  `qwen2.5-coder:3b`, prompt `react-node-task-service-v4`, 20,362.245 ms client
  latency, 18 files (one `LOCAL_LLM`, 17 `TEMPLATE`), execution status
  `NOT_EXECUTED`;
- fresh manifest/evidence/file verification passed and a 36-node/99-link graph
  v1 was saved in an isolated ignored store;
- structural verification had eight deterministic `PASS` findings and one
  expected `REVIEW_REQUIRED` limitation finding; there were no `FAIL` findings;
- MOCK and real local-Ollama scoped-regeneration experiments each selected only
  TaskService, preserved 17 unselected files byte-for-byte, produced graph v2,
  and left C4 retest `PENDING` and repair success `NOT_EVALUATED`;
- Docker preview manifest verification passed; HTTP CRUD checks passed list,
  create, list-after-create, update, delete, and missing-item 404; UI document
  returned HTTP 200; CORS preflight returned 204 with the exact local origin;
- the Research UI document and its real FastAPI health proxy returned HTTP 200
  on alternate port 5174. Port 5173 was occupied by an unrelated container and
  was not changed by this audit; and
- actual browser interaction is `NOT_VERIFIED` in Task 11 because both available
  browser-control entry points failed to initialize with `failed to write kernel
  assets: path not found`. HTTP/CORS success must not be relabeled as a browser
  observation.

The first sandboxed backend/frontend attempts encountered environment-only
ACL/spawn errors. The recorded pass counts above are the subsequent complete
runs outside that managed sandbox, using the same working tree.
