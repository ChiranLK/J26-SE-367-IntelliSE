# Component 3 directory structure

Component 3 keeps its service and user interface in separate, explicit
directories:

```text
component-3/
|-- backend/              Python FastAPI service and tests
|   |-- src/intelise_c3/
|   |-- tests/
|   `-- pyproject.toml
|-- frontend/             React Component 3 Research UI
|-- contracts/            Integration-contract documentation
|-- docs/                 Research and operating documentation
|-- generated-workspaces/ Generated application runs (Git-ignored)
|-- runtime/              Local traceability persistence (Git-ignored)
|-- .env.example
`-- README.md
```

The folders under a generated workspace may also be named `backend/` and
`frontend/`; those are generated application artifacts, not the Component 3
FastAPI service or Research UI.

The `.env` file, generated workspace root, and SQLite traceability store remain
anchored to `component-3/`, while Python packaging and pytest configuration are
owned by `component-3/backend/`.
