# Friday Supervisor Demo: Real Ollama and Three Testing Types

## Readiness verdict

`FRIDAY_DEMO_READY`

Validated on 20 October 2026 through the real React frontend, MongoDB-backed FastAPI API, isolated Docker runner, and local Ollama `qwen2.5-coder:3b` model.

## Demonstration files

- Defective ZIP: `component-4/demo_scenarios/friday_defective_three_tests.zip`
- Clean ZIP: `component-4/demo_scenarios/friday_clean_three_tests.zip`
- Defective source tree: `component-4/demo_scenarios/friday_defective/`
- Clean source tree: `component-4/demo_scenarios/friday_clean/`
- Single-source upload example: `component-4/demo_scenarios/friday_clean/shop/pricing.py`

Each ZIP contains separately categorized authorized tests under `tests/unit`, `tests/integration`, and `tests/performance`. The performance oracle explicitly requires checkout execution below 50 ms; Component 4 also reports its configured 200 ms p95 threshold.

## Exact startup commands

Open PowerShell in the repository root:

```powershell
cd 'D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4'
```

### 1. Docker

Start Docker Desktop, then verify the daemon and runner image:

```powershell
docker version
docker image inspect intelise-python-runner:3.12
```

Build the existing image only if it is missing:

```powershell
docker build -t intelise-python-runner:3.12 -f backend/docker/Dockerfile.python-runner backend/docker
```

### 2. Ollama

In terminal 1:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11434'
ollama serve
```

In another terminal:

```powershell
ollama --version
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
Invoke-RestMethod http://127.0.0.1:11434/api/tags

$body = @{
  model = 'qwen2.5-coder:3b'
  prompt = 'Return JSON with status set to ok.'
  stream = $false
  format = 'json'
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11434/api/generate -Method Post -ContentType 'application/json' -Body $body
```

Do not start a second `ollama serve` process if `/api/version` already responds.

### 3. Backend

The host machine currently has a global `DEBUG=release` environment variable, which is not a valid Boolean. Override it for this process:

```powershell
$env:DEBUG='false'
$env:COMPONENT_3_ENABLED='false'
$env:OLLAMA_ENABLED='true'
$env:OLLAMA_BASE_URL='http://127.0.0.1:11434'
$env:OLLAMA_MODEL='qwen2.5-coder:3b'
\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The checked-in local configuration selects MongoDB. Confirm persistence and AI connectivity:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/verifications/status/ai-engine
```

Expected health evidence includes `storage_backend: mongodb`, `is_ephemeral_storage: false`, `ollama_connected: true`, and `qwen2.5-coder:3b` in `available_models`.

### 4. Frontend

In terminal 3:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/submissions/new`.

## Defective-project walkthrough

1. On **New Submission**, click the plus button and choose **Upload Project ZIP**.
2. Select `demo_scenarios/friday_defective_three_tests.zip`.
3. Click **Verify Project** and confirm that the six-file project tree is shown.
4. Click **Initiate Verification Pipeline**.
5. Leave Unit, Integration, and Performance selected and click **Launch Pipeline**.
6. Open the pending run and click **Execute in Sandbox**.
7. Wait for the terminal `FAILED` state.
8. Point out the three separate result cards:
   - Unit Testing: one pass and one genuine failed assertion.
   - Integration Testing: the pricing/checkout interaction genuinely fails.
   - Performance Testing: p95 and the 200 ms threshold are displayed; the workload is within threshold.
9. In **Evidence-Based Defect Analysis**, show:
   - failed test and assertion (`100.0 != 90.0` and `110.0 != 99.0`);
   - affected source files `shop/pricing.py` and `shop/checkout.py`;
   - expected and observed values;
   - local AI evidence showing `LLM_ASSISTED`, invocation count 1, successful response count 1, and model `qwen2.5-coder:3b`;
   - **Verified facts**, **AI-assisted hypothesis**, and **Suggested correction** as distinct content.

### What to say

> These failures come from authorized pytest assertions executed in an isolated, network-disabled Docker container. The failed values and affected files are verified facts. Ollama is invoked only after those failures exist; its root-cause wording is a reviewable hypothesis and cannot replace the test evidence. This is intermediate defect assistance, not authorized Post-Delivery XAI.

## Clean-project walkthrough

1. Return to **New Submission** and upload `demo_scenarios/friday_clean_three_tests.zip`.
2. Initiate a run with all three test types selected.
3. Click **Execute in Sandbox**.
4. Confirm that Unit Testing, Integration Testing, and Performance Testing are all `PASSED`.
5. Show the green **SUCCESSFUL / PASSED** banner and **Zero Defects Detected** message.
6. Point out that the AI telemetry is `DETERMINISTIC_ONLY` with zero invocations for a clean run. This is intentional selective invocation, not a silent fallback.

### What to say

> All authorized unit assertions, cross-module integration checks, and the explicit performance threshold passed. Because there is no defect to explain, the pipeline correctly makes no Ollama call and displays no fabricated defect.

## Validated evidence

### Browser-run defective scenario

- Submission: `sub-48a76f8f7425`
- Verification run: `run-d3a5485109a1`
- Overall: `FAILED`
- Unit: 1 passed, 1 failed
- Integration: 0 passed, 1 failed
- Performance: passed; p95 1.0 ms, threshold 200.0 ms, no breach
- Ollama: `LLM_ASSISTED`, enabled, 1 invocation, 1 successful structured response, 0 failed responses, 0 fallbacks
- Model: `qwen2.5-coder:3b`
- Affected files: `shop/pricing.py:13`, `shop/checkout.py:7`
- Browser screenshot: `state/friday-demo/browser-defective.png`

### Browser-run clean scenario

- Submission: `sub-325aa654e313`
- Verification run: `run-e80aadc10b02`
- Overall: `PASSED`
- Unit: 2 passed, 0 failed
- Integration: 1 passed, 0 failed
- Performance: passed; p95 1.0 ms, threshold 200.0 ms, no breach
- Defects: 0
- Ollama calls: 0, by design because no defect reasoning was required
- Browser screenshot: `state/friday-demo/browser-clean.png`

### Single-file browser upload

- File: `demo_scenarios/friday_clean/shop/pricing.py`
- Persisted submission: `sub-e019bf2cc205`
- Frontend rendered **Source Code Submission Ingested**.

## Troubleshooting

### Port or process ownership

```powershell
Get-Process -Name '*ollama*' -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue
netstat -ano | Select-String ':11434'
netsh interface ipv4 show excludedportrange protocol=tcp
```

Port 11434 was not reserved during validation. Do not blindly kill processes or remove Windows port exclusions.

### Safe alternate Ollama port

If another identified process legitimately owns 11434, use a temporary localhost port instead of altering the firewall or port reservations:

```powershell
# Ollama terminal
$env:OLLAMA_HOST='127.0.0.1:11435'
ollama serve

# Backend terminal, before starting uvicorn
$env:OLLAMA_BASE_URL='http://127.0.0.1:11435'
```

Then verify both `/api/tags` and the backend AI-engine endpoint.

### Logs and checks

```powershell
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 100
Get-Content "$env:LOCALAPPDATA\Ollama\app.log" -Tail 100
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/verifications/status/ai-engine
docker ps -a --filter 'name=intelise_run_'
```

If the UI appears stale, restart FastAPI after code changes; the documented command intentionally does not use auto-reload.

## Limitations and intentionally unimplemented integrations

- Real Component 3 dispatch remains disabled (`COMPONENT_3_ENABLED=false`).
- Post-Delivery XAI authorization gates are unchanged. The defect explanation shown here is explicitly intermediate, evidence-grounded assistance.
- A clean run intentionally bypasses LLM defect reasoning; zero LLM calls on clean code is expected.
- Performance telemetry reports the isolated performance test duration and configured p95 threshold. This small demo uses one explicit performance workload, not a production load-testing campaign.
- The browser demo covers Python source and ZIP ingestion only, matching Friday's scope.
- No benchmark data, frozen evaluation artifacts, firewall policy, Windows port reservation, or governance security gate was changed.
