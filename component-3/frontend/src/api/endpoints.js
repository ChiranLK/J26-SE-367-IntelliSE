// One function per existing Component 3 endpoint (plus the thin /demo helpers).
import { apiRequest } from "./client.js";

const MINUTE = 60 * 1000;

export const api = {
  health: () => apiRequest("/health", { timeoutMs: 5000 }),
  overview: () => apiRequest("/demo/overview", { timeoutMs: 10000 }),
  fixture: (fixtureId) => apiRequest(`/demo/fixtures/${encodeURIComponent(fixtureId)}`),

  validateInput: (inputPackage) =>
    apiRequest("/validate-input", { method: "POST", body: inputPackage }),
  buildDesignContext: (generationContext) =>
    apiRequest("/design-context", { method: "POST", body: generationContext }),
  selectStack: (request) => apiRequest("/stack-selection", { method: "POST", body: request }),

  generate: (request) =>
    apiRequest("/generation-runs", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
  codePreview: (request) =>
    apiRequest("/demo/code-preview", { method: "POST", body: request }),
  workspaceRun: (workspaceRelativePath) =>
    apiRequest("/demo/workspace-run", {
      method: "POST",
      body: { workspace_relative_path: workspaceRelativePath },
    }),
  structuralVerification: (request) =>
    apiRequest("/structural-verifications", { method: "POST", body: request }),

  createGraph: (request) =>
    apiRequest("/traceability/graphs", { method: "POST", body: request }),
  latestGraph: (graphId) => apiRequest(`/traceability/graphs/${encodeURIComponent(graphId)}`),
  graphVersion: (graphId, version) =>
    apiRequest(`/traceability/graphs/${encodeURIComponent(graphId)}/versions/${version}`),

  createBaseline: () =>
    apiRequest("/demo/scoped-regeneration/baseline", { method: "POST", timeoutMs: 2 * MINUTE }),
  impactSelection: (request) =>
    apiRequest("/impact-selections", { method: "POST", body: request }),
  // MOCK uses the same real service with a deterministic test-double model.
  // REAL_LOCAL_OLLAMA uses the existing endpoint that calls local Ollama.
  scopedRegeneration: (mode, request) =>
    mode === "MOCK"
      ? apiRequest("/demo/scoped-regenerations/mock", { method: "POST", body: request, timeoutMs: 2 * MINUTE })
      : apiRequest("/scoped-regenerations", { method: "POST", body: request, timeoutMs: 10 * MINUTE }),
};
