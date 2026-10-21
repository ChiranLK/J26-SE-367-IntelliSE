# PP1 demo runbook — LOCAL_SANDBOX_PREVIEW of the generated GPA application

Scope: local generation and a disposable Docker preview only. CI/CD is
`DEFERRED_AFTER_PP1`, production deployment is `OUT_OF_SCOPE_FOR_PP1`, real C4
readiness is `PENDING_INTEGRATION`. Nothing is deployed, pushed or sent to a cloud target.

Two separate applications are shown:

| Application | Where | Port |
| --- | --- | --- |
| Component 3 API (FastAPI) | `component-3/` | `127.0.0.1:8000` |
| Component 3 dashboard (Vite) | `component-3/dashboard/` | `127.0.0.1:5175` (see `vite.config.js`) |
| Generated GPA frontend | Docker container `<preview>-web` | dynamically allocated `127.0.0.1:<ui_port>` |
| Generated GPA API | Docker container `<preview>-api` | dynamically allocated `127.0.0.1:<api_port>` |
| Generated PostgreSQL | Docker container `<preview>-db` | not published (internal network) |

## 1. Prerequisites (once)

```powershell
Set-Location component-3
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env          # keep GENERATION_PROVIDER=openrouter
docker version                        # Docker Desktop must be running
docker pull postgres:16-alpine        # first build also downloads node:24-bookworm-slim and npm packages
Set-Location dashboard; npm install; Set-Location ..
```

OpenRouter is optional for the GPA demo (0 calls). To show a bounded call, set
`OPENROUTER_EXPERIMENT_ENABLED=true` and `OPENROUTER_API_KEY` in `.env` only.

## 2. Start Component 3 (two terminals, leave them open)

```powershell
# Terminal A - C3 API
Set-Location component-3
.\.venv\Scripts\python.exe -m uvicorn intelise_c3.main:app --host 127.0.0.1 --port 8000

# Terminal B - C3 dashboard
Set-Location component-3\dashboard
npm run dev
```

Open the dashboard at the URL Vite prints, then **Hybrid GPA Benchmark** in the
sidebar (`/dashboard/hybrid`).

## 3. Panel demonstration sequence (about 6 minutes)

1. **PP1 scope card** — point at `LOCAL_SANDBOX_PREVIEW`, `DEFERRED_AFTER_PP1`, `OUT_OF_SCOPE_FOR_PP1`, `PENDING_INTEGRATION`.
2. **Load GPA benchmark fixture** (or *Or upload C1 and C2 as separate files* and pick the two sample JSON files; they show as `PROVISIONAL_DEMO_INPUT`) — contract `ACCEPTED`, `VALIDATED_CONTRACT_INPUT`, C1/C2 evidence `SIMULATED_FIXTURE`, SRS-GPA-2.0 / UML-GPA-2.0.
3. **Knowledge Base & policy** — KB 1.0.0 + digest, 18 rules, policy `SLIIT-UG-GPA-SAMPLE` = `SAMPLE_RESEARCH_POLICY`; open *Policy sources*; tick the acceptance box (Generate stays disabled until you do).
4. **Generate GPA project** — `ACCEPTED`, 17 modules / 38 files, 16 rules, **0 OpenRouter calls**; expand *Selected rule IDs*, *RAG chunks*, *Artifact inventory*.
5. **Living traceability** — 5/5 requirements traced, 0 orphans; read one row: REQ-GPA-102 → GpaCalculationService → R-GPA-CALC-001 → be.service → calculateGpa → gpa_calculations → SEAM-GPA-SERVICE.
6. **Internal verification** — Design-to-Code PASS, Architecture PASS (static only).
7. **Start preview** — first build ≈ 2–3 min, then seconds (cached). Show status `RUNNING`, both URLs, container names, health (API UP, database UP, frontend UP), start time, `LOCAL_SANDBOX_PREVIEW_NOT_DEPLOYED`.
8. **Run known GPA check** — expected 3.42, observed 3.42.
9. **Open generated GPA app ↗** — a new tab on the generated frontend port. Enter IT1010/4/A, IT1020/3/B+, IT1030/2/C, IT1040/3/A- → **3.42**. Try credits 25 → field error; remove a row; show the policy banner and history (stored in PostgreSQL).
10. Switch back to the C3 tab — it is still running.
11. **Section 7** (optional): *Apply approved change (REQ-GPA-103 v2)* → impact set, 26 files `PRESERVED_UNTOUCHED`; *Inject simulated defect → simulated C4 report* → only `be.service` regenerated; *Gate check* buttons show BLOCKED / SIMULATED ALLOWED with `NONE_PERFORMED`.
12. **LLM backend mode** (optional, spends tokens, needs TeamSocLo + Docker): tick *Let TeamSocLo write the backend logic*, then Generate. The service and validation modules show origin `TEAMSOCLO`; open *Artifact inventory*.
12b. **Section 8, OpenRouter trial** (optional, spends tokens): the LLM writes the GPA service module; compare 8 benchmark cases against the template in the no-network sandbox. The artifact is untouched.
13. **Stop Preview** — status `STOPPED`; the generated app URL stops responding.

## 4. Same flow without the dashboard (API / script)

```powershell
# Whole acceptance scenario, isolated workspace, no Docker:
.\.venv\Scripts\python.exe scripts\hybrid_gpa_demo.py --isolated
# Including Docker build + preview + known calculation; leaves the preview running:
.\.venv\Scripts\python.exe scripts\hybrid_gpa_demo.py --preview
# Live preview sessions (recovered from Docker labels):
Invoke-RestMethod http://127.0.0.1:8000/api/v1/hybrid/preview
```

## 5. Cleanup

Preferred: **Stop Preview** in the dashboard, or
`POST /api/v1/hybrid/preview/stop` with `{"preview_id": "<id>"}`.

Documented manual cleanup of every hybrid preview container and network:

```powershell
docker ps -aq --filter "label=intelise.c3.hybrid-preview" | ForEach-Object { docker rm -f $_ }
docker network ls -q --filter "label=intelise.c3.hybrid-preview" | ForEach-Object { docker network rm $_ }
```

## 6. Verified results (2026-10-20, this machine)

| Check | Result |
| --- | --- |
| Backend tests (`python -m pytest`) | 616 passed, 4 skipped (opt-in Ollama / local-manifest tests) |
| Hybrid tests (`tests/test_hybrid_pipeline.py`) | 46 passed |
| Dashboard tests (`npx vitest run`) / build (`npx vite build`) | 81 passed / built |
| Dashboard flow in Chromium (load → accept → generate → start → open app → calculate) | passed; preview `ihp-2d907506b5`, frontend `http://127.0.0.1:10603`, API `http://127.0.0.1:10602` |
| Health | API `{"status":"UP","database":"UP"}`, frontend HTTP 200, all three containers Docker-`healthy` |
| Known GPA calculation | expected 3.42, observed 3.42 (API and browser UI) |
| Isolation | db not published, `--internal` db network, uid 1000/70, read-only app roots, `cap-drop ALL`, 0 mounts |
| C3 availability while app open | API HTTP 200, dashboard reloads |
| Stop Preview | containers and networks removed; port closed |
| Determinism | two runs → identical artifact digest |
| Real OpenRouter (custom-extension fixture) | 1 call, 559 prompt + 320 completion tokens, 4.7 s, accepted; second run cache hit, 0 tokens |

## 7. Panel checklist (claim → evidence)

| Claim | Implementation | Verification command | Evidence | Limitation |
| --- | --- | --- | --- | --- |
| Only approved, version-matched C1/C2 pass | `hybrid/input_contracts.py`, `contracts/hybrid.py` | `pytest tests/test_hybrid_pipeline.py -k contract` | rejection codes per case | Refs are opaque; C3 cannot authenticate C1/C2 |
| Human override is explicit and version-bound | same | `-k human_override` | `OVERRIDE_VERSION_MISMATCH`, FAILED never overridable | Override scope limited to C2 NEEDS_HUMAN_REVIEW |
| Provisional upload is labelled | `classify_legacy_package`, gate | `-k provisional` | `PROVISIONAL_DEMO_INPUT`; gate blocks it | — |
| KB is versioned, validated, SLIIT policy sourced | `knowledge-base/`, `hybrid/knowledge_base.py` | `-k kb_` | KB digest, 12-grade table, provenance | SAMPLE_RESEARCH_POLICY, not institution-approved |
| Policy must be explicitly accepted | `HybridPipeline._check_policy` | `-k sample_policy` | `POLICY_ACCEPTANCE_REQUIRED/MISMATCH/NOT_ACKNOWLEDGED` | — |
| Deterministic rules; unsupported/ambiguous never fabricated | `generation-rules/`, `hybrid/rule_engine.py` | `-k rule or unsupported` | `UNSUPPORTED`, `AMBIGUOUS→REVIEW_REQUIRED` | Rules cover the GPA pack only |
| Known patterns cost 0 tokens; output is deterministic | `hybrid/gpa_templates.py` | `scripts/hybrid_gpa_demo.py --isolated` | step 9 (0 calls), step 13 (same digest) | One stack implemented |
| RAG is filtered, bounded, recorded, non-authoritative | `rag/best_practices.py` (extended) | `-k rag` | chunk ids/versions/scores in manifest | Small reviewed corpus (19 cards) |
| OpenRouter is bounded, cached, ledgered, 2 attempts max | `hybrid/llm_gateway.py` | `-k gateway or minimized` | ledger entries, cache hit, HUMAN_REVIEW_REQUIRED | Token estimate under-counts real usage (368 est. vs 559 actual); free models may drift or fail |
| Living traceability with no accepted orphans | `hybrid/living_trace.py` | `-k traceability or orphan` | 5/5 traced, 0 orphans, preserved/superseded/expired counts | Structural coverage, not test coverage |
| Design-to-Code and architecture verified | `hybrid/verification.py` | `-k design_to_code or architecture` | MISSING_METHOD, TYPE_MISMATCH, forbidden edges detected | Static analysis only |
| Scoped regeneration preserves unchanged hashes | `HybridPipeline.requirement_change`, `c4_defect` | `-k requirement_change or c4_defect` | 26 PRESERVED_UNTOUCHED; drift → IMPACT_SET_INCOMPLETE | Added/removed requirements need full regeneration |
| Stale C4 reports rejected | `c4_defect` | `-k c4_defect` | `STALE_DEFECT_REPORT`, `PATCH_OUTSIDE_IMPACT_SET` | C4 inputs are SIMULATED |
| Gate needs exact-artifact readiness | `deployment_gate` (stub) | `-k deployment_gate` | BLOCKED reasons; ALLOWED only with exact SIMULATED signal | No deployment performed (PP1) |
| Generated app runs isolated in Docker with Postgres | `hybrid/preview.py` | dashboard *Start preview* or `--preview` | URLs after health; `docker inspect` flags | Needs Docker Desktop; first build needs network |
| Known GPA result | generated `gpaCalculationService.js` | *Run known GPA check* | 3.42 observed | C3 smoke check, not C4 evidence |
