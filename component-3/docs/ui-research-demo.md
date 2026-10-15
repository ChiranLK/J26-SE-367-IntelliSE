# Component 3 Research UI

This React application is the **graphical interface for demonstrating Component 3 (C3)**.
It is not the web application that C3 generates. Every action calls the real C3
FastAPI services; Swagger and the terminal are not needed during the demo.

The demo UI lives in `component-3/frontend/` and only talks to
`http://127.0.0.1:8000/api/v1` through the Vite dev proxy. It never executes,
installs, or builds generated code. The generated files are shown as escaped text.

## What is real and what is simulated

| Item | Status in this demo |
| --- | --- |
| C3 FastAPI services (validation, design, stack, generation, structural check, graph, impact selection, scoped regeneration) | **Real**, called from the browser |
| Local Ollama model name and reachability | **Real** probe (`GET /api/tags`) |
| `TEMPLATE_ONLY` generation | Real deterministic C3 templates |
| `LOCAL_LLM` generation and `REAL_LOCAL_OLLAMA` repair | Real local model call; quality is not guaranteed |
| C1 requirements and C2 UML/UI package | **SIMULATED** fixture. C1/C2 are not integrated |
| C4 defect reports | **SIMULATED** fixtures. C4 is not integrated |
| Baseline for the repair demo | **SIMULATED**: a real run and graph whose service file is a deliberately defective *test-double* output |
| `MOCK` repair | The real regeneration pipeline with a fixed repaired file instead of a model. Pipeline check only |
| C4 retest, XAI, semantic-preservation evidence | **None exists.** Always `PENDING` or `NOT_INTEGRATED` |
| Deployment | **Not implemented.** Always `BLOCKED` |

Simulated data is labeled in the interface (orange dashed badges).

## Start the three processes (Windows PowerShell)

Open three terminals. Run the first commands from the repository root.

### A. Ollama

```powershell
ollama list
# If the service is not running (Ollama normally runs in the tray):
ollama serve
# If the model is missing:
ollama pull qwen2.5-coder:3b
```

The Overview page shows whether Ollama is reachable and whether the configured
model is installed. Only the `LOCAL_LLM` and `REAL_LOCAL_OLLAMA` steps need it.

### B. FastAPI

Use a new, separate graph store and workspace root for every presentation run.
Both paths stay inside `component-3/` and are git-ignored. The timestamp avoids
deleting or reusing historical research artifacts.

```powershell
Set-Location .\component-3
.\.venv\Scripts\Activate.ps1
$demoRun = Get-Date -Format "yyyyMMdd-HHmmss"
$env:TRACEABILITY_STORE_PATH = "runtime/traceability/demo-$demoRun.sqlite3"
$env:GENERATED_WORKSPACE_ROOT = "generated-workspaces/demo-$demoRun"
python -m uvicorn intelise_c3.main:app --host 127.0.0.1 --port 8000
```

Keep the same two environment values for that FastAPI process. For another clean
run, start FastAPI with a new `$demoRun`; do not delete or overwrite prior runs.

### C. Component 3 Research UI

Node.js 20 or newer is required.

```powershell
Set-Location .\component-3\frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The port is fixed; if it is taken Vite exits
instead of choosing another one. Use `C3_FRONTEND_API_TARGET` if FastAPI runs
elsewhere:

```powershell
$env:C3_FRONTEND_API_TARGET = "http://127.0.0.1:8000"
```

Frontend checks:

```powershell
npm test        # Vitest, mocked HTTP boundary only
npm run build   # production build to frontend/dist (git-ignored)
```

## Five-minute supervisor walkthrough

Use `LOCAL_LLM` for code generation and `MOCK` for scoped regeneration. This
demonstrates the required local Ollama integration while keeping the repair path
deterministic. Warm up Ollama before the presentation. Local inference time and
output are not scientifically deterministic; if the model output is rejected,
show the real rejection and do not substitute `TEMPLATE_ONLY` as if it were an
LLM result. The five-minute target assumes the installed 3B model responds within
about one minute on the presentation machine.

1. **Overview (30 s).** Point at API health, the local model name, and the
   SIMULATED / NOT INTEGRATED rows. Say: C1, C2, and C4 are not integrated.
2. **C1/C2 Inputs (40 s).** Load the simulated fixture and run validation
   (accepted). Click *Make a requirement DRAFT* and validate again to show the
   backend's real error codes; click *Restore fixture*.
3. **Design & Stack (40 s).** Build the design context, run stack selection, show
   all four candidates and scores, tick the acknowledgement and approve. Say:
   scores and weights are provisional research-policy assumptions.
4. **Code Generation (70 s).** Select `LOCAL_LLM` and generate through local
   Ollama. Show the model ID, prompt/evidence metadata, run ID, artifact digest,
   the single accepted `LOCAL_LLM` origin, remaining `TEMPLATE` origins,
   `NOT EXECUTED`, and the read-only preview. Run structural verification
   (static inspection only).
5. **Living Traceability (50 s).** Build the graph. Show node and link counts,
   coverage, and the requirement chain matrix. Click a chip to show link
   evidence (mapping rule, evidence refs). Show unresolved links if any exist.
6. **Scoped Regeneration (80 s).** Load the SIMULATED defect fixture, create the
   baseline, preview impact selection (selected vs excluded modules and reason
   codes), run **MOCK**. Show old/new artifact digests, graph `vN` to `vN+1`,
   unchanged-file preservation, and C4 handoff `PENDING`. Open the before/after
   preview. Say: repair success is NOT EVALUATED until C4 retests.
7. **Readiness (20 s).** Show C4 retest pending and deployment blocked with the
   listed blockers.

Optional extras: choose the *too broad* scenario to show `REVIEW_REQUIRED` with
nothing patched; run `REAL_LOCAL_OLLAMA` on a fresh baseline and report whatever
status it returns, including rejection.

## Interface behavior to know

- Loading shows elapsed time; calls are synchronous, so no incremental progress
  is available. Long calls survive page navigation inside the app, but not a
  browser reload.
- HTTP 409 and 422 responses are shown as amber review/gate panels with the
  backend's error codes. Network and timeout failures are shown in red. No
  failure is replaced by demo data.
- The session (real responses only) is kept in `sessionStorage`. Reloading returns
  to Overview while preserving completed workflow results. *Reset session* clears
  validation, design, approval, generation, graph, and regeneration state; it
  does not delete backend workspaces or graph snapshots. A very large session may
  exceed the browser storage quota; the app then keeps the session in memory only.
- A repaired baseline cannot be repaired again, because its graph version has
  advanced. Create a fresh baseline to try the other mode.

## Helper endpoints added for the Component 3 Research UI (read-only except baseline)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/demo/overview` | Service status, real Ollama probe, integration labels |
| `GET /api/v1/demo/fixtures/{id}` | SIMULATED fixtures (`input-package`, `defect-scenarios`, `stack-criteria`) |
| `POST /api/v1/demo/code-preview` | Verified display-only file text (manifest and hashes checked first, 120 KB cap) |
| `POST /api/v1/demo/workspace-run` | Read the stored manifest of a workspace after hash verification, so patched files can be previewed |
| `POST /api/v1/demo/scoped-regeneration/baseline` | Create the SIMULATED defective baseline run and graph (writes a workspace and a graph version) |
| `POST /api/v1/demo/scoped-regenerations/mock` | Real regeneration service with a deterministic test-double model |

Everything else uses the existing C3 endpoints unchanged.

## Not demonstrable yet

- **Component 4 integration:** no defect reports, retest, XAI, or semantic-preservation results.
- **Deployment:** not implemented in C3.
- **Graph update, compare, and ground-truth evaluate endpoints** (`/traceability/graphs/{id}/updates`, `/compare`, `/versions/{n}/evaluate`): exist in the API but are not surfaced in the research UI.
- **Generation of non-React stacks:** other candidates are scored but have no generator.
- **Real C1/C2 handoff:** only simulated packages.

## Research limitations

- Upstream and C4 inputs are simulated. Simulated defect scenarios and their
  expected scopes are authored by the implementer and not independently reviewed.
- Scores, weights, and confidences in stack selection are provisional policy
  assumptions. Approvals are caller-asserted; the approver is not authenticated.
- Generated code is never installed, built, or run by C3 or the research UI.
  Structural verification is static inspection, not testing.
- `MOCK` repair proves the pipeline only and repairs a single scenario (the
  service module); other scenarios fail visibly.
- `repair_success` is always `NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST`.
  C3 can claim that a scoped patch was applied and structurally inspected, not
  that a defect is fixed.
- Local-model output varies by model and hardware. A single demo run is not an
  evaluation, and no benchmark or research-completion percentage is claimed.
