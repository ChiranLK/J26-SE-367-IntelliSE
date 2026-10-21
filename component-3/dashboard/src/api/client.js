// Minimal fetch wrapper for the real Component 3 API.
//
// It never substitutes data on failure: every failure becomes an ApiError that the
// UI renders as-is (network, timeout, HTTP error with C3's structured errors, or an
// unreadable success body).

import { recordCall } from "../state/callLog.js";

export const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor({ kind, message, status = null, errors = [], path = "" }) {
    super(message);
    this.name = "ApiError";
    this.kind = kind; // "network" | "timeout" | "http" | "invalid-response" | "aborted"
    this.status = status;
    this.errors = errors; // [{code, field, message}]
    this.path = path;
  }
}

function normalizeErrors(payload) {
  if (payload && Array.isArray(payload.errors)) {
    return payload.errors.map((item) => ({
      code: String(item.code ?? "UNKNOWN_ERROR"),
      field: item.field ?? null,
      message: String(item.message ?? ""),
    }));
  }
  if (payload && typeof payload.detail === "string") {
    return [{ code: "HTTP_ERROR", field: null, message: payload.detail }];
  }
  return [];
}

// Every real call is logged (method, path, HTTP status, measured duration) so the
// dashboard timeline can show only what actually happened in this session.
export async function apiRequest(path, options = {}) {
  const startedAt = Date.now();
  const method = options.method ?? "GET";
  try {
    const result = await rawApiRequest(path, options);
    recordCall({ method, path, status: 200, ok: true, durationMs: Date.now() - startedAt, at: new Date().toISOString() });
    return result;
  } catch (error) {
    recordCall({
      method,
      path,
      status: error?.status ?? null,
      ok: false,
      errorCode: error?.errors?.[0]?.code ?? error?.kind ?? "ERROR",
      durationMs: Date.now() - startedAt,
      at: new Date().toISOString(),
    });
    throw error;
  }
}

async function rawApiRequest(
  path,
  { method = "GET", body, timeoutMs = 30000, signal } = {},
) {
  const url = `${API_PREFIX}${path}`;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (cause) {
    clearTimeout(timer);
    if (timedOut) {
      throw new ApiError({
        kind: "timeout",
        path,
        message: `No response from the Component 3 API within ${Math.round(timeoutMs / 1000)} s.`,
      });
    }
    if (cause?.name === "AbortError") {
      throw new ApiError({ kind: "aborted", path, message: "The request was cancelled." });
    }
    throw new ApiError({
      kind: "network",
      path,
      message:
        "Cannot reach the Component 3 API. Check that FastAPI is running on 127.0.0.1:8000.",
    });
  }
  clearTimeout(timer);

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const errors = normalizeErrors(payload);
    const unavailableThroughProxy = payload === null && response.status >= 500;
    throw new ApiError({
      kind: "http",
      path,
      status: response.status,
      errors,
      message:
        errors[0]?.message ||
        (unavailableThroughProxy
          ? `The Component 3 API or local dashboard proxy is unavailable (HTTP ${response.status}).`
          : `The API answered HTTP ${response.status}.`),
    });
  }
  if (payload === null) {
    throw new ApiError({
      kind: "invalid-response",
      path,
      status: response.status,
      message: "The API answered successfully but the body was not valid JSON.",
    });
  }
  return payload;
}
