# Component 01 backend

Component 01 is the AI-Powered Intelligent Requirement Engineering Agent for
Agile Software Development in the IntelliSE fourth-year research project.
The proposed 50% prototype deadline is October 18, 2026. This directory provides
the backend foundation only; it does not represent the completed prototype.

## Current behavior

FastAPI serves a typed availability response, interactive API documentation,
and explicit configurable development CORS origins. The health endpoint works
without MongoDB, an LLM API key, downloaded models, or any external service.
It confirms application availability only, not database or AI readiness.

Project persistence, requirement extraction, FR/NFR classification, quality
validation, RAG, LangGraph, audio processing, and SRS generation remain future
work. No frontend or research results are included.

## macOS setup

Supported runtime: **Python 3.12** (verified with 3.12.8). Install Python 3.12
first if `python3.12 --version` is unavailable. Dependency management uses pip
and `pyproject.toml`; `requirements.lock` pins the resolved runtime and test
dependencies for reproducible installation. No other package manager is needed.

From the repository root, run:

```sh
cd component-1/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e '.[dev]'
cp .env.example .env
python -m pip check
python -m pytest
python -m intelise_c1
```

The virtual environment isolates this backend's dependencies from other
components. Run all commands below from `component-1/backend` with it active.
For subsequent sessions:

```sh
cd component-1/backend
source .venv/bin/activate
python -m intelise_c1
```

Stop the server with Ctrl+C. The equivalent installed command is
`component-1-backend`.

## Environment setup

`.env` is optional and ignored by Git. `.env.example` contains only example
development values, with no credentials. Defaults are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `C1_BACKEND_HOST` | `127.0.0.1` | Local bind address |
| `C1_BACKEND_PORT` | `8001` | TCP port (1–65535) |
| `C1_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | Exact allowed browser origins |

Environment variables override `.env`. The `.env` file is read from the current
working directory; run from this backend directory. CORS origins use a JSON
array of HTTP(S) origins, including the port where applicable. Wildcards,
paths, and trailing slashes are rejected. An empty array disables cross-origin
access. Credentials are disabled and only GET is allowed for browser preflight
requests. CORS is a browser policy, not authentication; unlisted origins do not
receive an allow-origin header.

For example, temporarily override the port:

```sh
C1_BACKEND_PORT=8011 python -m intelise_c1
```

For development reload, Uvicorn's CLI requires its own explicit host/port flags
(it does not read `C1_BACKEND_HOST` or `C1_BACKEND_PORT`):

```sh
python -m uvicorn intelise_c1.main:app --host 127.0.0.1 --port 8001 --reload
```

## Verify the running API

At the default host and port:

- Health: <http://127.0.0.1:8001/api/v1/component-1/health>
- Swagger UI: <http://127.0.0.1:8001/docs>
- ReDoc: <http://127.0.0.1:8001/redoc>
- OpenAPI schema: <http://127.0.0.1:8001/openapi.json>

From another terminal:

```sh
curl --fail-with-body -i http://127.0.0.1:8001/api/v1/component-1/health
```

Expected HTTP status: `200`. Expected JSON:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

Check the default allowed-origin response:

```sh
curl --fail-with-body -i \
  -H 'Origin: http://localhost:5173' \
  http://127.0.0.1:8001/api/v1/component-1/health
```

Expect `access-control-allow-origin: http://localhost:5173`.
Run automated health, CORS, and configuration smoke checks with `python -m pytest`.

## Dependency updates

The lock includes development dependencies and the pinned setuptools build
backend. To intentionally refresh it, use a fresh Python 3.12 virtual
environment, install `setuptools==80.9.0`, then install `-e '.[dev]'` and export
`python -m pip freeze --exclude-editable`. Review the version changes, replace
the pinned lines in `requirements.lock`, and repeat setup and verification.
Do not export unrelated system or other-component packages into the lock.

## Troubleshooting

- **`python3.12: command not found`:** Install Python 3.12 for macOS and open a
  new terminal. Confirm `python3.12 --version` before creating the environment.
- **`No module named intelise_c1`:** Activate `.venv` and repeat the editable
  installation from this directory. Check `which python` points inside `.venv`.
- **Dependency download fails:** Check network access to PyPI and retry the
  locked installation. Do not remove version pins to bypass a download error.
- **Address already in use:** Stop the process using port 8001 or choose a free
  `C1_BACKEND_PORT`. Use that port in health and documentation URLs.
- **Invalid settings:** Check the port range and the CORS JSON array in `.env`.
  Match the browser origin exactly; `localhost` and `127.0.0.1` differ.
- **Connection refused:** Keep the server terminal running and check startup
  logs, bind host, and port. No database or AI service needs to be started.
- **CORS error:** Add the actual development browser origin to
  `C1_CORS_ORIGINS` and restart. An OPTIONS preflight for an unlisted origin
  returns 400; an ordinary GET remains available without an allow-origin header.

No shared repository files or other components are required to run this service.
