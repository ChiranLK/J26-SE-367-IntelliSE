# INTELISE — Component 4: Intelligent Agentic Testing & Feedback Loop Assistant

> **Phase 1: Backend Foundation Only**  
> Part of the INTELISE Undergraduate Research Project.

---

## 1. Overview & Research Context

**INTELISE** (Intelligent Software Engineering) is an agentic multi-component research system for automated software generation, verification, and refinement.

Within INTELISE, **Component 4** serves as the **Intelligent Agentic Testing & Feedback Loop Assistant**:
- **Verification Authority**: Independently tests code produced by Component 3 using unit, integration, and performance testing agents.
- **Defect Reporting & Explainability**: Generates structured defect reports paired with conditional Explainable AI (XAI) feedback for actionable root-cause guidance.
- **Feedback Loop**: Communicates defects back to Component 3 for automated correction, and reverifies revised iterations.
- **Strict Boundary**: Component 4 **never directly modifies submitted code**.

During independent development, Component 4 supports manual and file-based submissions while Component 3 integration is being prepared.

---

## 2. Phase 1 Scope & Behavioral Boundaries

Phase 1 establishes the **backend foundation** of Component 4:
- [x] Modular FastAPI architecture with separated routes, schemas, services, repositories, and tests.
- [x] Manual code submission endpoint (code string, language, filename, requirement IDs, metadata).
- [x] Safe source file upload endpoint (strict extension allowlist, file size limits, text encoding validation, path traversal prevention, zero code execution).
- [x] Verification run lifecycle model (`PENDING`, `RUNNING`, `PASSED`, `FAILED`, `ERROR`).
- [x] Repository abstraction layer supporting both ephemeral in-memory storage and MongoDB Atlas.
- [x] Environment configuration with `.env.example` (no hardcoded secrets).
- [x] Strict CORS origin configuration.
- [x] Structured logging and standardized error envelopes.
- [x] Automated pytest test suite covering all endpoints and validation rules.

### Important Behavioral Restrictions
- **No fake AI agents**: No simulated test passes or fabricated metrics.
- **Strict status integrity**: Verification runs are created with `PENDING` status. No run is marked `PASSED` without real verification evidence.
- **Zero code execution**: Uploaded or submitted code is strictly stored as text; code execution is deferred to isolated containerized test runners in Phase 2.
- **No external service mocks**: Clean integration boundaries are preserved for future Component 3 APIs without mock services.

---

## 3. Storage Architecture: Ephemeral Memory vs. MongoDB Atlas

Component 4 features a **Repository Pattern** (`BaseSubmissionRepository`, `BaseVerificationRunRepository`) that separates domain business logic from database drivers:

```
FastAPI Endpoints ──▶ Services (SubmissionService, VerificationService)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
       InMemoryRepository        MongoRepository (PyMongo)
    (Active in Dev / Testing)    (Atlas Ready)
```

> [!WARNING]
> ### Ephemeral In-Memory Storage Warning
> When `STORAGE_BACKEND=memory` (the default for local development while the Atlas cluster is unavailable):
> - **All data resides exclusively in process memory.**
> - **Temporary data is COMPLETELY LOST whenever the server restarts or stops.**
> - To retain data across restarts, set `STORAGE_BACKEND=mongodb` and configure `MONGODB_URI` once your Atlas cluster credentials are ready.

---

## 4. Project Directory Structure

```
component-4/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application factory, CORS, lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # Dependency injection providers
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py           # Combined v1 router
│   │       ├── health.py           # /health endpoint
│   │       ├── submissions.py      # Manual submission & file upload routes
│   │       └── verifications.py    # Verification run routes
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # pydantic-settings configuration
│   │   ├── errors.py               # Custom exceptions & global exception handlers
│   │   └── logging.py              # Structured logging configuration
│   ├── repositories/
│   │   ├── __init__.py             # Repository factories
│   │   ├── base.py                 # Abstract base repository interfaces
│   │   ├── in_memory.py            # Temporary in-memory stores
│   │   └── mongo.py                # PyMongo / Atlas implementations
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py               # Common enums (Language, Status, Severity)
│   │   ├── submission.py           # Code submission Pydantic schemas
│   │   ├── verification.py         # Verification run Pydantic schemas
│   │   ├── test_result.py          # Test result schemas (Phase 2+ ready)
│   │   ├── defect_report.py        # Defect report schemas (Phase 2+ ready)
│   │   └── feedback.py             # Feedback loop iteration schemas
│   └── services/
│       ├── __init__.py
│       ├── submission_service.py   # Submission validation & safe file upload
│       └── verification_service.py # Verification run management
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures & repository state resets
│   ├── test_file_upload.py         # File upload security and validation tests
│   ├── test_health.py              # Health check endpoint tests
│   ├── test_submissions.py         # Manual submission endpoint tests
│   └── test_verifications.py       # Verification lifecycle tests
├── .env.example                    # Environment template
├── .gitignore                      # Git ignore configuration
├── README.md                       # Documentation
└── requirements.txt                # Exact pinned dependencies
```

---

## 5. Getting Started & Installation

### Prerequisites
- Python 3.12 (Python 3.12.10 recommended)
- Git

### 1. Set Up Virtual Environment

**Windows (PowerShell):**
```powershell
cd component-4
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
cd component-4
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to create your local `.env`:

```bash
cp .env.example .env    # Linux / macOS
copy .env.example .env  # Windows PowerShell / CMD
```

Default settings in `.env.example` enable in-memory storage (`STORAGE_BACKEND=memory`), allowing immediate local development without a database connection.

---

## 6. Running the Application

Start the development server with Uvicorn:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running:
- **API Root**: [http://localhost:8000/](http://localhost:8000/)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 7. API Endpoints Reference

### Health Endpoints
- `GET /health` or `GET /api/v1/health`  
  Returns operational status, version, and active storage backend.

### Submissions Endpoints
- `POST /api/v1/submissions`  
  Accepts manual JSON code submission.  
  *Payload:*
  ```json
  {
    "code": "def add(a: int, b: int) -> int:\n    return a + b",
    "language": "python",
    "filename": "calculator.py",
    "requirement_ids": ["REQ-001", "REQ-002"],
    "metadata": { "author": "Component-3" }
  }
  ```
  *Response:* `201 Created` with generated submission ID (e.g., `sub-a1b2c3d4e5f6`).

- `POST /api/v1/submissions/upload`  
  Accepts source file upload (`multipart/form-data`).  
  *Form fields:*
  - `file`: Source code file (max 2MB, allowed extensions: `.py`, `.js`, `.ts`, `.java`, `.cpp`, `.c`, `.cs`, `.go`, etc.).
  - `language` *(optional)*: Explicit language override.
  - `requirement_ids` *(optional)*: Comma-separated requirement IDs (e.g., `"REQ-01,REQ-02"`).

- `GET /api/v1/submissions`  
  Lists stored submissions (supports pagination with `?skip=0&limit=50`).

- `GET /api/v1/submissions/{submission_id}`  
  Retrieves full submission details by ID.

### Verification Runs Endpoints
- `POST /api/v1/verifications`  
  Initiates a verification run for a submission.  
  *Payload:*
  ```json
  {
    "submission_id": "sub-a1b2c3d4e5f6",
    "triggered_by": "manual",
    "test_types": ["unit", "integration", "performance"]
  }
  ```
  *Response:* `201 Created` with status `PENDING` (prepared for Phase 2 agent execution).

- `GET /api/v1/verifications`  
  Lists verification runs (supports filtering by `?submission_id=...`).

- `GET /api/v1/verifications/{run_id}`  
  Retrieves full verification run details including test results, defect reports, and feedback history.

- `GET /api/v1/verifications/{run_id}/status`  
  Retrieves lightweight status object (`PENDING`, `RUNNING`, `PASSED`, `FAILED`, `ERROR`).

---

## 8. Running Automated Tests

Run the complete test suite with pytest:

```bash
pytest -v
```

All 24 automated unit and integration tests validate:
- Root, health-check, and versioned health-check endpoints.
- Manual submission validation (empty code rejection, language enum enforcement, metadata storage).
- File upload safety (extension allowlists, file size boundaries, path traversal sanitization, UTF-8 validation).
- Verification run initialization (ensuring strictly `PENDING` status without fake test runs).
- Verification run retrieval, status retrieval, and filtered listings.

---

## 9. Security Notes

1. **No Code Execution**: In Phase 1, submitted code is treated solely as plain text data. The application never executes user-submitted or component-submitted code.
2. **Path Traversal Defense**: File upload sanitization enforces `os.path.basename()` and strips dangerous relative path segments (`../`).
3. **MIME & Extension Enforcement**: Binary files and disallowed extensions (`.exe`, `.sh`, `.bin`) are rejected with `400 Bad Request`.
4. **Size Bounds**: Upload size is capped at 2MB by default (configurable via `MAX_UPLOAD_SIZE_BYTES`).
5. **CORS Whitelist**: Explicitly configured origins (`ALLOWED_ORIGINS`) prevent unauthorized browser origins from querying the API.

---

## 10. Research Roadmap

- **Phase 1 (Current)**: Backend foundation, API contracts, in-memory & Atlas repository abstraction, verification run lifecycle.
- **Phase 2**: Multi-agent test execution (Unit, Integration, Performance agents via LangGraph and local Ollama LLMs).
- **Phase 3**: Explainable AI (XAI) feedback generator and automated defect communication loop with Component 3.
- **Phase 4**: React & TypeScript web interface for real-time verification monitoring and feedback inspection.
