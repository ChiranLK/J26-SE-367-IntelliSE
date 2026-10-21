// Engine-switch / Colab controls are for rehearsal only; they stay hidden unless the
// page URL carries ?advanced=1.
export function isAdvancedMode() {
  try {
    return new URLSearchParams(window.location.search).get("advanced") === "1";
  } catch {
    return false;
  }
}
