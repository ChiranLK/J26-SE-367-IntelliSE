# FR-C3-03/04 Local-LLM Code Generation MVP

This document describes the narrow Task 6 research prototype. It is not a
claim that arbitrary applications or all evaluated stacks can be generated.
The only working generator combination is React + Node.js, and its only
supported domain fixture is the explicitly simulated Task Management package.

## Authorization and trust boundary

Generation accepts an immutable `GenerationContext`, `DesignContext`, and
`StackSelectionReport`. Before writing anything, Component 3 checks that their
project, SRS, UML, context, requirement, anchor, UI-artifact, contract-version,
and upstream-provenance identities agree. Every requirement must retain a C2
anchor to a known UML artifact. The selected candidate must be eligible React +
Node.js and report an implemented generator.

The caller must also provide `ProvisionalStackApproval` with status
`APPROVED_FOR_MVP_GENERATION` and acknowledge the provisional research policy.
This is a workflow gate, not proof of identity or authority. Component 3 does
not authenticate the named approver, cryptographically verify C1/C2 releases,
or prove genuine client approval. Real integration needs trusted issuers,
signed or otherwise verifiable artifact identities, access control, and
durable storage.

The simulated fixture and manual script use conspicuous `SIMULATED-*`
references. They must never be presented as real C1, C2, client, or researcher
approvals.

## Supported and unavailable generators

| Selected stack | Generator status |
| --- | --- |
| React + Node.js | `IMPLEMENTED` for this narrow Task Management MVP |
| Angular + Node.js | `NOT_IMPLEMENTED` |
| React + Spring Boot | `NOT_IMPLEMENTED` |
| Angular + Spring Boot | `NOT_IMPLEMENTED` |

An unsupported selected stack fails explicitly. Component 3 never replaces it
with React + Node.js.

The MVP additionally requires an explicit task-related requirement, a parsed
`Task` class, at least one structured UI/wireframe reference, and complete
requirement-to-UML anchors. This protects the prototype from claiming general
domain generation.

## Generation modes and file origins

- `LOCAL_LLM` sends one versioned, grounded prompt to the configured local
  Ollama client. Ollama may return only
  `backend/src/services/taskService.js`. If inference or output validation
  fails, the request fails and no template fallback occurs.
- `TEMPLATE_ONLY` is an explicit development mode. It makes no LLM call and
  uses the deterministic task-service template.

In both modes, all other files are deterministic templates:

```text
README.md
api/openapi.yaml
frontend/
  package.json
  vite.config.js
  index.html
  src/main.jsx
  src/App.jsx
  src/api/tasks.js
  src/components/TaskForm.jsx
  src/components/TaskList.jsx
backend/
  package.json
  src/app.js
  src/routes/taskRoutes.js
  src/controllers/taskController.js
  src/repositories/taskRepository.js
  src/db/schema.sql
  src/services/taskService.js       # local LLM or explicit template mode
  tests/taskService.test.js
artifact-manifest.json
```

Each file's manifest record labels its origin as `TEMPLATE` or `LOCAL_LLM`.
The repository is injected into the service, providing the mockable boundary
required by FR-C3-04. The included service test demonstrates that seam but is
not executed automatically. The coherent MVP `Task` model has exactly three
fields: UUID-formatted string `id`, non-empty string `title`, and boolean
`completed`. The service, controllers, frontend client, OpenAPI schemas, and
SQL design script use this same model.

The generated repository remains explicitly `IN_MEMORY`. The SQL file is a
`SCRIPT_ONLY` design artifact and is not connected to runtime persistence. A
manifest `PERSISTS_TO` link between that repository and SQL table is therefore
`UNRESOLVED` / `REVIEW_REQUIRED`, not a claim that database persistence works.

## Prompt and local-model configuration

The model prompt is versioned as `react-node-task-service-v4`. It contains the
preserved project, SRS, UML, requirement, class, and anchor data from the
accepted design context. Values are serialized as grounding data, not treated
as instructions. The prompt requires a JSON object with exactly `path` and
`content`; its schema fixes the path to the allowlisted service module.

The Ollama request uses the configured local values:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_TEMPERATURE=0.0
OLLAMA_NUM_CTX=4096
GENERATED_WORKSPACE_ROOT=generated-workspaces
```

Only an HTTP loopback Ollama endpoint and a non-cloud model are accepted. There
is no cloud fallback. The model output is untrusted even when its JSON shape is
valid.

## Output controls

The workspace setting must resolve to a child of `component-3/`. Every run is
written beneath:

```text
component-3/generated-workspaces/<workspace-name>/<generation-run-id>/
```

The implementation rejects absolute paths, Windows separators, drive-qualified
paths, traversal, paths outside the allowlist, case-insensitive duplicates,
workspace-root symlinks, and detected symlink traversal. The final success
manifest is first written with a `.pending` name and atomically renamed only
after all artifacts are written; a failed write cannot publish a final
`artifact-manifest.json` success record. Model content is
limited in size and rejects direct filesystem, process, child-process, eval,
dynamic-import, environment access, `Math.random`, and unrestricted object
merge constructs. The service output validator additionally requires UUID
generation, input-type checks, exact repository signatures, restricted update
fields, and consistent 400/404 error metadata. These checks reduce risk;
they are not a complete JavaScript security analysis or sandbox.

The deterministic scaffold restricts CORS to one explicit origin configured
with generated-app `CORS_ALLOWED_ORIGIN` (default
`http://127.0.0.1:5173`), limits JSON request size, validates create/update
payload types, uses `globalThis.crypto.randomUUID()`, and returns structured
400/404 errors. Direct package versions are exact rather than ranges. No npm
install or dependency audit was performed by Component 3.

Component 3 writes source and metadata only. It does not run `npm install`,
build, test, start, or deploy the generated application.

## Artifact manifest

`artifact-manifest.json` uses manifest version `2.0` and records:

- generation run ID, timestamp, mode, and `NOT_EXECUTED` status;
- source project, SRS, UML, generation-context, and design-context versions;
- provisional C1/C2 contract versions and opaque validation/provenance refs;
- preserved requirement IDs, UML IDs, design-anchor mappings, and UI refs;
- selected stack and caller-asserted provisional approval evidence;
- file/module identities, artifact types, origins, sizes, and SHA-256 hashes;
- per-file requirement/UML/anchor/UI identities plus API operations, database
  table/column identities, and the injected repository test seam;
- typed `DERIVED_FROM`, `IMPLEMENTS`, `EXPOSES`, `DEFINES`, `PERSISTS_TO`, and
  `VERIFIED_BY` links with mapping rule, evidence refs, resolution status, and
  review status;
- local model, prompt version, generation parameters, latency, and available
  Ollama response metadata for `LOCAL_LLM` mode; and
- a deterministic overall digest over sorted file paths and file hashes; and
- canonical source-input/prompt hashes plus one evidence digest binding the run
  ID, source hashes, exact prompt request/version, generator/template versions,
  local model configuration, and artifact digest.

### Canonical evidence serialization

`C3_CANONICAL_JSON_V1` converts Pydantic values to JSON-mode data, encodes
objects with lexicographically sorted keys and no insignificant whitespace,
preserves array order, emits Unicode directly, and hashes the UTF-8 bytes with
SHA-256. It is a project convention, not RFC 8785. The evidence digest payload
does not include `evidence_digest_sha256` itself. Verification recomputes that
digest and detects accidental or uncoordinated changes to a bound field.

A plain unkeyed hash does **not** authenticate an issuer, prove approval,
prevent a malicious actor from modifying evidence and recomputing all hashes,
or replace signed provenance and protected storage. Those controls require a
later integration design.

### Provisional traceability mapping rules

The Task MVP maps requirements only when their titles satisfy one narrow,
deterministic rule: `create` plus `list`, `update` plus `delete`, or
`repository`. Template metadata then identifies which files implement those
capabilities. Parsed class names and retained C2 anchors justify UML links;
reviewed static template metadata identifies exact API operations, SQL
entities, and the repository seam. A requirement that does not match is not
copied to every file: it receives an `UNRESOLVED` / `REVIEW_REQUIRED` link.

UI input currently contains only an opaque artifact reference, not an
authoritative UI-to-file mapping. UI-related file links retain that reference
but are deliberately `UNRESOLVED` / `REVIEW_REQUIRED`. These structures prepare
evidence for a later Living Traceability Agent; they do not implement a living
graph, graph persistence, or regeneration update algorithm.

Task 6 does not create or persist the Living Traceability Graph.

## Run a fixed manual experiment

From `component-3/`, with the virtual environment active and local Ollama
running:

```powershell
python -m intelise_c3.scripts.generate_task_mvp --mode local-llm
```

The script validates the simulated fixture, builds its design context, selects
React + Node.js using simulated evidence, attaches an explicit simulated
provisional approval, and invokes local Ollama. It is fixed-input by design;
it is not an unrestricted prompt endpoint.

To inspect the deterministic development mode without contacting Ollama:

```powershell
python -m intelise_c3.scripts.generate_task_mvp --mode template-only
```

The command prints the workspace, manifest, business-logic origin, and digest.
Inspect without executing:

```powershell
$run = Get-ChildItem .\generated-workspaces\task-management-manual -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
Get-Content "$($run.FullName)\artifact-manifest.json"
Get-Content "$($run.FullName)\backend\src\services\taskService.js"
Get-ChildItem $run.FullName -Recurse -File | Select-Object FullName
```

If dependency validation is separately approved, copy the generated project
to a disposable restricted VM/container with network allowlisting and no host
credentials, then inspect before running:

```powershell
npm install --package-lock-only --ignore-scripts
npm audit
npm ci --ignore-scripts
npm test
```

These are instructions only. This milestone did not execute them and claims no
dependency-audit result.

The opt-in pytest experiment uses the real configured model and a temporary
workspace:

```powershell
$env:RUN_OLLAMA_GENERATION_INTEGRATION = "1"
python -m pytest .\backend\tests\test_generation_integration.py -m integration -v
Remove-Item Env:RUN_OLLAMA_GENERATION_INTEGRATION
```

Ordinary pytest runs use mocked Ollama responses and skip this experiment.

## API demonstration

The existing FastAPI application exposes:

```text
POST /api/v1/generation-runs
```

Use Swagger UI at <http://127.0.0.1:8000/docs>. The request must contain the
three matching contexts/reports, explicit provisional approval, generation
mode, and a safe workspace name. Avoid using confidential SRS content in this
research prototype because authentication, authorization, and protected
durable storage are not yet implemented.

## Manual review checklist

- [ ] Confirm the simulated C1/C2 contract assumptions with their owners.
- [ ] Verify every project/SRS/UML/context version and source identity.
- [ ] Verify every requirement-to-UML anchor and structured UI reference.
- [ ] Review and record the provisional stack-policy decision and approver.
- [ ] Inspect every generated file and its manifest origin before any use.
- [ ] Recompute or independently verify file hashes and the artifact digest.
- [ ] Recompute the canonical evidence digest and remember that it is not an
  authenticity proof.
- [ ] Review every `UNRESOLVED` / `REVIEW_REQUIRED` trace link.
- [ ] Confirm the narrow requirement-title mapping rules are acceptable for the
  research experiment.
- [ ] Review model-generated JavaScript for correctness and security.
- [ ] If execution is required later, use an explicitly approved restricted
  environment and record actual install/build/test results.

## Limitations and remaining work

- Only the simulated Task Management shape and React + Node.js are supported.
- Only one business-logic module is model-generated; scaffolding is templated.
- Output validation is structural and denylist-based, not a proof of safety or
  semantic conformance.
- Serializing requirement/design values as grounding data and constraining the
  response schema reduce prompt-injection risk but do not eliminate it.
- Direct template dependencies are pinned, but generated lockfiles do not
  exist and dependencies have not been installed, audited, or
  compatibility-tested by Component 3.
- Generated frontend/backend code is not built, tested, or executed here.
- The in-memory repository does not use the supplied SQL schema at runtime.
- The API has no production authentication, authorization, rate limiting,
  run registry, cleanup policy, signature/key management, or cleanup/recovery
  for partial directories after a failed write. Only final manifest publication
  is atomic.
- Upstream references and caller approval assertions are not authenticated.
- Generator-quality experiments, baselines, and evaluation metrics are future
  research work; no experimental results are fabricated here.
- Living traceability, scoped regeneration, deployment authorization, and
  Component 4 XAI/readiness integration are outside Task 6.
