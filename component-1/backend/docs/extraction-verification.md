# Component 01 extraction verification — 2026-10-14

See the follow-up section below for the current compact Ollama request, live
response and verification results. The initial sections retain historical evidence.

Branch inspected: `component-1-backend`. Initial status contained only untracked
`.DS_Store`, `component-1/.DS_Store` and `component-3/.DS_Store`; these remain untouched.
Root and backend README instructions were read. No applicable AGENTS.md was found.
All changes are within `component-1/backend`. No frontend or other component was
modified, and no commit, push, merge or pull request was made.

## Finding and changes

The observed 14-candidate output was supplied by the user; the old model behavior
was not reproduced. Repository inspection found an Anthropic adapter and no Ollama
adapter. Existing evidence validation checked quotes and model-supplied offsets,
but permitted arbitrary rewritten requirement text alongside real evidence. That
allowed a fabricated feature paired with a real source quote to pass validation.
The atomic-splitting prompt also permitted rewritten candidate wording.

Added an explicitly selected Ollama adapter using JSON Schema, temperature zero,
configurable URL/model/context/output/deadline, bounded responses and completion
checks. Defaults are localhost:11434 and llama3.2:1b. Existing Anthropic support
remains available and stays the default provider for compatibility. No adapter
pulls models, retries generation or falls back to another provider.

The versioned prompt extracts only explicit requirements, treats the discussion
as untrusted source data, preserves permissions/negation/conditions/numeric limits,
and excludes meeting arrangements. Provider schemas now request quotes without
offsets; backend code computes exact Unicode spans. New runs require candidate
text to equal a supporting quote, and reject duplicates, blanks, malformed output,
incomplete generation and unsupported evidence before any database insert.

The persisted API shape is preserved with the additive `provider` field. Old runs
without it read as Anthropic and remain unchanged. Projects retain original text,
runs remain append-only, all candidates are unreviewed, and failed extraction leaves
previous successful runs available. Health does not contact Ollama or MongoDB.

## Files changed

- `.env.example`: explicit provider and Ollama configuration examples.
- `README.md`: setup, wire/output policy, error behavior, reproducible checks and limitations.
- `src/intelise_c1/core/config.py`: provider, Ollama settings and validation.
- `src/intelise_c1/main.py`: explicit provider factory selection.
- `src/intelise_c1/services/provider.py`: Ollama adapter and quote-only Anthropic output.
- `src/intelise_c1/services/extraction.py`: prompt v2, backend offsets and exact-source validation.
- `src/intelise_c1/api/extraction_schemas.py`: quote-only wire schema and provider metadata.
- `src/intelise_c1/api/extractions.py`: provider metadata and actionable sanitized errors.
- `tests/test_extractions.py`: existing coverage adapted to the stricter policy.
- `tests/test_ollama_extraction.py`: mocked adapter and regression/failure preservation coverage.
- `scripts/smoke_ollama.py`: one live synthetic extraction, actual response and elapsed-time reporting.
- `docs/extraction-verification.md`: this report.

MongoDB repository code was inspected and reused without modification. It already
validates before append-only majority inserts and preserves previous runs.

## Automated verification

- Extraction suites: **102 passed**.
- Entire Component 01 backend: **186 passed, 6 skipped**. All six skips are real
  MongoDB integration tests because `TEST_MONGODB_URI` was not set.
- `pip check`: **No broken requirements found**.
- `git diff --check`: passed.
- Existing Starlette/httpx deprecation warning remains; dependencies were not changed.

Provider responses in automated tests are mocked. The three expected candidates
and excluded Friday meeting verify the extraction contract with a fixture; they
are not evidence that llama3.2:1b actually returned those candidates. Unsupported
login/reminder/OS/history additions fail, including fabricated text paired with
real quotes. Tests also verify permission/negation preservation, empty output,
duplicates, Unicode/CRLF offsets, invalid JSON/schema, unavailable/missing models,
timeouts, truncation, single-request behavior and successful-run preservation.
Database failures are tested using collection doubles; real persistence was not
verified during this change.

## Actual live smoke test

The initial sandboxed attempt could not reach Ollama (0.253 seconds, no response).
The same smoke command was then run with approved access to the local server.
It made one generation request using the supplied synthetic discussion, configured
`llama3.2:1b`, context 8192, output limit 8192, temperature 0 and a 60-second deadline.

Result: **ProviderTimeout after 60.071 seconds**. No response body/model candidates
were returned (`actual_response: null`). No generation retry, model download,
provider fallback or database write occurred. Actual faithful extraction performance
therefore remains unverified. The timeout does not establish whether model loading,
generation speed or server behavior caused the delay.

## Reproduce

From the repository root:

```sh
cd component-1/backend
.venv/bin/python -m pytest tests/test_extractions.py tests/test_ollama_extraction.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
C1_OLLAMA_BASE_URL=http://localhost:11434 C1_OLLAMA_MODEL=llama3.2:1b \
  .venv/bin/python scripts/smoke_ollama.py
```

From the repository root, also run `git diff --check`. The smoke script ignores
`.env`, uses environment overrides, prints the actual response and elapsed time,
and exits nonzero on unavailable/invalid/quality-mismatched output. Ensure the
server is running and the model is already installed. It never changes your database.
Optional real persistence verification requires a separately provisioned disposable
MongoDB test server:

```sh
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -m integration -q
```

## Remaining limitations

Exact quotes establish textual traceability, not semantic correctness, completeness,
relevance or preservation of context across utterances. A model could omit a
requirement, extract a meeting sentence, or select only part of a restriction while
still satisfying the substring checks. These need human review and evaluation on
reviewed discussions. Prompt instructions reduce these risks without proving they
are eliminated. Rewritten splits/paraphrases are deliberately rejected; compound
source statements can remain together. Repeated quotes resolve to their first
occurrence, which may not be the occurrence the model intended. All candidates
remain explicitly unreviewed.

An ambiguous database/network write failure can still reach MongoDB despite an API
503, as in the existing implementation; there is no retry or idempotency token.

## Follow-up: compact Ollama diagnostic comparison — 2026-10-14

The earlier sections document the initial implementation. This follow-up supersedes
its Ollama prompt/schema/defaults and current verification counts; the previous live
60.071-second timeout remains historical evidence.

The user supplied a separate short direct request that completed in 9.63 seconds
with llama3.2:1b, temperature zero, context 2048, output cap 256 and a quotes array.
Its three requirement quotes were accompanied by `We will meet onFriday.`. That
malformed extra quote is not a source substring and must fail the whole run. The
exact direct-request prompt and timing envelope were not supplied, so this is
user-provided diagnostic evidence rather than an independently repeated benchmark.

### Request comparison

| Property | Initial backend request | Current compact backend request |
| --- | --- | --- |
| System prompt length | 1,292 characters | 530 characters |
| Serialized schema size (Python `json.dumps`, UTF-8) | 1,442 bytes | 326 bytes |
| Wire response | candidates with repeated requirement text/evidence, actor/action | quotes array only |
| Context default | 8,192 tokens | 2,048 tokens |
| Output cap default | 8,192 tokens (`C1_LLM_MAX_TOKENS`) | 256 tokens (`C1_OLLAMA_MAX_TOKENS`) |
| Temperature | 0 | 0 |
| Whole-operation timeout | 60 seconds | 60 seconds |
| Completion required | `done: true`, `done_reason: "stop"` | unchanged |

The simpler prompt/schema and smaller context/output limits are consistent with
lower generation work. However, an output cap is a ceiling, not the number of
tokens necessarily generated. Context size can also affect model loading/memory.
The old run returned no timings or token counts; these changes were made together,
so this comparison cannot establish which variable caused the earlier timeout.
Model warm state and server load are also uncontrolled. This is not a latency benchmark.

The Ollama-specific prompt version is now `c1-ollama-quotes-v3`. It explicitly
excludes meetings, greetings and conversational logistics and requests exact,
complete source quotes preserving restrictions and numeric limits. Backend code
maps quotes into the existing candidate API: text and evidence retain the quote,
actor/action are null, offsets and IDs are generated locally, review status remains
unreviewed, and source hash/timestamp/provider/model metadata are unchanged.
The Anthropic adapter retains its existing wire schema, prompt version and token
setting. No public endpoint or candidate response fields were removed.

Modified in this follow-up: extraction schemas/service/provider, configuration,
extraction route (provider-specific prompt metadata), Ollama tests, smoke script,
`.env.example`, README and this report. Other existing work was preserved.

### One actual live compact extraction

One real generation request was made through the backend Ollama adapter; no database
was used and no retry was attempted. Client elapsed time: **11.155 seconds**.
Actual response:

```json
{
  "model": "llama3.2:1b",
  "created_at": "2026-10-14T14:12:19.735349Z",
  "message": {
    "role": "assistant",
    "content": "{\"quotes\": [\"Customers can book appointments.\", \"Only administrators can delete accounts.\", \"Search results must appear within two seconds.\", \"We will meet on Friday.\"]}"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 10838158010,
  "load_duration": 5138481039,
  "prompt_eval_count": 152,
  "prompt_eval_cached_count": 0,
  "prompt_eval_duration": 3514552000,
  "eval_count": 34,
  "eval_duration": 2145681999
}
```

Server-reported duration: 10.838 seconds, including 5.138 seconds model loading,
3.515 seconds prompt evaluation and 2.146 seconds generation. The schema measured
326 bytes, prompt 530 characters, options temperature 0/context 2048/output 256,
with a 60-second timeout. The source is the original smoke fixture, including
`Only administrators can delete\naccounts.` and its unchanged line breaks.

**Source validation failed:** the model replaced the newline between `delete` and
`accounts` with a space. `Only administrators can delete accounts.` is therefore
not an exact substring. The complete run failed with `InvalidExtraction` and
`Evidence quote is absent from the original source.` No quote was repaired or saved.

**Relevance evaluation failed independently:** the model also returned the exact
`We will meet on Friday.` despite the prompt exclusion. That quote is traceable
but irrelevant. The three intended software statements are represented in the
response, but one violates the exact-source policy; this is not a successful
faithful extraction or an accuracy result.

### Regression checks and limitations

The malformed `We will meet onFriday.` is now a regression test: a previously saved
successful run remains available and no partial replacement is inserted. A separate
exact-Friday test deliberately shows that substring validation accepts its evidence
and can persist it as **unreviewed**; the synthetic fixture's relevance/completeness
comparison rejects the extra item. There is no claim of a general semantic validator
and no hardcoded meeting filter in production. The live newline normalization is
also covered as a rejected, unrepaired quote. Existing completion, duplicate, schema,
timeout, no-retry and database failure preservation coverage remains in place.

Affected suites: **105 tests**, all passed as part of the full backend run.
Full backend: **189 passed, 6 skipped**, with the existing Starlette/httpx warning.
The six skips require `TEST_MONGODB_URI`; no live persistence claim is made.
`git diff --check` passed. Automated responses remain mocked and separate from the
actual response above.

The new 2048/256 defaults target short discussions. Longer sources need deliberate
context/output configuration. The existing character limit does not prove token
fit, and a completed generation cannot prove input context was retained or every
requirement extracted. Output truncation still fails completion checks. Exact
quotes establish traceability, not relevance, completeness or adequate contextual
coverage. Preserve these distinctions in research evaluation and human review.

Reproduce from the repository root:

```sh
cd component-1/backend
.venv/bin/python -m pytest tests/test_extractions.py tests/test_ollama_extraction.py -q
.venv/bin/python -m pytest -q
C1_OLLAMA_BASE_URL=http://localhost:11434 C1_OLLAMA_MODEL=llama3.2:1b \
  C1_OLLAMA_CONTEXT_LENGTH=2048 C1_OLLAMA_MAX_TOKENS=256 C1_LLM_TIMEOUT_SECONDS=60 \
  .venv/bin/python scripts/smoke_ollama.py
```

Run `git diff --check` from the repository root. The smoke script prints the actual
response/options/timing, distinguishes source acceptance from fixture evaluation,
never writes a run and never retries. Future live results may differ; the failed
live request above was not retried during this investigation.
