// One function per existing Component 3 endpoint (plus the thin /demo helpers).
import { apiRequest } from "./client.js";

const MINUTE = 60 * 1000;

export const api = {
  health: () => apiRequest("/health", { timeoutMs: 5000 }),
  overview: () => apiRequest("/demo/overview", { timeoutMs: 10000 }),
  engineSwitch: (engine, colabTunnelUrl = null, customModel = null) =>
    apiRequest("/demo/engine-switch", {
      method: "POST",
      body: { engine, colab_tunnel_url: colabTunnelUrl, custom_model: customModel },
    }),
  engineReload: () => apiRequest("/demo/engine-reload", { method: "POST", body: {} }),
  crudDomains: () => apiRequest("/demo/crud-domains"),
  fixture: (fixtureId) => apiRequest(`/demo/fixtures/${encodeURIComponent(fixtureId)}`),
  previewBuild: (request) =>
    apiRequest("/demo/preview/build", { method: "POST", body: request, timeoutMs: 12 * MINUTE }),
  previewStart: (previewId) =>
    apiRequest("/demo/preview/start", { method: "POST", body: { preview_id: previewId } }),
  previewStop: (previewId) =>
    apiRequest("/demo/preview/stop", { method: "POST", body: { preview_id: previewId } }),
  previewStatus: (previewId) => apiRequest(`/demo/preview/${encodeURIComponent(previewId)}`),

  validateInput: (inputPackage) =>
    apiRequest("/validate-input", { method: "POST", body: inputPackage }),
  buildDesignContext: (generationContext) =>
    apiRequest("/design-context", { method: "POST", body: generationContext }),
  selectStack: (request) => apiRequest("/stack-selection", { method: "POST", body: request }),

  generate: (request) =>
    apiRequest("/generation-runs", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
  generateExperimental: (request) =>
    apiRequest("/experiments/claude-generation", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
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
  graphRtm: (graphId, version = null) =>
    apiRequest(
      version == null
        ? `/traceability/graphs/${encodeURIComponent(graphId)}/rtm`
        : `/traceability/graphs/${encodeURIComponent(graphId)}/versions/${version}/rtm`,
    ),
  graphMetrics: (graphId, version = null) =>
    apiRequest(
      version == null
        ? `/traceability/graphs/${encodeURIComponent(graphId)}/metrics`
        : `/traceability/graphs/${encodeURIComponent(graphId)}/versions/${version}/metrics`,
    ),

  createBaseline: () =>
    apiRequest("/demo/scoped-regeneration/baseline", { method: "POST", timeoutMs: 2 * MINUTE }),
  impactSelection: (request) =>
    apiRequest("/impact-selections", { method: "POST", body: request }),
  // MOCK is a deterministic fallback pipeline and does not claim AI/RAG repair.
  // REAL_LOCAL_OLLAMA uses the existing endpoint that calls local Ollama.
  scopedRegeneration: (mode, request) =>
    mode === "MOCK"
      ? apiRequest("/demo/scoped-regenerations/mock", { method: "POST", body: request, timeoutMs: 2 * MINUTE })
      : apiRequest("/scoped-regenerations", { method: "POST", body: request, timeoutMs: 10 * MINUTE }),
};
