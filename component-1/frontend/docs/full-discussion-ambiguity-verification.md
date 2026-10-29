# Full-discussion wording review after an incomplete extraction

## Confirmed observation

A read-only API check of the user's test project confirmed that all three test
sentences were saved (150 characters), but its existing Ollama `llama3.2:1b` run
with prompt `c1-ollama-quotes-v3` contained only the final, measurable timing
requirement. The “quickly” and “user-friendly” statements were absent. Direct
local rule checks found those two phrases; the returned requirement had no rule
matches. No saved project or run was changed during diagnosis.

The original UI checked wording only in returned candidates. That meant extraction
omissions could hide potential wording issues from the ambiguity review.

## Change and limits

Step 2 now scans the full saved `discussion_text` without a provider call, before
extraction. It shows a distinct **Unclear wording in saved discussion** panel,
opened initially when flags exist. It states explicitly that flags are source
wording hints, not extracted requirements or FR/NFR predictions. The original
per-requirement hints remain under table Details. Source positions are displayed
as end-exclusive Unicode character offsets within the saved discussion.

No candidates are fabricated, inferred, automatically restored or written to the
database. Existing extraction, classifier results and source evidence remain
unchanged. The existing one-candidate run remains one candidate. This feature
exposes wording clues despite omissions; it does not detect all omitted requirements,
verify software relevance, or repair/prove extraction completeness. English phrase
rules may flag ordinary conversation, or wording already explained by other context.
They can also miss unclear references, missing conditions and domain ambiguity.

The scanner accepts explicit `discussion_text` or `requirement_text` scopes. A
single UTF-16-to-Unicode offset map replaces repeated prefix conversions, keeping
long-discussion processing bounded by text/rule matches. Only the first 20 flags
are rendered in a panel to avoid an excessively large page; the total is shown
and all flags remain in the export.

JSON exports add `source_ambiguity_analysis` with `offset_scope: "discussion_text"`.
Existing requirement analyses still use `requirement_text`. Text exports include
UNCLEAR WORDING IN SAVED DISCUSSION separately from extracted requirements. No
backend/API/provider/model/dependency changes were made; no MongoDB records were
modified or new model requests triggered for the user's project.

## How to retry the user's check

Refresh the saved project, open Step 2 and inspect **Unclear wording in saved
discussion · 2 potential flags**. It should list “quickly” and “user-friendly”,
with timing/workload and measurable usability questions. A new extraction request
is not needed to view these source hints. The existing requirement table will
still show the actual saved single timing requirement. Exporting keeps that one
requirement and includes both source-wording hints separately.

For the viva, distinguish source wording review, extraction completeness, model
prediction and human label review. The unchanged baseline's within-corpus evaluation
limitations remain; this is not a new model or accuracy measurement.

## Reproduce verification

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

The regression case uses all three test sentences and deliberately returns only
the final sentence from a mocked extractor. It checks that the full-discussion
analysis still has two flags, the requirement analysis has none, and exactly one
actual candidate is exported. Other tests cover analysis without extraction,
conversation false-positive scope, exact Unicode offsets in long discussions,
source preservation and unknown-scope rejection. Chrome also checks visibility
before extraction, persistence of source hints with a partial response, separate
export scopes and reopening. Its workflow HTTP API is mocked; the separate local
classifier test uses the existing actual artifact. Live Azure audio is not run.

Verification completed on 2026-10-19: 105 automated unit tests passed; lint,
production build and whitespace checks passed. Browser checks finished with two
passed and one skipped (live Azure audio). The partial-extraction workflow used
mocked API responses; no live Ollama completeness measurement was performed.
The real local classifier check returned FR and NFR for its two single-input
cases, but the illustrative CSV comparison still contained mismatches. These
checks do not establish overall classification accuracy.
