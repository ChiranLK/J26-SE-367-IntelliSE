import { vi } from "vitest";
import { STORAGE_KEY, emptySession } from "../src/state/session.jsx";

// Test doubles for the HTTP boundary only. They stand in for the network so the
// real client, endpoint, state, and page code run unchanged. Response bodies here
// are test inputs; no test asserts that they reflect real backend behavior.

export function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// routes: { "POST /api/v1/validate-input": (body, init) => Response | object }
export function installFetch(routes) {
  const calls = [];
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const key = `${method} ${url}`;
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ key, method, url, body });
    const handler = routes[key];
    if (!handler) {
      return jsonResponse({ errors: [{ code: "TEST_UNROUTED", field: null, message: `No test route for ${key}` }] }, 500);
    }
    const result = typeof handler === "function" ? await handler(body, init) : handler;
    return result instanceof Response ? result : jsonResponse(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock, called: (key) => calls.filter((call) => call.key === key) };
}

export const HEALTH = { status: "ok", service_name: "intelise-component-3", api_version: "v1" };

export const OVERVIEW_OK = {
  service_name: "intelise-component-3",
  api_version: "v1",
  ollama: {
    base_url: "http://127.0.0.1:11434",
    configured_model: "qwen2.5-coder:3b",
    reachable: true,
    model_installed: true,
    detail: "Ollama is reachable and the configured model is installed.",
    checked_at_utc: "2026-10-14T00:00:00Z",
  },
  teamsoclo: {
    enabled: true,
    key_configured: true,
    model: "claude-opus-5-5",
  },
  generated_workspace_root_name: "demo-ui",
  traceability_store_name: "demo-ui.sqlite3",
  integrations: [
    { component: "Component 1 (requirements)", state: "SIMULATED_FIXTURE", note: "simulated" },
    { component: "Component 4 (testing, XAI)", state: "NOT_INTEGRATED", note: "none" },
  ],
};

export const CRUD_DOMAINS = {
  catalog_version: "1.0",
  review_status: "NOT_INDEPENDENTLY_REVIEWED",
  domains: [
    {
      domain_id: "student_management",
      title: "Student Management",
      fixture_id: "student_management",
      classification: "SIMULATED_C1_C2_FIXTURE",
      notice: "SIMULATED",
    },
  ],
};

export const baseRoutes = () => ({
  "GET /api/v1/health": HEALTH,
  "GET /api/v1/demo/overview": OVERVIEW_OK,
  "GET /api/v1/demo/crud-domains": CRUD_DOMAINS,
});

export function seedSession(partial) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...emptySession(), ...partial }));
}

export function makeManifest({ mode = "TEMPLATE_ONLY", runId = "run-1", dynamic = false } = {}) {
  const generatedOrigin = mode === "LOCAL_LLM"
    ? "LOCAL_LLM"
    : mode === "EXPERIMENTAL_CLAUDE" || mode === "EXPERIMENTAL_OPENROUTER"
      ? mode
      : "TEMPLATE";
  const files = [
    { file_id: "F1", relative_path: "backend/src/services/taskService.js", module_identity: "taskService", artifact_type: "SOURCE", origin: generatedOrigin, sha256: "a".repeat(64), size_bytes: 120, requirement_ids: ["REQ-1"] },
    { file_id: "F2", relative_path: "backend/src/app.js", module_identity: "app", artifact_type: "SOURCE", origin: "TEMPLATE", sha256: "b".repeat(64), size_bytes: 80, requirement_ids: [] },
  ];
  return {
    generation_run_id: runId,
    generated_at_utc: "2026-10-14T00:00:00Z",
    generation_mode: mode,
    selected_frontend: "REACT",
    selected_backend: "NODE_JS",
    stack_approval: { classification: "CALLER_ASSERTED_PROVISIONAL_APPROVAL", authenticity_verified: false },
    files,
    artifact_digest_sha256: "c".repeat(64),
    run_evidence: {
      evidence_digest_sha256: "d".repeat(64),
      ...(dynamic
        ? {
            generator_version: "react-node-crud-generator-v1",
            template_set_version: "react-node-crud-scaffold-v1",
          }
        : {}),
    },
    execution_status: "NOT_EXECUTED",
    trust_boundary: "Generated code is untrusted and was not executed.",
    llm_inference: mode === "LOCAL_LLM" || mode === "EXPERIMENTAL_CLAUDE" || mode === "EXPERIMENTAL_OPENROUTER"
      ? {
          provider: { LOCAL_LLM: "ollama-local", EXPERIMENTAL_CLAUDE: "teamsoclo-claude", EXPERIMENTAL_OPENROUTER: "openrouter" }[mode],
          configured_model_identifier: { LOCAL_LLM: "qwen2.5-coder:3b", EXPERIMENTAL_CLAUDE: "claude-haiku-4-5", EXPERIMENTAL_OPENROUTER: "openai/gpt-4o" }[mode],
          response_model_identifier: { LOCAL_LLM: "qwen2.5-coder:3b", EXPERIMENTAL_CLAUDE: "claude-haiku-4-5", EXPERIMENTAL_OPENROUTER: "openai/gpt-4o-2024-08-06" }[mode],
          prompt_template_version: "v-test",
          generation_parameters: mode === "LOCAL_LLM"
            ? { temperature: 0, num_ctx: 4096, timeout_seconds: 120 }
            : { temperature: 0, max_tokens: 4096, timeout_seconds: 120 },
          client_inference_latency_ms: 1500,
          response: mode === "LOCAL_LLM" ? { eval_count: 99 } : { output_tokens: 99 },
        }
      : null,
  };
}

export const makeRun = (options) => ({
  workspace_relative_path: `demo/${options?.runId ?? "run-1"}`,
  manifest_relative_path: `demo/${options?.runId ?? "run-1"}/artifact-manifest.json`,
  manifest: makeManifest(options),
});

export function makeRegenerationResult({ status = "REVIEW_REQUIRED", mock = true } = {}) {
  return {
    status,
    reason_codes: status === "REVIEW_REQUIRED" ? ["IMPACT_SELECTION_REVIEW_REQUIRED"] : ["PATCH_APPLIED_STRUCTURALLY_VERIFIED"],
    model_evidence_class: mock ? "MOCKED_TEST_DOUBLE" : "REAL_LOCAL_OLLAMA",
    impact_selection: { status: "REVIEW_REQUIRED", defects: [], selected_modules: [], reason_codes: [] },
    patch_attempts: [],
    patches: [],
    artifact_versioning: null,
    preservation: null,
    structural_verification: null,
    graph_versioning: null,
    c4_retest_handoff: null,
    escalation: null,
    discarded_workspace_relative_path: null,
    metrics: { total_latency_ms: 1, llm_call_count: 0, rejected_attempt_count: 0, within_request_attempt_count: 0, within_request_attempt_limit: 2, repair_success: "NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST" },
    repair_execution_mode: mock ? "DETERMINISTIC_TEST_DOUBLE" : "AI_RAG_LOCAL_LLM",
    retrieval_evidence: [{
      module_path: "backend/src/services/taskService.js",
      rag_a_chunk_ids: mock ? [] : ["RAGA-CHUNK-001"],
      rag_b_rule_ids: mock ? [] : ["node-svc-001"],
      applied_to_prompt: !mock,
    }],
    patch_event: null,
    human_review_package: null,
    c4_testing_claim: false,
    execution_claim: "GENERATED_CODE_NOT_EXECUTED",
  };
}

export const DEFECT_FIXTURE = {
  fixture_id: "defect-scenarios",
  classification: "SIMULATED_C4_FIXTURE",
  review_status: "NOT_INDEPENDENTLY_REVIEWED",
  notice: "SIMULATED defect scenarios.",
  payload: {
    scenarios: [
      {
        scenario_id: "SIM-SCN-001-service",
        description: "Service defect",
        expected_status: "SELECTED",
        expected_modules: ["backend/src/services/taskService.js"],
        defects: [
          {
            defect_id: "SIM-DEF-001",
            category: "BUSINESS_LOGIC",
            severity: "HIGH",
            title: "Unknown id not rejected",
            affected_requirement_ids: ["REQ-1"],
            failing_tests: [{ test_case_id: "SIM-TC-1", hook_type: "TEST_FILE", hook_ref: "t.js" }],
            explanation: "SIMULATED",
          },
        ],
      },
    ],
  },
};

export function makeBaseline() {
  return {
    classification: "SIMULATED_DEFECTIVE_BASELINE",
    model_evidence_class: "MOCKED_TEST_DOUBLE",
    notice: "SIMULATED baseline.",
    injected_defect_module: "backend/src/services/taskService.js",
    generation_run: makeRun({ runId: "baseline-run" }),
    design_context: { design_context_version: "1.0" },
    graph_snapshot: { graph_id: "g-1", graph_version: 3, graph_content_digest_sha256: "e".repeat(64) },
  };
}
