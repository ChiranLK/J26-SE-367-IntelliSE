# Restyled Human review dropdown

Replaced the platform-specific native label popup with a controlled React
combobox/listbox. It matches the green workspace theme, uses FR/NFR badges,
Functional/Non-functional names and short descriptions, marks the selected option,
and uses a compact green focus/open state. No package or dependency change was
needed. The review value is still controlled by the existing row editor.

Keyboard controls: Enter/Space open/select; arrows move the active option;
Home/End select the first/last active option; F/N navigate to FR/NFR; Escape closes
without committing the active option; Tab closes and follows normal tab order.
The control exposes its label, selected-value description, expanded state and
active option to assistive technology. Pointer selection preserves trigger focus.
The optional clear action affects the unsaved value, not a saved backend record.

A body portal avoids clipping inside the horizontally scrollable table. The popup
is clamped to viewport edges, opens above when needed, follows trigger scrolling,
and closes on outside pointer interaction, blur or resize. A row leaving the
viewport closes its popup. Loading/saving/uncertain states disable the picker;
changes still require explicit Save review. Original model predictions, row IDs,
source text, backend contracts, saved label history and export behavior remain.

## Verification

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

102 frontend tests passed; lint and production build passed. Chrome workflow
checks use a test-only HTTP API and cover real pointer selection, keyboard
selection without automatic saving, Escape preserving the chosen value, outside
click dismissal, Tab dismissal, popup viewport containment, row detail toggles,
save/retrieve by requirement ID and export/reopen behavior. The existing actual
local classifier is checked separately; mocked workflow labels are not accuracy
evidence. Live Azure audio is skipped and no client records are changed.

An initial browser run found the popup closing when programmatic focus scrolled
a row into view. Scroll handling now updates the popup position rather than
closing a visible trigger's menu. Subsequent workflow checks passed.

No backend files, model artifacts, dependencies, commits or pushes were changed
for this UI work. Prior staged/unrelated work remains preserved.

Final Chrome result: 2 passed, 1 live audio test skipped. The viewport-only
screenshot of the open styled menu was visually inspected; a full-page capture
would resize the viewport and intentionally dismiss the menu. Screenshot:
`<system-temp>/intellise-c1-workspace-label-dropdown.png`.
Its requirement labels are mocked UI fixtures, not actual model predictions.
