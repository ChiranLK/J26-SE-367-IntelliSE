# InteliSE Component 3

Component 3 is the Intelligent Development and Deployment Assistant for
traceable software generation. The service currently provides its FastAPI
foundation, deterministic validation of provisional C1/C2 input packages,
limited-subset design understanding, evidence-based stack selection, and a
reusable local-only Ollama inference client.

Full application generation, traceability persistence, scoped regeneration,
deployment, and real integrations with Components 1, 2, and 4 remain future
work.

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

Stack selection evaluates exactly React/Angular × Node.js/Spring Boot. Task 4
does not implement a working generator, so all candidates currently report
`NOT_IMPLEMENTED`. React + Node.js is separately identified as the sole October
21 MVP generator target; unavailable selections are never silently substituted.

## Configuration

The defaults are safe for a locally running Ollama instance:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_TEMPERATURE=0.0
OLLAMA_NUM_CTX=4096
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

## Current local-inference limitations

- The client provides reusable inference plumbing only; full React + Node.js
  generation is not implemented.
- Model output is treated as untrusted text and is never executed automatically.
- Local endpoint validation, cloud-tag rejection, and remote-model metadata
  checks are MVP controls, not a complete host-level network sandbox. Ollama
  should also be configured in local-only mode by the operator.
- The client records evidence for reproducibility but does not claim that
  stochastic output is perfectly reproducible.
- The LLM cannot validate C1/C2 approval authenticity, authorize deployment, or
  provide Component 4's XAI defect explanations.
- Living traceability and defect-feedback-driven scoped regeneration remain
  future work.
