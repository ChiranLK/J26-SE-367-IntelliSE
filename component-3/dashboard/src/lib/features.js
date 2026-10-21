// Pages that are built but switched off for now. Scoped regeneration needs the independent tester (C4), which is not
// connected yet, so it stays hidden unless VITE_SHOW_SCOPED_REGENERATION=true. The tests keep exercising it.
export const SHOW_SCOPED_REGENERATION =
  import.meta.env.MODE === "test" || import.meta.env.VITE_SHOW_SCOPED_REGENERATION === "true";
