# Component 3 backend

This directory contains the Python FastAPI service, the `intelise_c3` package,
and its automated tests. Component-level configuration remains one directory
above this folder so the backend and frontend share the same isolated C3 root.

From `component-3/` with the virtual environment active:

```powershell
python -m pip install -e "./backend[dev]"
Set-Location backend
python -m pytest
python -m uvicorn intelise_c3.main:app --host 127.0.0.1 --port 8000
```

The backend loads `../.env`, writes generated applications under
`../generated-workspaces/`, and stores local traceability data under
`../runtime/`. Those runtime paths remain excluded from Git.
