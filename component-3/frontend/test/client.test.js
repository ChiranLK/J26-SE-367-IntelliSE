import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api/endpoints.js";
import { ApiError, apiRequest } from "../src/api/client.js";
import { installFetch, jsonResponse } from "./helpers.js";

describe("apiRequest", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls the real /api/v1 path and sends JSON bodies", async () => {
    const { calls } = installFetch({ "POST /api/v1/validate-input": { ok: true } });

    const result = await apiRequest("/validate-input", { method: "POST", body: { a: 1 } });

    expect(result).toEqual({ ok: true });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/validate-input");
    expect(calls[0].body).toEqual({ a: 1 });
  });

  it("reports an unreachable backend as a network error, never as data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(apiRequest("/health")).rejects.toMatchObject({ kind: "network", path: "/health" });
  });

  it("reports a timeout when the server never answers", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, init) => new Promise((_resolve, reject) => {
        init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      })),
    );

    const pending = apiRequest("/generation-runs", { method: "POST", body: {}, timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toMatchObject({ kind: "timeout" });
    await vi.advanceTimersByTimeAsync(1500);
    await assertion;
  });

  it("keeps C3's structured error envelope for HTTP 422 and 409", async () => {
    installFetch({
      "POST /api/v1/validate-input": () => jsonResponse({ errors: [{ code: "DRAFT_REQUIREMENT", field: "c1.requirements[0].status", message: "Requirement is not approved." }] }, 422),
      "POST /api/v1/generation-runs": () => jsonResponse({ errors: [{ code: "STACK_APPROVAL_REQUIRED", field: "stack_approval", message: "Approve first." }] }, 409),
    });

    const validation = await apiRequest("/validate-input", { method: "POST", body: {} }).catch((e) => e);
    const generation = await apiRequest("/generation-runs", { method: "POST", body: {} }).catch((e) => e);

    expect(validation).toBeInstanceOf(ApiError);
    expect(validation).toMatchObject({ kind: "http", status: 422 });
    expect(validation.errors).toEqual([{ code: "DRAFT_REQUIREMENT", field: "c1.requirements[0].status", message: "Requirement is not approved." }]);
    expect(generation).toMatchObject({ status: 409, errors: [{ code: "STACK_APPROVAL_REQUIRED" }] });
  });

  it("reports FastAPI default validation errors and non-JSON failures honestly", async () => {
    installFetch({
      "GET /api/v1/a": () => jsonResponse({ detail: "Not Found" }, 404),
      "GET /api/v1/b": () => new Response("<html>Bad gateway</html>", { status: 502 }),
    });

    const notFound = await apiRequest("/a").catch((e) => e);
    const gateway = await apiRequest("/b").catch((e) => e);

    expect(notFound.errors).toEqual([{ code: "HTTP_ERROR", field: null, message: "Not Found" }]);
    expect(gateway).toMatchObject({ kind: "http", status: 502, errors: [] });
    expect(gateway.message).toBe(
      "The Component 3 API or local frontend proxy is unavailable (HTTP 502).",
    );
  });

  it("rejects a successful but unreadable body instead of inventing a result", async () => {
    installFetch({ "GET /api/v1/c": () => new Response("not json", { status: 200 }) });

    await expect(apiRequest("/c")).rejects.toMatchObject({ kind: "invalid-response" });
  });
});

describe("api endpoint routing", () => {
  it("sends MOCK regeneration to the demo helper and REAL regeneration to the existing endpoint", async () => {
    const { calls } = installFetch({
      "POST /api/v1/demo/scoped-regenerations/mock": { mode: "mock" },
      "POST /api/v1/scoped-regenerations": { mode: "real" },
    });

    await api.scopedRegeneration("MOCK", { x: 1 });
    await api.scopedRegeneration("REAL_LOCAL_OLLAMA", { x: 2 });

    expect(calls.map((call) => call.key)).toEqual([
      "POST /api/v1/demo/scoped-regenerations/mock",
      "POST /api/v1/scoped-regenerations",
    ]);
  });

  it("uses the existing C3 endpoints for the pipeline", async () => {
    const { calls } = installFetch({
      "POST /api/v1/validate-input": {},
      "POST /api/v1/design-context": {},
      "POST /api/v1/stack-selection": {},
      "POST /api/v1/generation-runs": {},
      "POST /api/v1/structural-verifications": {},
      "POST /api/v1/traceability/graphs": {},
      "GET /api/v1/traceability/graphs/g%201": {},
      "GET /api/v1/traceability/graphs/g%201/versions/2": {},
      "POST /api/v1/impact-selections": {},
    });

    await api.validateInput({});
    await api.buildDesignContext({});
    await api.selectStack({});
    await api.generate({});
    await api.structuralVerification({});
    await api.createGraph({});
    await api.latestGraph("g 1");
    await api.graphVersion("g 1", 2);
    await api.impactSelection({});

    expect(calls).toHaveLength(9);
    expect(calls.every((call) => call.url.startsWith("/api/v1/"))).toBe(true);
  });
});
