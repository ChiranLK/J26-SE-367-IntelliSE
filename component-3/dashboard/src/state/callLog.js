import { useSyncExternalStore } from "react";

// Log of real API calls made in this browser session (method, path, status, measured
// duration). It is the only source for the pipeline timeline, so the timeline can
// never show a stage or a duration that did not come from a real response.
// sessionStorage is the source of truth so a refresh keeps the log; "Reset session"
// clears it.

const KEY = "intelise-c3-demo-calllog-v1";
const MAX_ENTRIES = 300;
const listeners = new Set();
let cachedRaw = null;
let cachedValue = [];

function readRaw() {
  try {
    return window.sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function getCallLog() {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      const parsed = raw ? JSON.parse(raw) : [];
      cachedValue = Array.isArray(parsed) ? parsed : [];
    } catch {
      cachedValue = [];
    }
  }
  return cachedValue;
}

function notify() {
  listeners.forEach((listener) => listener());
}

export function recordCall(entry) {
  try {
    const next = [...getCallLog(), entry].slice(-MAX_ENTRIES);
    window.sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage may be unavailable; the timeline then simply shows fewer stages.
  }
  notify();
}

export function clearCallLog() {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  notify();
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useCallLog() {
  return useSyncExternalStore(subscribe, getCallLog, getCallLog);
}
