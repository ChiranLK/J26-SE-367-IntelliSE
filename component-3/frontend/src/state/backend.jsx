import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/endpoints.js";

// Real status of the FastAPI service and the local Ollama probe, fetched from the API.
// While the API is unreachable the value stays "unreachable"; it is never defaulted to ok.
const BackendContext = createContext(null);

export function BackendProvider({ children }) {
  const initialRefreshStarted = useRef(false);
  const [state, setState] = useState({
    loading: true,
    health: null,
    overview: null,
    error: null,
    checkedAt: null,
  });

  const refresh = useCallback(async () => {
    setState((previous) => ({ ...previous, loading: true }));
    let health = null;
    let overview = null;
    let error = null;
    try {
      health = await api.health();
      overview = await api.overview();
    } catch (caught) {
      error = caught;
    }
    setState({ loading: false, health, overview, error, checkedAt: Date.now() });
  }, []);

  useEffect(() => {
    // React StrictMode deliberately replays effects in the Vite development build.
    // Probe once per mounted provider so an unnecessary duplicate Ollama request cannot
    // race the real response and replace it with a timeout during a presentation reload.
    if (initialRefreshStarted.current) return;
    initialRefreshStarted.current = true;
    refresh();
  }, [refresh]);

  const value = useMemo(() => ({ ...state, refresh }), [state, refresh]);
  return <BackendContext.Provider value={value}>{children}</BackendContext.Provider>;
}

export function useBackend() {
  const value = useContext(BackendContext);
  if (!value) throw new Error("useBackend must be used inside BackendProvider");
  return value;
}
