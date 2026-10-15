import { useCallback, useEffect, useRef, useState } from "react";

// Runs one async API action and exposes real loading / error state. A failure is
// kept as the thrown ApiError; the hook never swaps in fallback data.
export function useAction(fn) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    startedAt: null,
    durationMs: null,
  });
  const alive = useRef(true);
  const latestFn = useRef(fn);
  latestFn.current = fn;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const run = useCallback(async (...args) => {
    const startedAt = Date.now();
    setState({ loading: true, error: null, startedAt, durationMs: null });
    try {
      const result = await latestFn.current(...args);
      if (alive.current) {
        setState({ loading: false, error: null, startedAt: null, durationMs: Date.now() - startedAt });
      }
      return result;
    } catch (error) {
      if (alive.current) {
        setState({ loading: false, error, startedAt: null, durationMs: Date.now() - startedAt });
      }
      return undefined;
    }
  }, []);

  const clear = useCallback(
    () => setState({ loading: false, error: null, startedAt: null, durationMs: null }),
    [],
  );

  return { run, clear, ...state };
}
