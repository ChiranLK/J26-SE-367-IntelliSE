# InteliSE Component 3

Component 3 is the Intelligent Development and Deployment Assistant for
traceable software generation. The service currently provides its FastAPI
foundation, deterministic validation of provisional C1/C2 input packages,
limited-subset design understanding, evidence-based stack selection, and a
reusable local-only Ollama inference client. Task 6 adds a React + Node.js Task
Management generation MVP using deterministic scaffolding and one locally
model-generated business-logic module. Dynamic CRUD Stage 1 adds a deterministic
multi-entity generator while preserving that legacy Task path. Task 7 adds
persistent, versioned living requirement traceability over verified manifests.

General-purpose/non-CRUD generation, dynamic scoped regeneration, deployment,
and real integrations with Components 1, 2, and 4 remain future work.

## Requirements

- Windows PowerShell
- Python 3.11 or Python 3.12
- Ollama installed locally on Windows
- The local `qwen2.5-coder:3b` model for the default smoke workflow

Component 3 has no cloud LLM fallback. It accepts only an HTTP loopback Ollama
URL and rejects documented Ollama cloud-model identifiers ending in `:cloud`
or `-cloud`. The API health endpoint does not contact Ollama.

## Set up the development environment

Run these commands from the repository root:

```powershell
Set-Location .\component-3
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

If Python 3.12 is unavailable but Python 3.11 is installed, replace `-3.12`
with `-3.11`.

## Run the tests

With the virtual environment active and from `component-3/`:

```powershell
python -m pytest
```

## Start FastAPI

With the virtual environment active and from `component-3/`:

```powershell
python -m uvicorn intelise_c3.main:app --host 127.0.0.1 --port 8000 --reload
```

The service endpoints are then available at:

- Health: <http://127.0.0.1:8000/api/v1/health>
- Swagger UI: <http://127.0.0.1:8000/docs>

The health endpoint reports only the API process state. It does not contact
Ollama or claim that local inference is ready.

## Test provisional C1/C2 validation

The endpoint is available in Swagger UI under `input-validation`:

```text
POST /api/v1/validate-input
```

From another PowerShell session, submit the explicitly simulated valid fixture:

```powershell
Set-Location .\component-3
$body = Get-Content -Raw .\tests\fixtures\simulated\valid_input_package.json
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/validate-input `
  -ContentType application/json `
  -Body $body
```

The C1/C2 schemas are provisional assumptions documented in
`contracts/README.md`. Reference fields are retained as opaque provenance;
their presence does not prove authentic client approval or upstream
validation.

## Understand design and select a stack

The versioned FR-C3-02 endpoints are:

```text
POST /api/v1/design-context
POST /api/v1/stack-selection
```

Use Swagger UI to pass the accepted `GenerationContext` to the first endpoint,
then include its `DesignContext` response with reviewed selection criteria in
the second endpoint. The full parsing subset, scoring formula, policy weights,
uncertainties, generator availability, and manual approval points are recorded
in `docs/design-understanding-and-stack-selection.md`.

Stack selection evaluates exactly React/Angular x Node.js/Spring Boot. The
narrow React + Node.js Task Management generator now reports `IMPLEMENTED`.
Angular + Node.js, React + Spring Boot, and Angular + Spring Boot remain
`NOT_IMPLEMENTED`; unavailable selections are never silently substituted.

## Generate the Task Management MVP

Task 6 accepts matching validated/design/selection contexts plus an explicit
provisional stack approval. That approval is a caller assertion, not
cryptographic proof of real C1/C2 or client authorization.

Run the fixed simulated-input experiment from `component-3/`:

```powershell
# Use the real configured local Ollama model for the service module
python -m intelise_c3.scripts.generate_task_mvp --mode local-llm

# Or use the explicitly labeled deterministic development mode
python -m intelise_c3.scripts.generate_task_mvp --mode template-only
```

Outputs are written under
`generated-workspaces/task-management-manual/<generation-run-id>/`. The
command prints the exact workspace and manifest paths. It writes source only;
it never installs dependencies or executes, tests, starts, or deploys the
generated application.

Manifest version 2 records canonical run-evidence hashes and precise typed
traceability links instead of assigning every source identity to every file.
Unjustified UI and runtime-database mappings are explicitly marked
`UNRESOLVED` / `REVIEW_REQUIRED`. The generated runtime repository remains
`IN_MEMORY`; `schema.sql` is design-only. SHA-256 integrity checks detect
changes but do not authenticate upstream evidence or stop an attacker from
recomputing hashes.

The existing FastAPI application also exposes:

```text
POST /api/v1/generation-runs
```

Its body requires a `GenerationContext`, `DesignContext`,
`StackSelectionReport`, provisional approval, mode, and safe workspace name.
See `docs/local-llm-code-generation-mvp.md` for the trust boundary, manifest,
template/model split, output controls, inspection commands, and limitations.

## Generate supported dynamic CRUD applications

The same `POST /api/v1/generation-runs` pipeline can deterministically render
one or more independent CRUD entities from an accepted `DesignContext` in
`TEMPLATE_ONLY` mode. Student, Library, and Inventory simulated fixtures test
one shared rules-based renderer; they are not separate hardcoded applications.
Unsupported relationships, types, incomplete CRUD evidence, and ambiguous
requirement mappings fail explicitly.

Dynamic `LOCAL_LLM` generation is not implemented in Stage 1 and is rejected
without fallback. The historical Task flow retains its existing local-Ollama
behavior. See `docs/dynamic-crud-generation-stage1.md` for the supported
intermediate specification, upstream contract gaps, traceability policy, and
runtime limitations.

## Build and inspect living traceability

Task 7 verifies a Task 6 manifest and every referenced generated file before
building typed Requirement → UML/Anchor → Code/API/Database/Test/UI evidence.
Snapshots are append-only in local SQLite, retain retired link history, and
produce coverage and change reports. Uncertain evidence remains
`REVIEW_REQUIRED`; no filename-similarity inference is used.

The endpoints are grouped under:

```text
/api/v1/traceability/graphs
```

Swagger documents graph creation, latest/version retrieval, comparison,
update, and researcher-ground-truth evaluation operations. See
`docs/living-requirement-traceability.md` for the precise data model,
algorithm, coverage policy, trust boundary, and decisions requiring manual
research approval.

## Defect-feedback-driven scoped regeneration

Task 9 turns a structured defect report into a minimal, justified patch scope
over the verified traceability graph, patches only the selected modules with
the local model, proves every other file is byte-identical, and publishes a new
immutable run and graph version. It returns a Component 4 retest handoff that
is always `PENDING`; Component 3 never claims a defect is fixed or that C4
testing occurred. Defect reports are currently **SIMULATED** fixtures.

Every defect report must carry a strict positive-integer `source_graph_version`
that equals the exact graph snapshot used for impact selection (missing, null,
invalid, or stale versions are rejected). The stored graph is verified against a
rebuild from the verified manifest, comparing every ACTIVE node and link (ID,
endpoints, relation, resolution, review status, lifecycle, provenance, file
hashes), not only identifier sets. Local-model patches pass a conservative
JavaScript **lexical** policy (network and dynamic-code APIs, `globalThis`,
constructor and prototype access, timers, escape-obfuscated identifiers);
syntax that cannot be inspected is escalated to `REVIEW_REQUIRED`. That policy
is not a sandbox and not a proof of safety.

```text
POST /api/v1/impact-selections        # read-only, no model call
POST /api/v1/scoped-regenerations     # patches only an authorized, verified scope
```

```powershell
python -m intelise_c3.scripts.scoped_regeneration_experiment --model mock
python -m intelise_c3.scripts.scoped_regeneration_experiment --model ollama
```

See `docs/defect-feedback-scoped-regeneration.md` for the algorithm, worked
example, metric status, and limitations.

## Research demo dashboard (UI)

A React dashboard in `dashboard/` demonstrates the whole C3 workflow through a
browser UI backed by the real FastAPI services (C1/C2 inputs and C4 defects are
clearly labeled **SIMULATED**; C4 retest stays `PENDING` and deployment stays
`BLOCKED`). With FastAPI running on port 8000:

```powershell
Set-Location .\component-3\dashboard
npm install
npm run dev     # then open http://127.0.0.1:5173
```

See `docs/ui-research-demo.md` for the three-process Windows start-up, the
five-minute walkthrough, helper endpoints, and limitations.

## Best-practice RAG

Generation supports an offline deterministic `filter` backend and an optional
real embedding-backed `chroma` backend. The default remains `filter`; Chroma and
sentence-transformers are installed separately so ordinary C3 setup does not
silently download an embedding model.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-rag.txt
$env:RAG_BACKEND = "chroma"
.\.venv\Scripts\python.exe scripts\rag_demo.py
```

See [docs/rag-best-practice-retrieval.md](docs/rag-best-practice-retrieval.md)
for the evidence fields, real-model demo, ablation procedure, and research
limitations. This is best-practice RAG for generation; it is not yet Component
4 defect-context RAG.

## Configuration

The defaults are safe for a locally running Ollama instance:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_TEMPERATURE=0.0
OLLAMA_NUM_CTX=4096
GENERATED_WORKSPACE_ROOT=generated-workspaces
TRACEABILITY_STORE_PATH=runtime/traceability/traceability.sqlite3
```

Copy `.env.example` to `.env` for local overrides. Never commit `.env` or
credentials. No generated application is executed automatically by this
service.

`OLLAMA_BASE_URL` must use `http` with `localhost`, `127.0.0.1`, or `::1`.
Remote hosts, URL credentials, path-scoped URLs, and direct cloud endpoints are
rejected. `OLLAMA_TEMPERATURE` must be between `0.0` and `2.0`; the timeout must
be positive and no more than 600 seconds; and `OLLAMA_NUM_CTX` must be between
512 and 131072. The defaults are MVP configuration choices and should be
reviewed for later experiments and larger models.

## Start and verify Ollama on Windows

First check the installed application and locally available models:

```powershell
ollama --version
ollama list
```

The Ollama Windows application normally starts its local service. If it is not
running, start it in a separate PowerShell window:

```powershell
ollama serve
```

Verify the local API without sending a prompt:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:11434/api/tags
```

The configured model must appear in the local model list. If the approved
local model is absent, install it manually with:

```powershell
ollama pull qwen2.5-coder:3b
```

Do not select an Ollama cloud model. Official Ollama API documentation is at
<https://docs.ollama.com/api>.

## Run the manual local-inference smoke test

The smoke workflow is a command-line module with a fixed harmless prompt. It
does not expose unrestricted prompting through FastAPI and does not execute
the returned text:

```powershell
Set-Location .\component-3
.\.venv\Scripts\Activate.ps1
python -m intelise_c3.scripts.ollama_smoke_test
```

It reports the configured/returned model identifiers, prompt-template version,
client latency, and response. It does not log credentials, SRS content, or full
request payloads.

The real-service pytest is opt-in and is skipped during an ordinary test run:

```powershell
$env:RUN_OLLAMA_INTEGRATION = "1"
python -m pytest .\tests\test_ollama_integration.py -m integration -v
Remove-Item Env:RUN_OLLAMA_INTEGRATION
```

All other Ollama tests use mocked HTTP responses and do not require the service
or model to be running.

## Ollama troubleshooting

- `OLLAMA_SERVICE_UNAVAILABLE`: start the local Ollama application or
  `ollama serve`, then verify `/api/tags` on the configured loopback port.
- `OLLAMA_MODEL_NOT_INSTALLED`: compare `OLLAMA_MODEL` with `ollama list` and
  install the explicitly approved local model if needed.
- `OLLAMA_REQUEST_TIMEOUT`: confirm the model is loading and, after review,
  increase `OLLAMA_TIMEOUT_SECONDS` within the allowed range.
- `OLLAMA_UNEXPECTED_HTTP_RESPONSE`: verify the Ollama version, endpoint, and
  local service logs. Raw upstream error bodies are not exposed by the client.
- `OLLAMA_INVALID_RESPONSE`: the service returned missing, malformed, or empty
  chat output; retry only after checking the local Ollama process and model.
- Settings validation failure: use a loopback HTTP endpoint and a non-cloud
  model identifier. Component 3 intentionally refuses remote inference.

## Current generation and local-inference limitations

- React + Node.js generation supports the historical Task MVP and a narrow,
  deterministic, independent-entity CRUD profile. Angular, Spring Boot,
  relational/nested domains, and non-CRUD workflows are not implemented.
- Deterministic templates create the scaffold; only
  `backend/src/services/taskService.js` is produced by Ollama in `LOCAL_LLM`
  mode.
- Model output is treated as untrusted, structurally constrained source and is
  never executed automatically.
- Dynamic CRUD outputs can be built, dependency-audited, backend-tested, and
  HTTP-smoke-tested with the tracked restricted Docker harness. Ordinary
  Python tests do not require Docker. See
  `docs/dynamic-crud-docker-validation.md` for commands, controls, and the
  precise claim boundary. Historical local-LLM Task output is outside this
  dynamic harness and is not automatically executed.
- Local endpoint validation, cloud-tag rejection, and remote-model metadata
  checks are MVP controls, not a complete host-level network sandbox. Ollama
  should also be configured in local-only mode by the operator.
- The client records evidence for reproducibility but does not claim that
  stochastic output is perfectly reproducible.
- The LLM cannot validate C1/C2 approval authenticity, authorize deployment, or
  provide Component 4's XAI defect explanations.
- Living traceability is implemented for verified Task 6 manifests using a
  local SQLite MVP store; dynamic manifests can be converted to graphs, but
  Stage 1 does not run or persist a new research snapshot automatically.
- Defect-feedback-driven scoped regeneration is implemented for simulated
  defect reports, the service/controller/repository allowlist, and at most two
  modules. Repair success, XAI, and semantic preservation are not evaluated by
  Component 3 and remain pending independent Component 4 retesting.
- Deterministic design-to-code structural verification is available at
  `POST /api/v1/structural-verifications`. It verifies manifest/file integrity,
  binds the supplied DesignContext to the generation evidence, and checks the
  supported React/Node Task module, API, layering, repository, UI-client, and
  SQL structures without executing generated code. See
  `docs/design-to-code-structural-verification.md` for rules and limitations.
  Its current rule set and the scoped-regeneration patch policy remain
  Task-specific and explicitly reject dynamic generator manifests rather than
  applying unsafe Task assumptions.
