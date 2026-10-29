# Hybrid rule-governed generation (Component 3)

Status: implemented for the GPA domain pack on React + Node.js + PostgreSQL.
Execution scope for PP1: **LOCAL_SANDBOX_PREVIEW** only.

| PP1 boundary | Status |
| --- | --- |
| Current execution | `LOCAL_SANDBOX_PREVIEW` (disposable Docker, loopback ports) |
| CI/CD implementation | `DEFERRED_AFTER_PP1` |
| Production deployment | `OUT_OF_SCOPE_FOR_PP1` |
| Real C4 readiness integration | `PENDING_INTEGRATION` (contracts + gate stub only) |

## 1. Pipeline

```
C1 package (2.0, CLIENT_APPROVED)  +  C2 release (2.0, VALIDATED)
        │  contracts/hybrid.py, hybrid/input_contracts.py
        ▼  (reuses InputValidationService + DesignUnderstandingService)
Normalized GenerationContext + DesignContext
        ▼
Knowledge Base facts (knowledge-base/)  +  Rule engine (generation-rules/)
        ▼  bounded stack selection: existing StackSelectionService scores 4 stacks;
        ▼  rule R-STACK-001 accepts only a stack whose KB entry is IMPLEMENTED
Deterministic templates (hybrid/gpa_templates.py, 17 modules, 0 LLM tokens)
   + best-practice RAG (rules/ cards, existing RAG store, filtered, audit only)
   + bounded OpenRouter (hybrid/llm_gateway.py) ONLY for rule-UNSUPPORTED custom service classes, opt-in
        ▼
frontend/ backend/ database/ openapi/ test-seams/ deployment/ README.md
        ▼
Design-to-Code + architecture verification (hybrid/verification.py; report only)
        ▼
Living traceability graph version (hybrid/living_trace.py; same SQLite file, own table)
        ▼
Immutable run directory: generated-workspaces/hybrid/<workspace>/<run_id>/
        ▼
LOCAL_SANDBOX_PREVIEW (hybrid/preview.py)  ·  C4 defect intake / scoped regeneration  ·  gate stub
```

Code: `src/intelise_c3/hybrid/` and `src/intelise_c3/api/routes/hybrid.py` (`/api/v1/hybrid/*`).
Dashboard: `dashboard/src/pages/HybridPipeline.jsx` (`/dashboard/hybrid`).

## 2. Research boundaries

| Owner | Owns | What C3 does with it |
| --- | --- | --- |
| C1 | Requirements, FR/NFR, quality, stable IDs, client approval | Validates `CLIENT_APPROVED` + version + stable IDs; never rewrites text. Structured `constraints` are a **proposed** C1 field pending C1 confirmation. |
| C2 | UML, semantic/syntax validation, UI spec, release status | Requires `VALIDATED`, matching SRS version, anchors to declared classes. `NEEDS_HUMAN_REVIEW` passes only with an explicit, version-bound `human_override`; `FAILED` never passes. |
| C3 | Contracts, stack, generation, traceability, verification, impact, scoped regeneration, preview, audit | This document. |
| C4 | Independent tests, defect truth, semantic preservation, convergence, readiness | C3 publishes **test seams** and consumes C4 *contracts* (`C4DefectFeedback`, `C4ReadinessSignal`). Every C4 document in this repo is a `SIMULATED_FIXTURE`. |

The legacy 1.0 plain-text / PlantUML upload adapter remains for the earlier
pages and is classified `PROVISIONAL_DEMO_INPUT`; the gate always blocks that
classification.

## 3. Knowledge Base vs Rule Base vs RAG

| Layer | Location | Holds | Authority |
| --- | --- | --- | --- |
| Knowledge Base | `knowledge-base/` (manifest + 16 files, 23 items) | Facts: type maps, layering, API/DB conventions, stack status, **GPA policy**, formula, rounding, edge cases | Rank 3 (below C1, C2) |
| Rule Base | `generation-rules/` (15 files, 18 rules) | Deterministic decisions: conditions → modules, required KB items, validation, trace behaviour, failure mode | Rank 4 |
| RAG | `rules/` best-practice cards via the existing `BestPracticeStore` | Reviewed coding guidance with version/provenance/digest | Rank 5 — guidance only |
| LLM | OpenRouter | Suggestions for rule-unsupported custom modules | Rank 6 — untrusted until validated |

* Each KB item has an `item_id` (becomes a `KNOWLEDGE_ITEM` trace node). The KB
  digest is computed over parsed JSON (CRLF-safe) and binds manifests and the LLM cache.
* Rules: within one target and category the highest priority wins; equal top
  priority between different rules → `AMBIGUOUS` → `REVIEW_REQUIRED`; no rule →
  `UNSUPPORTED` (nothing fabricated). Outcomes: `MATCHED`, `UNSUPPORTED`,
  `AMBIGUOUS`, `REVIEW_REQUIRED`, `FAILED`.
* RAG was **extended, not replaced**: optional card metadata
  (`version`, `artifact_types`, `modules`, `task_types`, `provenance`, `document_id`),
  a new `search(RetrievalQuery)` with stack/layer/artifact-type/module/task filters,
  top-k clamped to 3–5 and a 2,000-token context budget. Cards in categories such as
  `grading-policy`, `requirement-approval` or `secret` are rejected at load time.
  Retrieved chunk IDs, versions, scores and digests are written to the manifest.

### GPA policy (SLIIT)

`knowledge-base/domains/gpa/grading-policy.json` holds a transcription of the
publicly described SLIIT 4.0 scale (A+/A 4.0, A- 3.7, B+ 3.3, B 3.0, B- 2.7,
C+ 2.3, C 2.0, C- 1.7, D+ 1.3, D 1.0, E 0.0) with sources. It is labelled
**`SAMPLE_RESEARCH_POLICY`**: it was not supplied or approved by SLIIT, the client
or C1. Generation is refused (`POLICY_ACCEPTANCE_REQUIRED`) unless the request
carries an acceptance bound to the policy id, version and digest that
acknowledges the sample status. Rounding (2 dp, HALF_UP) and pass/fail exclusion
are recorded as `RESEARCH_ASSUMPTION`; unknown grades and repeated modules are
`REVIEW_REQUIRED` (HTTP 422, no guessed value); zero-credit counted modules are
rejected. WGPA year weights are recorded as `RECORDED_NOT_GENERATED` because no
approved requirement asks for them.

## 4. OpenRouter boundary and token-saving strategy

* Provider: OpenRouter only (`GENERATION_PROVIDER=openrouter`,
  `OPENROUTER_EXPERIMENT_ENABLED=true`, key in `.env`). Local Ollama is never
  probed or used as a fallback; if OpenRouter is unavailable the module becomes
  `HUMAN_REVIEW_REQUIRED`.
* Known patterns (all 17 GPA modules) are rendered by templates: **0 tokens**.
* Rule `R-LLM-BOUNDED-001` allows one bounded call per *module* for an
  unsupported custom service class, only when `allow_llm_for_unsupported=true`.
* Prompt contents: that module's requirement slice (id, version, statement), its
  UML class only, stack, rule IDs, interface contract, ≤5 RAG chunks, and on retry
  the previous output + exact validator findings. No other requirements, UML or files.
* Budgets: `HYBRID_LLM_MAX_INPUT_TOKENS` (default 3000, estimated; over-budget
  prompts are not sent), `HYBRID_LLM_MAX_OUTPUT_TOKENS` (4096; reasoning models spend output tokens on hidden reasoning, 1500 truncated a full service module), max 2 attempts.
* Cache key: requirement ids+versions, UML version, stack, module, KB digest,
  rule-set digest, prompt version, provider/model, retrieved-context digest
  (+ repair inputs). Accepted outputs are cached atomically in `runtime/llm-cache/`.
* Ledger per attempt: provider, requested/response model, upstream provider,
  prompt/completion/total tokens, latency, attempt, cache hit, validation
  result, accepted, error code. Cost is `null` (not returned by the client).
* Output validation: strict JSON `{path, content}`, existing JS lexical safety
  policy, exact class/method interface, no imports. Accepted model modules stay
  `REVIEW_REQUIRED_BEFORE_WIRING`.
* Provider errors (`OPENROUTER_RATE_LIMITED`, timeout, model invalid,
  authentication) stop immediately and are recorded; empty/truncated/malformed
  responses consume the second attempt. Free models are not assumed stable.

### LLM backend logic mode (TeamSocLo, explicit opt-in)

`POST /api/v1/hybrid/runs` with `"llm_backend_logic": true` (dashboard: *Let TeamSocLo write the backend logic*).
The rule engine still decides what is built; templates still produce everything else (frontend, SQL, OpenAPI,
Docker, policy table, controller, routes, repository). Only `be.service` and `be.validation` are written by
**TeamSocLo** (`claude-haiku-4-5`), one bounded call each, under governance rule `R-LLM-BACKEND-001`.

* Prompt per module: its own requirement slice, its own UML class, stack, rule IDs, injected-dependency contract,
  the Knowledge Base facts (formula, rounding, edge-case behaviour, approved C1 limits as data) and up to 5 RAG
  best-practice chunks (recorded with `applied_to_prompt: true`). The grade table is never written by the model:
  it arrives through the injected `gradingPolicy`.
* Acceptance gate per module: JS lexical safety policy, interface check, no imports, **then the shared
  benchmark cases in the Docker sandbox** (`gpa-backend-bench-2`: 9 service cases incl. a repository shape check mirroring the PostgreSQL columns, 13 validation cases whose limits
  come from the approved C1 constraints). Failing cases are sent back, verbatim, in attempt 2. Maximum two attempts.
* On failure **generation stops**: no template fallback, no artifact, nothing in the trace graph. Every attempt,
  the ledger and the rejected outputs are preserved in `generated-workspaces/hybrid/<workspace>/_human-review/`.
  Docker or TeamSocLo being unavailable stops *before* any model call.
* The generated project's `backend/test/gpa.smoke.test.js` runs the same benchmark cases again during the Docker
  preview build, against the files that actually ship.
* Scoped regeneration never silently replaces model-written modules (`LLM_MODULE_IMPACTED_REQUIRES_REVIEW`,
  `MODEL_MODULE_REPAIR_REQUIRES_REVIEW`).
* Limits: the benchmark is C3-authored smoke checking, not independent C4 testing; passing it does not prove
  equivalence with the template (see the OpenRouter trial for an observed difference). TeamSocLo is an external
  gateway: the module's requirement/UML/KB slice leaves the machine. The model name is the gateway's alias.

### OpenRouter trial (LLM vs template) and separate C1/C2 upload

* **Upload:** the dashboard accepts the C1 and C2 documents as two JSON files (`tests/fixtures/hybrid/gpa_c1_package_2.0.json`, `gpa_c2_package_2.0.json`). They are combined client-side, validated by the backend, and classed `PROVISIONAL_DEMO_INPUT` unless both declare `UPSTREAM_COMPONENT_OUTPUT` (a hand-uploaded file cannot prove its origin).
* **Trial** (`POST /api/v1/hybrid/llm-trial`, `hybrid/llm_trial.py`): one bounded OpenRouter call writes the `GpaCalculationService` module that a template normally produces. The context is the requirement linked to that module, its UML class, KB formula/rounding/edge-case facts, injected-dependency contract and <=5 RAG chunks. The module and the template module then run the same 8 benchmark cases inside a Docker sandbox (no network, read-only root, tmpfs, no mounts, uid 1000, caps dropped; source passed on stdin). The result is recorded in `evidence/llm-trials.jsonl` and is `LLM_TRIAL_NOT_PART_OF_ARTIFACT`: the run, manifest, trace graph and artifact digest never change.
* **Limits:** passing 8 cases is not equivalence. Observed difference: the LLM version validates grades only on GPA-counted modules and omits non-counted modules from its result; the template validates all grades. Reasoning models can spend the whole output budget on hidden reasoning (`OPENROUTER_OUTPUT_TRUNCATED`); `HYBRID_LLM_REASONING_EFFORT=low` is the default for this reason.

## 5. Living traceability schema

Node types: `REQUIREMENT, UML_ELEMENT, RULE, KNOWLEDGE_ITEM, MODULE, CODE_FILE,
CODE_SYMBOL, API_OPERATION, DATABASE_ENTITY, TEST_SEAM, C4_TEST, DEFECT_REPORT,
PATCH_EVENT, READINESS_SIGNAL, DEPLOYMENT_EVENT, ARTIFACT`.

Relations (enforced endpoint types): `DESIGNED_BY, IMPLEMENTED_BY, GENERATED_AS,
PRODUCED, CONSTRAINED, CONTAINS, DEFINES, EXPOSED_BY, STORED_BY, VERIFIED_THROUGH,
TARGETS, PART_OF, EXERCISES, IMPACTS, REGENERATED, AUTHORIZES, DEPLOYED`.

* Every `CODE_FILE` carries requirement IDs, SRS and UML versions, rule IDs,
  template reference, SHA-256 and the run that created it. A file without a
  `PRODUCED` rule link, a containing module, or an originating requirement is an
  orphan; a run with orphans is `REJECTED_ORPHAN_ARTIFACTS` and not accepted.
* `IMPLEMENTED_BY` links are `DIRECT` (semantic) or `HOSTING_CLOSURE` (scaffold
  such as `package.json`, Dockerfiles). Impact analysis uses `DIRECT` only.
* Link identity includes the target digest / requirement version, so on
  regeneration unchanged links are **preserved**, replaced links become
  **SUPERSEDED** and vanished links **EXPIRED**; earlier versions stay in the
  append-only `hybrid_trace_versions` table and earlier run directories are untouched.

## 6. Verification agents

* Design-to-Code (`V-D2C-*`): missing class, missing method, missing field,
  type mismatch (KB type map), composition/injection relationships, missing
  endpoint (OpenAPI + route), missing DB entity/column, unsupported extra elements.
* Architecture (`V-ARCH-NODE-LAYERING`, from `KB-ARCH-NODE-LAYERED`): import
  graph per layer; forbids Route→Repository/DB, Controller→Repository/DB,
  Frontend→DB and SQL outside repositories.
* Each finding: rule ID, expected, observed, evidence path, module, severity,
  confidence, artifact digest. Verifiers have no patch authority; a FAIL rejects
  the run and lists regeneration triggers for the central workflow.

## 7. Scoped regeneration and C4 contracts

* **Approved change** (`POST /hybrid/regenerations/requirement-change`): base run
  must be the current artifact and untampered; changed requirements must carry a
  higher version and a new SRS/UML version. Impact = modules with `DIRECT`
  links to changed requirements (+ approved dependency modules). All modules are
  re-rendered in memory; any module **outside** the impact set whose bytes would
  change aborts with `IMPACT_SET_INCOMPLETE` (no silent widening). Files outside
  the impact set are copied byte-for-byte and keep their original run ID.
* **C4 defect** (`POST /hybrid/c4/defects`, `C4DefectFeedback` 2.0): rejected when
  the artifact digest is not the run's, the run is not current
  (`STALE_DEFECT_REPORT`), the module digest is stale, the module/test seam is
  unknown, or the proposed scope leaves the traced impact set without an
  approved dependency reason. A defect in a template module that re-renders to
  identical bytes returns `REVIEW_REQUIRED` (`TEMPLATE_DEFECT_REQUIRES_RULE_OR_KB_CHANGE`).
* Every regeneration returns a C4 handoff with `retest_status: PENDING`.
* **Gate stub** (`POST /hybrid/deployment-gate`, `C4ReadinessSignal` 2.0): ALLOWED
  only for an `ACCEPTED`, current, untampered, `VALIDATED_CONTRACT_INPUT` run with
  a READY, unrevoked, PRESERVED, CONVERGED signal citing the exact artifact and
  every module digest, issued after generation. It performs **no deployment**.

## 8. Docker security model (LOCAL_SANDBOX_PREVIEW)

`hybrid/preview.py` per preview: images built from a copy of the verified
project files (no bind mounts); networks `<id>-dbnet` (`--internal`) and
`<id>-edge`; containers `<id>-db` (postgres:16-alpine, uid 70, tmpfs, internal
network only, never published), `<id>-api` (uid 1000, read-only root,
`127.0.0.1:<api_port>`), `<id>-web` (uid 1000, read-only, `127.0.0.1:<ui_port>`).
All use `--cap-drop ALL`, `no-new-privileges`, pid/memory/cpu limits, no Docker
socket, no privileged mode. Ports are allocated dynamically and never equal
8000/5173–5175/3001/8080/5432. URLs are returned only after `/api/health`
reports `database: UP` and the frontend serves its root. The database password
is random per preview and not recorded. Failures remove the containers and
write logs to `evidence/preview-events.jsonl`. State is recovered from container
labels, so Stop works after a C3 restart.

## 9. Test layers (kept separate)

1. **C3 automated tests**: `tests/test_hybrid_pipeline.py`, `dashboard/test/hybrid.test.jsx`.
2. **Generated-app smoke checks**: `backend/test/gpa.smoke.test.js`, run by `npm test`
   inside the Docker build, plus `POST /hybrid/preview/{id}/gpa-check`.
3. **Test seams for C4**: `test-seams/c4-test-seams.json` (C3 publishes; C4 tests).
4. **Simulated C4 fixtures**: `/hybrid/runs/{id}/simulated-c4-defect|readiness` (`SIMULATED_FIXTURE`).
5. **Real independent C4 evidence**: none exists yet.

## 10. Known limitations

* One domain pack (GPA) and one implemented stack (React + Node + PostgreSQL).
* The SLIIT policy is a public-source transcription, not institution-approved.
* Upstream references are opaque; C3 does not authenticate C1/C2/C4 documents.
* Verification is static; the smoke checks are C3-owned and narrow.
* Requirement-change regeneration handles changes to existing requirements/classes;
  added or removed requirements/classes need full regeneration.
* Model-generated custom modules are not wired into routes automatically.
* Preview needs Docker Desktop and network access for npm/postgres images on first build.
