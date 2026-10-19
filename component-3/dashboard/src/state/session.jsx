import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from "react";

// The session only stores responses that real API calls returned. It is kept in
// sessionStorage so a browser refresh during a demo does not lose the run; "Reset
// session" clears it. Nothing is ever pre-populated.

export const STORAGE_KEY = "intelise-c3-demo-session-v1";

export const emptySession = () => ({
  fixtures: { inputPackage: null, defectScenarios: null, stackCriteria: null },
  inputText: "",
  inputContractVersion: "1.0",
  c1InputText: "",
  c2InputText: "",
  inputSources: { c1: "NONE", c2: "NONE" },
  validation: null, // { ok, at, generationContext?, error? }
  designContext: null,
  applicationProfile: "SCHEMA_DRIVEN_CRUD",
  stackReport: null,
  approval: null, // { status, approvedBy, approvalReference, acknowledgesProvisionalPolicy, at }
  generationRun: null, // { run, mode, durationMs, at }
  preview: null,
  structural: null,
  graph: null, // { snapshot, versions: [snapshot...] }
  scoped: { scenarioId: null, baseline: null, impact: null, runs: [] },
});

function load() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return emptySession();
    const stored = JSON.parse(raw);
    const migrated = { ...emptySession(), ...stored };
    if ((!stored.c1InputText || !stored.c2InputText) && stored.inputText) {
      try {
        const legacyPackage = JSON.parse(stored.inputText);
        migrated.inputContractVersion = legacyPackage.contract_version ?? "1.0";
        migrated.c1InputText = legacyPackage.c1 ? JSON.stringify(legacyPackage.c1, null, 2) : "";
        migrated.c2InputText = legacyPackage.c2 ? JSON.stringify(legacyPackage.c2, null, 2) : "";
        migrated.inputSources = { c1: "MIGRATED_SESSION", c2: "MIGRATED_SESSION" };
      } catch {
        // Keep an invalid legacy draft untouched; the user can paste into the new editors.
      }
    }
    return migrated;
  } catch {
    return emptySession();
  }
}

function reducer(state, action) {
  if (action.type === "set") return { ...state, [action.key]: action.value };
  if (action.type === "update") return { ...state, [action.key]: action.update(state[action.key]) };
  if (action.type === "reset") return emptySession();
  return state;
}

const SessionContext = createContext(null);

export function SessionProvider({ children, initial }) {
  const [session, dispatch] = useReducer(reducer, undefined, () => initial ?? load());

  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } catch {
      // Storage may be full or disabled; the in-memory session still works.
    }
  }, [session]);

  const set = useCallback((key, value) => dispatch({ type: "set", key, value }), []);
  const update = useCallback((key, fn) => dispatch({ type: "update", key, update: fn }), []);
  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  const value = useMemo(() => ({ session, set, update, reset }), [session, set, update, reset]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
