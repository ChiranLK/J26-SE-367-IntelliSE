# InteliSE Component 3

Component 3 is the Intelligent Development and Deployment Assistant for
traceable software generation. The service currently provides its FastAPI
foundation and deterministic validation of provisional C1/C2 input packages.

Generation, traceability persistence, scoped regeneration, deployment, and
real integrations with Components 1, 2, and 4 remain future work.

## Requirements

- Windows PowerShell
- Python 3.11 or Python 3.12
- A local Ollama installation will be required by later inference work, but it
  is not contacted by this foundation service.

Component 3 has no cloud LLM fallback. The configured Ollama URL and model are
stored for later use only.

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

## Configuration

The defaults are safe for a locally running Ollama instance:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

Copy `.env.example` to `.env` for local overrides. Never commit `.env` or
credentials. No generated application is executed automatically by this
service.
