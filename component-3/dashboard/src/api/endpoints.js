// One function per existing Component 3 endpoint (plus the thin /demo helpers).
import { API_PREFIX, apiRequest } from "./client.js";

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

  // Rule-governed hybrid pipeline (KB + rules + templates + RAG + bounded OpenRouter).
  hybridOverview: () => apiRequest("/hybrid/overview", { timeoutMs: 30000 }),
  hybridFixture: (fixtureId) => apiRequest(`/hybrid/fixtures/${encodeURIComponent(fixtureId)}`),
  hybridValidate: (inputPackage) => apiRequest("/hybrid/contracts/validate", { method: "POST", body: inputPackage }),
  hybridGenerate: (request) => apiRequest("/hybrid/runs", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
  hybridLocation: (runId) => apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}/location`),
  hybridOpenFolder: (runId) => apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}/open-folder`, { method: "POST", body: {} }),
  hybridArchiveUrl: (runId) => `${API_PREFIX}/hybrid/runs/${encodeURIComponent(runId)}/archive`,
  hybridRun: (runId) => apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}`),
  hybridTrace: (projectId) => apiRequest(`/hybrid/projects/${encodeURIComponent(projectId)}/trace`),
  hybridRequirementChange: (request) =>
    apiRequest("/hybrid/regenerations/requirement-change", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
  hybridInjectDefect: (runId) =>
    apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}/simulated-defect-injection`, { method: "POST", body: {} }),
  hybridSimulatedDefect: (runId) => apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}/simulated-c4-defect`),
  hybridSimulatedReadiness: (runId) => apiRequest(`/hybrid/runs/${encodeURIComponent(runId)}/simulated-c4-readiness`),
  hybridDefect: (submission) => apiRequest("/hybrid/c4/defects", { method: "POST", body: submission, timeoutMs: 6 * MINUTE }),
  hybridGate: (request) => apiRequest("/hybrid/deployment-gate", { method: "POST", body: request }),
  hybridLlmTrial: (runId, bypassCache) =>
    apiRequest("/hybrid/llm-trial", { method: "POST", body: { generation_run_id: runId, bypass_cache: bypassCache }, timeoutMs: 10 * MINUTE }),
  hybridPreviews: () => apiRequest("/hybrid/preview", { timeoutMs: 30000 }),
  hybridPreviewStart: (runId) =>
    apiRequest("/hybrid/preview/start", { method: "POST", body: { generation_run_id: runId }, timeoutMs: 20 * MINUTE }),
  hybridPreviewStop: (previewId) =>
    apiRequest("/hybrid/preview/stop", { method: "POST", body: { preview_id: previewId }, timeoutMs: 2 * MINUTE }),
  hybridPreviewStatus: (previewId) => apiRequest(`/hybrid/preview/${encodeURIComponent(previewId)}`, { timeoutMs: 30000 }),
  hybridPreviewGpaCheck: (previewId) =>
    apiRequest(`/hybrid/preview/${encodeURIComponent(previewId)}/gpa-check`, { method: "POST", body: {}, timeoutMs: 30000 }),

  validateInput: (inputPackage) =>
    apiRequest("/validate-input", { method: "POST", body: inputPackage }),
  // Send the accepted input to the backend PlantUML design parser.
  buildDesignContext: (generationContext) =>
    apiRequest("/design-context", { method: "POST", body: generationContext }),
  // Ask the backend to calculate FR-to-UML anchor coverage.
  designCoverage: (generationContext) =>
    apiRequest("/design-coverage", { method: "POST", body: generationContext }),
  // Ask the backend to score and rank the four documented technology stacks.
  selectStack: (request) => apiRequest("/stack-selection", { method: "POST", body: request }),

  generate: (request) =>
    apiRequest("/generation-runs", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
  behaviourGenerate: (request) =>
    apiRequest("/behaviour/generation-runs", { method: "POST", body: request, timeoutMs: 30 * MINUTE }),
  behaviourStart: (workspaceRelativePath) =>
    apiRequest("/behaviour/apps/start", { method: "POST", body: { workspace_relative_path: workspaceRelativePath }, timeoutMs: 6 * MINUTE }),
  behaviourArchiveUrl: (workspaceRelativePath) =>
    `${API_PREFIX}/behaviour/workspace/archive?workspace_relative_path=${encodeURIComponent(workspaceRelativePath)}`,
  behaviourStop: (workspaceRelativePath) =>
    apiRequest("/behaviour/apps/stop", { method: "POST", body: { workspace_relative_path: workspaceRelativePath } }),
  openrouterCheck: () => apiRequest("/experiments/openrouter-check", { method: "POST", body: {}, timeoutMs: 2 * MINUTE }),
  generateOpenRouter: (request) =>
    apiRequest("/experiments/openrouter-generation", { method: "POST", body: request, timeoutMs: 6 * MINUTE }),
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
  graphImpact: (graphId, version, requirementId) =>
    apiRequest(
      `/traceability/graphs/${encodeURIComponent(graphId)}/versions/${version}/impact/${encodeURIComponent(requirementId)}`,
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
