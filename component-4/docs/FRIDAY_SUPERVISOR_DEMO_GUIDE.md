# INTELISE Component 4 — Friday Supervisor Demonstration Guide

**Project:** `D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4`  
**Target Milestone:** Friday Supervisor Demonstration & Evaluation  
**Status Verdict:** `FRIDAY_DEMO_READY` (Fully validated with real Docker, MongoDB Atlas, FastAPI, React, and local Ollama `qwen2.5-coder:3b`)

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Exact PowerShell Startup Commands](#2-exact-powershell-startup-commands)
3. [Docker Readiness Check](#3-docker-readiness-check)
4. [MongoDB Readiness Check](#4-mongodb-readiness-check)
5. [Ollama Model Readiness Check](#5-ollama-model-readiness-check)
6. [Frontend and Backend Startup](#6-frontend-and-backend-startup)
7. [Location of Defective and Clean Demo Files](#7-location-of-defective-and-clean-demo-files)
8. [Step-by-Step Defective-Code Demonstration (Scenario A)](#8-step-by-step-defective-code-demonstration-scenario-a)
9. [Step-by-Step Corrected-Code Demonstration (Scenario B)](#9-step-by-step-corrected-code-demonstration-scenario-b)
10. [How to Demonstrate All Three Testing Types](#10-how-to-demonstrate-all-three-testing-types)
11. [How to Demonstrate Successful Authorized Delivery](#11-how-to-demonstrate-successful-authorized-delivery)
12. [How to Demonstrate Post-Delivery XAI](#12-how-to-demonstrate-post-delivery-xai)
13. [What to Say to the Supervisor (Presentation Script)](#13-what-to-say-to-the-supervisor-presentation-script)
14. [Known Limitations](#14-known-limitations)
15. [Troubleshooting Instructions](#15-troubleshooting-instructions)

---

## 1. Prerequisites

Before starting the demonstration, verify that your computer has:
- **Windows 10/11** with PowerShell 5.1 or PowerShell 7+
- **Docker Desktop** installed and running with Linux containers mode enabled.
- **Python 3.12** virtual environment located at `.venv\Scripts\python.exe`.
- **Node.js 18+** and `npm` installed.
- **Ollama for Windows** installed at `C:\Users\NIMADITH\AppData\Local\Programs\Ollama\ollama.exe`.
- **Ollama Model:** `qwen2.5-coder:3b` pulled locally (`ollama pull qwen2.5-coder:3b`).
- **MongoDB Atlas Connection** configured in `backend/.env`.

---

## 2. Exact PowerShell Startup Commands

Open three dedicated PowerShell terminal windows in the workspace root directory:

```powershell
cd 'D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4'
```

### Terminal 1: Local Ollama Daemon
```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama serve
```
*(Leave running. If Ollama is already running as a Windows service or tray application, check step 5).*

### Terminal 2: FastAPI Backend
```powershell
cd 'D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4'
$env:DEBUG = 'false'
$env:COMPONENT_3_ENABLED = 'false'
$env:OLLAMA_ENABLED = 'true'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:OLLAMA_MODEL = 'qwen2.5-coder:3b'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

### Terminal 3: React Frontend (Vite)
```powershell
cd 'D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4\frontend'
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## 3. Docker Readiness Check

In any PowerShell window, verify Docker is responding and the runner image is built:

```powershell
docker version
docker image inspect intelise-python-runner:3.12 --format 'Image SHA: {{.Id}}'
```

**Expected output:**
```text
Image SHA: sha256:eb45f2a070ca4d178ead4a2d9ed626b2ea4ca2e179a4d061e9ccb845b0d017ce
```

If the image is missing, build it with:
```powershell
docker build -t intelise-python-runner:3.12 -f backend/docker/Dockerfile.python-runner backend/docker
```

---

## 4. MongoDB Readiness Check

Verify backend connection to MongoDB by querying the health endpoint:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/health | ConvertTo-Json
```

**Expected output:**
```json
{
  "status": "ok",
  "storage_backend": "mongodb",
  "is_ephemeral_storage": false
}
```

---

## 5. Ollama Model Readiness Check

Verify Ollama is responding and the `qwen2.5-coder:3b` model is loaded:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/verifications/status/ai-engine | ConvertTo-Json
```

**Expected output:**
```json
{
  "ollama_enabled": true,
  "ollama_base_url": "http://127.0.0.1:11434",
  "configured_model": "qwen2.5-coder:3b",
  "ollama_connected": true,
  "available_models": ["qwen2.5-coder:3b"],
  "status_message": "Ollama is active with 1 model(s) installed: qwen2.5-coder:3b"
}
```

---

## 6. Frontend and Backend Startup

Open Google Chrome or Edge and navigate to:
```text
http://127.0.0.1:5173/submissions/new
```

Verify that the navigation bar, **New Submission** header, and the unified composer load cleanly.

---

## 7. Location of Defective and Clean Demo Files

The demonstration projects are prepared in `component-4\demo_scenarios`:

1. **Defective Project ZIP:**
   `D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4\demo_scenarios\friday_defective_three_tests.zip`
   - Files: `shop/pricing.py`, `shop/checkout.py`, `tests/unit/test_unit_pricing.py`, `tests/integration/test_integration_checkout.py`, `tests/performance/test_performance_checkout.py`.
   - Bug: In `shop/pricing.py`, `apply_discount(value, rate)` returns `value` instead of `value * (1.0 - rate)`.

2. **Clean Project ZIP:**
   `D:\GitHub Projects\Research Project\J26-SE-367-IntelliSE\component-4\demo_scenarios\friday_clean_three_tests.zip`
   - Same multi-file structure with the discount bug fixed (`return round(value * (1.0 - rate), 2)`).

3. **Unsupported C Sample:**
   Paste directly into editor:
   ```c
   #include <stdio.h>
   int main() { printf("Hello IntelliSE\n"); return 0; }
   ```

---

## 8. Step-by-Step Defective-Code Demonstration (Scenario A)

### Objective
Show the supervisor that defective code is caught by genuine tests, accurately classified, stops the delivery workflow, and keeps human-facing XAI strictly locked.

### Steps:
1. Open `http://127.0.0.1:5173/submissions/new`.
2. Click the **`+` (Attachment)** button in the bottom-left of the composer.
3. Select **Upload Project ZIP**.
4. Browse and select `friday_defective_three_tests.zip`.
5. Notice the **Project ZIP** chip appears in the composer.
6. Click the green **Run Verification** button.
7. Observe execution status transitions: `PENDING` → `RUNNING` in container → `FAILED`.
8. Observe the results:
   - **UNIT TESTING:** `FAILED` (1 passed, 1 failed: `test_unit_apply_discount` assertion failure).
   - **INTEGRATION TESTING:** `FAILED` (0 passed, 1 failed: cross-module checkout discount interaction failed).
   - **PERFORMANCE TESTING:** `PASSED` (measured latency ~0.12ms <= 500ms threshold SLA).
   - **OVERALL VERDICT:** `FAILED`.
   - **Technical Failure Evidence:** Shows `shop/pricing.py:13` line location, traceback, and defect classification.
   - **POST-DELIVERY XAI:** Explicitly displays **LOCKED** with banner: *"Post-Delivery Human-Facing XAI Locked — Software failed verification. User-facing explanation is strictly withheld until all defects are resolved."*
   - Delivery is blocked.

---

## 9. Step-by-Step Corrected-Code Demonstration (Scenario B)

### Objective
Show the supervisor the clean code path: all 3 test categories pass, deployment governance approves, delivery is authorized in development simulation, and real Ollama generates post-delivery human-facing software documentation.

### Steps:
1. On the same page, click **Clear** (or **Submit Another**).
2. Click the **`+` (Attachment)** button → **Upload Project ZIP**.
3. Select `friday_clean_three_tests.zip`.
4. Click **Run Verification**.
5. Observe execution: container runs pytest inside Docker sandbox.
6. Observe results:
   - **UNIT TESTING:** `PASSED` (2 passed, 0 failed).
   - **INTEGRATION TESTING:** `PASSED` (1 interaction passed: `shop.checkout` + `shop.pricing` verified).
   - **PERFORMANCE TESTING:** `PASSED` (0.12ms p95 <= 500ms threshold SLA).
   - **OVERALL VERDICT:** `PASSED`.
   - **Deployment Readiness Governance:** `APPROVED`.
   - **Downstream Delivery Gate:** `PENDING AUTHORIZATION`.
7. Scroll down to the Post-Delivery XAI gate.
8. Click **Authorize Dev Delivery Simulation**.
9. Notice:
   - Delivery is confirmed with a generated ID (e.g. `dlv-feb6fdebea02`).
   - The delivery gate status changes to `AUTHORIZED`.
   - Ollama `qwen2.5-coder:3b` generates post-delivery software explanations in real-time.
   - Inference provenance displays: `qwen2.5-coder:3b • GENUINE LOCAL LLM INFERENCE`.
   - Toggle between **Beginner View** (clear, plain English explanation) and **Technical View** (8 dimensions).

---

## 10. How to Demonstrate All Three Testing Types

Point out each distinct category in the 3-column verification grid:

1. **Unit Testing:**
   - Evaluates pure functions in isolation (`shop.pricing.calculate_subtotal`, `apply_discount`).
   - Tests boundary conditions, edge cases, and arithmetic assertions.

2. **Integration Testing:**
   - Evaluates multi-module interaction between `shop.checkout.process_order` and `shop.pricing.apply_discount`.
   - Point out: Safe AST syntax checking is **not** counted as integration testing; genuine cross-module interaction assertions must execute.

3. **Performance Testing:**
   - Measures p95 latency inside the container.
   - Compares measured execution against configured SLA threshold (e.g. 500 ms).
   - Produces a deterministic pass/fail verdict based on latency limits.

---

## 11. How to Demonstrate Successful Authorized Delivery

1. Explain the **3-Phase Research Gate**:
   - Step 1: Verification must pass (0 failed assertions).
   - Step 2: Deployment-readiness governance must approve (no security blockers).
   - Step 3: Explicit downstream delivery confirmation.
2. In the UI, show that even when tests pass, Post-Delivery XAI is **not** immediately displayed until the user clicks **Authorize Dev Delivery Simulation**.
3. Once clicked, show the server-generated delivery confirmation ID (`dlv-...`), timestamp, and SHA-256 artifact checksum binding.
4. Explain that simulated delivery is clearly labeled for development/demonstration mode and cannot bypass production credentials.

---

## 12. How to Demonstrate Post-Delivery XAI

Show the supervisor the post-delivery software understanding console:
1. **Inference Provenance Badge:**
   - Shows `qwen2.5-coder:3b`, execution duration in seconds, and `GENUINE LOCAL LLM` badge.
2. **Beginner View:**
   - High-level overview: what the software does in simple terms.
   - How to use it in user applications.
   - Safety notes and operating boundaries.
3. **Technical View across 8 Core Dimensions:**
   - **Dimension 1:** Software Purpose & Overview.
   - **Dimension 2:** Architecture & Module Responsibilities.
   - **Dimension 3:** Important Functions & Business Logic.
   - **Dimension 4:** API Contracts & Data Flow.
   - **Dimension 5:** Verified Behavior & Test Evidence.
   - **Dimension 6:** Measured Performance & SLA Compliance.
   - **Dimension 7:** Algorithms & Design Decisions.
   - **Dimension 8:** Assumptions & Verification Scope Limits.

---

## 13. What to Say to the Supervisor (Presentation Script)

> *"Good morning / afternoon. Today I am demonstrating Component 4 of IntelliSE: Intelligent Agentic Verification and Post-Delivery Explainable AI.*
>
> *Our core research contribution addresses a critical flaw in traditional AI-assisted CI/CD: confusing test failure diagnostics with software explanations. In our architecture, there are two strictly decoupled stages:*
>
> 1. *During verification, any defect produces structured technical failure evidence—such as failed assertions, tracebacks, and affected source files. User-facing explanation is strictly withheld because explaining defective software to end-users is unsafe.*
> 2. *Only after software has passed Unit, Integration, and Performance verification, cleared governance, and been authorized for delivery, do we generate post-delivery Explainable AI.*
>
> *Let's first look at Scenario A: a multi-file Python project with a pricing discount defect.*
> *(Click Run Verification on defective ZIP)*
> *Notice that Unit and Integration testing fail with real assertions, the overall verdict is FAILED, and the Post-Delivery XAI is strictly LOCKED.*
>
> *Now let's look at Scenario B: the corrected project.*
> *(Click Run Verification on clean ZIP)*
> *All three testing categories pass inside Docker. Notice that even though tests pass, the human-facing XAI remains gated until delivery is confirmed.*
> *(Click Authorize Dev Delivery Simulation)*
> *Now delivery is confirmed, and our local Ollama model—qwen2.5-coder:3b running on GPU—synthesizes an 8-dimension software understanding package explaining the delivered system to the user.*
>
> *Finally, if we submit unsupported C code, the system immediately marks it as BLOCKED with clear diagnostics, without hanging in PENDING or running unsafe containers.*
>
> *This concludes our demonstration of reliable, decoupled verification and post-delivery XAI."*

---

## 14. Known Limitations

Be upfront with the supervisor if asked:
1. **Language Runner Scope:** Python 3.12 is the fully supported, containerized execution runtime for this milestone. Other languages (like C, Go, Java) safely transition to `BLOCKED` with clear user messaging.
2. **Component 3 Automated Repair:** Live network dispatch to Component 3 is simulated/fail-closed for standalone demonstration so Component 4 can be evaluated independently without external server dependencies.
3. **Delivery Simulation:** The development mode delivery simulator generates genuine verification gates and explanations, but is explicitly labeled as non-production.

---

## 15. Troubleshooting Instructions

### Issue: Backend returns 500 or says `storage_backend: in_memory`
**Fix:** Verify `backend/.env` contains valid `MONGODB_URL`. Run `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health` to confirm `storage_backend: mongodb`.

### Issue: Ollama returns connection refused (`127.0.0.1:11434`)
**Fix:** Run `ollama serve` in PowerShell. In another terminal, test with `Invoke-RestMethod http://127.0.0.1:11434/api/version`.

### Issue: Ollama model generation is slow
**Fix:** The `qwen2.5-coder:3b` model runs on GPU via CUDA. If running on CPU only, inference takes ~15–20 seconds. The frontend displays a loading spinner during synthesis.

### Issue: Docker runner image missing
**Fix:** Build the runner image:
```powershell
docker build -t intelise-python-runner:3.12 -f backend/docker/Dockerfile.python-runner backend/docker
```

### Issue: Page refresh shows empty form
**Fix:** The page automatically restores the last run via URL parameter `?run_id=...` or `sessionStorage`. To view any previous run, append `?run_id=<RUN_ID>` to `http://127.0.0.1:5173/submissions/new`.
