# Ollama timeout recovery — 2026-10-22

The backend's configured 60-second provider deadline could expire during model
loading, queueing or CPU generation. The precise cause of the user's earlier
request cannot be reconstructed from the screenshot. The frontend additionally
classified the backend's known 504 response as an uncertain database write,
leaving an unnecessary recovery lock even though that route returns before
repository.create(). Unknown gateway timeouts/network failures remain uncertain.

## Changes

- Updated only the backend's ignored local .env extraction settings to
  C1_LLM_TIMEOUT_SECONDS=180 and C1_OLLAMA_MAX_TOKENS=768. The existing owner-only
  backup/update helper preserved other configuration. Model/provider/context are
  unchanged: Ollama, llama3.2:1b, 2048 context, temperature 0. The output allowance
  gives a full GPA quote list room beyond the earlier 256-token limit.
- Updated configuration examples and launcher output to display these nonsecret
  budgets. There are no startup downloads, automatic retries or provider fallback.
- Frontend recognizes only the exact application-level provider-timeout response
  as a known unsaved extraction. It retains uncertainty for other 504s and network
  failures. Prior successful runs remain displayed. Recovery controls open when
  retrieval is required, including a persisted warning from an older session.
- Gracefully restarted the identified Component 01 launcher after verifying zero
  queued/processing audio jobs. MongoDB was retained. Startup confirmed the new
  budgets, real database ping, backend storage readiness and frontend availability.
  No existing project was extracted/classified or otherwise modified by this fix.

## Actual live check

One real request used scripts/smoke_ollama.py with the synthetic GPA voice-fixture
transcript. No retries or database writes were made. Actual elapsed time:
**37.550 seconds**. Generation completed; schema and exact-source evidence checks
passed. The returned list contained **10 of 11** reference statements, omitting:
“Students shall be able to edit and delete an added course.”

This is a **completeness mismatch**, not a fully successful quality evaluation.
The script correctly exits nonzero for that mismatch despite the successful
request and source validation. No statement was invented to fill the gap.
The complete actual response, timing, bounded request metadata and known synthetic
source are in ollama-gpa-live-check.json. Source traceability does not prove
semantic correctness or completeness. No actual FR/NFR inference or ASR check
was performed in this live extraction test. A longer timeout does not guarantee
future performance or correct extraction.

## Reproduce

From the backend worktree's component-1/backend:

```sh
.venv/bin/python -m pytest tests/test_ollama_extraction.py tests/test_extractions.py -q
.venv/bin/python scripts/smoke_ollama.py --fixture gpa --timeout 180 --max-tokens 768
```

The live command makes exactly one local generation request. Its GPA fixture must
exist under the frontend public/samples/gpa-calculator-viva.local directory.
A quality mismatch is reported honestly with exit code 1. Existing default smoke
fixture behavior remains unchanged when --fixture is omitted.

From component-1/frontend:

```sh
npm test
npm run lint
npm run build
C1_BROWSER_PATH="$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-x64/chrome-headless-shell" node --test --test-name-pattern='project creation, extraction' tests/browser-workflow.test.mjs
```

105 affected backend tests and 118 frontend tests passed. Lint/build passed.
Tests distinguish confirmed backend timeouts, unknown gateway 504s and network
uncertainty; prior evidence/truncation/persistence checks remain in place.
No new dependencies, classifier changes, commits or pushes were made.

The mocked browser workflow passed, including the new confirmed-timeout case:
one POST only, explicit Run re-enabled, no uncertain-save warning, and the prior
successful requirement still displayed. Its asynchronous reviewer-focus assertion
now waits for the scheduled animation frame; no application behavior was weakened.
Final lint/build and whitespace checks passed.
