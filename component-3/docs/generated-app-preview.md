# Manifest-verified generated application preview

This is an optional Docker-only runtime check for the generated React + Node.js
Task Management MVP. The Component 3 Research UI never executes generated code.
The preview workflow verifies the stored manifest, evidence digest, aggregate
artifact digest, and every file SHA-256 before making a new disposable copy.

## Safety boundary

- Generated `npm` and `node` commands run only inside a Linux container.
- The verified workspace is bind-mounted read-only and copied into container
  `/tmp` before dependency installation.
- The container runs as a non-root user, is read-only outside `tmpfs`, drops all
  Linux capabilities, uses `no-new-privileges`, and has CPU, memory, and PID
  limits.
- Ports are published on host loopback only: API `3001`, UI `5180`.
- `runtime-preview/executions/` is Git-ignored. Every execution ID must be new;
  the verifier refuses to overwrite historical evidence.
- The build and `npm install` require external package repositories. This is an
  operational limitation, not a claim that dependencies were independently
  audited or that network egress is restricted to one domain.

## Stored PP1 baseline identities

These are ignored local research artifacts, not Git-tracked fixtures. Always
run the verifier before relying on them.

| Mode | Run ID | Recorded artifact digest | Model-origin file |
| --- | --- | --- | --- |
| `TEMPLATE_ONLY` | `eaaa9365-efcf-4bc7-93a1-78cdf07b5de2` | `c99e46e40c76e6087c41a4b77a59c17a7179e58a6e40f8af18b0d4c9665b39b6` | none |
| `LOCAL_LLM` | `9ea01c6f-c7de-4c57-9d83-1e1f3f9158dd` | `20d1cedad7d08deb274cd8125096f956175cb46f6b076807d01f2bf3eca74c65` | `backend/src/services/taskService.js` |

## Run from Windows PowerShell

Prerequisites: Docker Desktop using Linux containers, ports `3001` and `5180`
free, and the Component 3 `.venv` with the backend installed editable.

From `component-3/`, choose a fresh execution ID. Do not reuse an old ID.

```powershell
$executionId = "pp1-preview-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
powershell -File .\runtime-preview\run-isolated-preview.ps1 `
  -WorkspaceRelativePath "local-llm-baseline/9ea01c6f-c7de-4c57-9d83-1e1f3f9158dd" `
  -ExecutionId $executionId `
  -ProjectSuffix pp1 `
  -Detached `
  -RunApiSmoke
```

Open:

- generated UI: <http://127.0.0.1:5180>
- generated API: <http://127.0.0.1:3001/api/v1/tasks>

The expected CRUD path is list, create, list, update, delete, and missing-item
404. A pass verifies this runtime instance only; it does not prove semantic
correctness, security, C4 readiness, or deployability.

Stop the specific preview without deleting its recorded execution folder:

```powershell
docker compose -f .\runtime-preview\compose.preview.yml `
  --project-name c3-preview-9ea01c6f-pp1 down
```

Evidence for the new execution remains under:

```text
runtime-preview/executions/<execution-id>/
|-- meta.json
|-- preview-meta.json
|-- api-smoke.json
|-- logs/
`-- workspace/               verified immutable copy used by Docker
```

## Current `Failed to fetch` diagnostic

The generated frontend calls `http://127.0.0.1:3001/api/v1/tasks`. A browser
`Failed to fetch` normally means the container is not running, port `3001` is
unavailable, or CORS rejected the page origin. The preview adapter accepts only
`http://127.0.0.1:5180` and `http://localhost:5180`, and forwards to the
generated Express process inside the same container.

Check in this order:

```powershell
docker ps --filter "name=c3-preview"
Invoke-RestMethod http://127.0.0.1:3001/api/v1/tasks
docker compose -f .\runtime-preview\compose.preview.yml `
  --project-name c3-preview-9ea01c6f-pp1 logs --tail 100
```

Previous screenshots or smoke JSON do not prove the current session is
healthy. Re-run the smoke and then perform a browser create/update/delete cycle.

## What the preview does not prove

- Generated persistence remains `IN_MEMORY`; `schema.sql` is design evidence,
  not a connected database.
- The preview does not perform a dependency vulnerability audit.
- C4 has not independently tested the generated application or regenerated
  patch. C4 retest stays `PENDING` and deployment stays `BLOCKED`.
- A successful browser CRUD exercise is demonstration evidence, not a research
  benchmark or general generator validation.
