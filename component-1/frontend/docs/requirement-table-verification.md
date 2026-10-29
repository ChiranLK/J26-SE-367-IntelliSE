# Compact requirement review table

The Step 2 requirement cards have been replaced with one semantic HTML table:
ID, Requirement, Model prediction, Human review, Details. Short display IDs such
as R01 help scanning; original IDs and supporting quotes remain accessible under
View details. The table uses a caption, scoped headers, labelled row controls and
accessible expanded-state/details associations. A horizontally scrollable focusable
region contains the table on narrow screens.

Original model badges and saved human labels remain separate. Each requirement
retains its existing explicit Save review request, UUID mapping, optional note,
reviewer/date metadata, duplicate guard and uncertain-save retry behavior. A saved
label expands to show its metadata. Evidence and Unclear points expand in a full-width
row. Toggling details does not unmount the editor or discard drafts. Unsaved changes
continue to block export; saved labels are retrieved when reopening the project.
No new automatic saving, client approval or retraining is introduced.

Backend services, model artifacts, source discussions and JSON/text export contracts
were not changed. No backend files were modified for this table change. Earlier
staged and unrelated work was preserved; nothing was committed or pushed.

## Checks

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

The Chrome workflow uses an isolated mocked HTTP API. Its eight-requirement
calculator fixture checks row text/identity, an explicit save on the second row,
duplicate-save protection, reopening/retrieval, draft preservation across detail
toggles, export blocking for unsaved changes, mobile table containment and desktop
layout. Existing workflow checks also cover source evidence, ambiguity questions,
saved corrections, project deletion/recovery and actual JSON/text file downloads.
These fixture outputs are UI test data, not model accuracy evidence.

The separate opt-in model tester checks the existing actual local classifier. Live
Azure audio is not exercised for this table change. No real client records are
modified; previous backend MongoDB verification is documented separately. The
unchanged baseline and English ambiguity rules remain fallible; within-corpus
metrics do not prove correctness on new projects or individual requirements.

## Results

- Frontend unit suite: **102 passed**.
- ESLint: passed, zero warnings. Vite production build: passed.
- Chrome: **2 passed, 1 skipped**. The full workflow and eight-row calculator
  table checks passed, including saving/reloading the second row by its original
  requirement ID, preserving a draft while toggling another row's details,
  preventing duplicate saves, and containing horizontal scrolling at 375 px.
- The separate existing actual local classifier check passed. The live audio
  browser scenario was skipped; no Azure calls were made.
- An initial test run caught a fixture returning another project's extraction;
  the fixture now scopes retrieval to its project, matching the real API.

Temporary mock-API layout screenshots:
`<system-temp>/intellise-c1-workspace-table-desktop.png`
and
`<system-temp>/intellise-c1-workspace-table-mobile.png`.
Their labels are fixture values for UI verification, not measured predictions.
