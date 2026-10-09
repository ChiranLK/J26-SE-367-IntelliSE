# Component 01 — Backend foundation

AI-Powered Intelligent Requirement Engineering Agent for Agile Software Development.
The complete component is intended to transform client communications into
structured requirements, classify FR/NFR, identify quality issues, generate
Agile artifacts and an SRS, and support client review and targeted regeneration.

This branch contains only the backend foundation. It does not represent
50% completion toward the proposed October 18, 2026 prototype deadline.
No extraction, classification, quality validation, RAG, LangGraph, audio
processing, SRS generation, MongoDB persistence, authentication, or deployment
is implemented. Other components and shared files are unchanged.

The companion branch is `component-1-frontend`.
Both worktrees can run together using the addresses below.
No credentials or generated dependencies are included.

## Backend setup and run on macOS

Requires Python 3.11 or 3.12 and curl. From this worktree's repository root:

```zsh
cd component-1/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.lock.txt
cp .env.example .env
python -m uvicorn intelise_c1.main:app --host 127.0.0.1 --port 8001 --reload
```

For Python 3.11, use `python3.11` instead. `pyproject.toml` declares dependency
ranges; `requirements-dev.lock.txt` records the verified Python 3.12 versions.
Installation requires internet access; runtime requires no external services.

The service uses the repository's Python `src/` convention. Its only functional
endpoint is `GET /api/v1/component-1/health`. It reports API process state only,
without claiming database or AI readiness.

Backend: <http://127.0.0.1:8001>. API docs: <http://127.0.0.1:8001/docs>.
The companion frontend runs at <http://127.0.0.1:5173>.

## Environment configuration

The optional local `.env` contains explicit allowed frontend origins:

```dotenv
C1_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

These are local placeholders, not credentials. No LLM key or database connection
is required. Start from `backend/` so `.env` is read from the right directory.
Origins must have no wildcard, path, or trailing slash. Restart after changes.

## Verify and troubleshoot

With the server running:

```zsh
curl --fail --show-error http://127.0.0.1:8001/api/v1/component-1/health
curl --include --header 'Origin: http://127.0.0.1:5173' http://127.0.0.1:8001/api/v1/component-1/health
```

Expected response:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

The second request includes `access-control-allow-origin: http://127.0.0.1:5173`.
From `component-1/backend/`, with the virtual environment active:

```zsh
python -m pytest
python -m ruff check .
python -m pip check
```

If imports fail, activate `.venv` and reinstall dependencies. If the port is
occupied, stop the conflicting service or select a new port and update the
companion frontend API URL. If curl works but the browser fails, check the exact
frontend origin against CORS settings; localhost and 127.0.0.1 differ. For
network installation failures, verify registry access and retry. Stop with Ctrl+C.
Never commit `.env`, `.venv`, credentials, caches, or build output.
