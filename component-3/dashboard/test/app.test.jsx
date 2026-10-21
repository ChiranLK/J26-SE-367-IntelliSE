import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App.jsx";
import {
  DEFECT_FIXTURE,
  OVERVIEW_OK,
  baseRoutes,
  installFetch,
  jsonResponse,
  makeBaseline,
  makeRegenerationResult,
  makeRun,
  seedSession,
} from "./helpers.js";

const INPUT_PACKAGE = {
  contract_version: "1.0",
  c1: {
    project_id: "TASK-DEMO",
    srs_version: "SRS-1",
    approval_status: "APPROVED",
    requirements: [{ requirement_id: "REQ-1", title: "Create task", status: "APPROVED" }],
  },
  c2: {
    uml_version: "UML-1",
    release_status: "RELEASED",
    validation_state: "VALID",
    uml_elements: [{ uml_id: "UML-1", element_type: "CLASS_DIAGRAM", name: "TaskModel" }],
    ui_artifacts: [],
    requirement_uml_anchors: [{ anchor_id: "ANC-1", requirement_id: "REQ-1", uml_id: "UML-1" }],
  },
};

const GENERATION_CONTEXT = {
  project_id: "TASK-DEMO",
  srs_version: "SRS-1",
  uml_version: "UML-1",
  requirements: [{}],
  uml_elements: [{}],
  ui_artifacts: [],
  requirement_uml_anchors: [{}],
  upstream_provenance: { c1_approval_provenance_ref: "C1-REF", c2_validation_report_ref: "C2-REF" },
};

const nav = () => within(screen.getByRole("navigation"));
const openPage = async (user, name) => user.click(nav().getByRole("button", { name }));

describe("backend status", () => {
  it("shows the real health and Ollama probe result from the API", async () => {
    const { called } = installFetch(baseRoutes());

    render(<App />);

    expect(await screen.findByText("Ollama Local ready")).toBeInTheDocument();
    expect(screen.getByText("qwen2.5-coder:3b")).toBeInTheDocument();
    expect(screen.queryByText("API healthy")).not.toBeInTheDocument();
    expect(screen.queryByText("C4 NOT INTEGRATED")).not.toBeInTheDocument();
    expect(called("GET /api/v1/health")).toHaveLength(1);
    expect(called("GET /api/v1/demo/overview")).toHaveLength(1);
    expect(screen.queryByText("SIMULATED FIXTURE")).not.toBeInTheDocument();
  });

  it("shows the API as unreachable instead of pretending it is healthy", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("Backend unreachable");
    expect(screen.queryByText("API healthy")).not.toBeInTheDocument();
    expect(screen.queryByText(/Ollama Local/)).not.toBeInTheDocument();
  });

  it("warns when Ollama is up but the model is missing", async () => {
    installFetch({
      ...baseRoutes(),
      "GET /api/v1/demo/overview": {
        ...OVERVIEW_OK,
        ollama: { ...OVERVIEW_OK.ollama, model_installed: false, detail: "Model qwen2.5-coder:3b is not installed." },
      },
    });

    render(<App />);

    expect(await screen.findByText("Ollama model missing")).toBeInTheDocument();
  });
});

describe("C1/C2 inputs", () => {
  const C1_TEXT = ["R01 | FR | Unreviewed model prediction", "Add two numbers.", "Requirement ID: req-1"].join(String.fromCharCode(10));
  const C2_TEXT = ["@startuml", "class Addition", "@enduml"].join(String.fromCharCode(10));
  const fillDocuments = () => {
    fireEvent.change(screen.getByLabelText("C1 finalized SRS text"), { target: { value: C1_TEXT } });
    fireEvent.change(screen.getByLabelText("C2 finalized PlantUML source"), { target: { value: C2_TEXT } });
  };

  it("offers TXT, PlantUML, and JSON files in both upload controls without extension labels", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    for (const upload of [screen.getByLabelText("Upload C1 SRS document"), screen.getByLabelText("Upload C2 PlantUML document")]) {
      expect(upload).toHaveAttribute("accept", ".txt,.puml,.json");
    }
    expect(screen.queryByText(".txt")).not.toBeInTheDocument();
    expect(screen.queryByText(".puml")).not.toBeInTheDocument();
  });

  it("has no advanced JSON or fixture section any more", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    expect(screen.queryByText(/Advanced JSON contracts/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Load Task Management fixture/ })).not.toBeInTheDocument();
  });

  it("shows pasted documents in plain language and keeps the IDs in the technical details", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    fillDocuments();

    expect(screen.getByTestId("c1-summary")).toHaveTextContent("1 requirement found");
    expect(screen.getByTestId("c2-summary")).toHaveTextContent("1 class found");
    expect(screen.getByText("Add two numbers.")).toBeInTheDocument();
    expect(screen.getByText(/Technical details/)).toBeInTheDocument();
    expect(screen.queryByText(/notes about these documents/)).not.toBeInTheDocument();
  });

  it("validates with a single button and sends the package built from the two documents", async () => {
    const user = userEvent.setup();
    const { called } = installFetch({ ...baseRoutes(), "POST /api/v1/validate-input": GENERATION_CONTEXT });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    expect(screen.getByRole("button", { name: "Validate inputs" })).toBeDisabled();
    fillDocuments();
    await user.click(screen.getByRole("button", { name: "Validate inputs" }));

    expect(await screen.findByText("Inputs accepted")).toBeInTheDocument();
    const sent = called("POST /api/v1/validate-input")[0].body;
    expect(sent.c1.requirements.map((item) => item.requirement_id)).toContain("req-1");
    expect(screen.getByRole("button", { name: /Continue to Design/ })).toBeInTheDocument();
  });

  it("does not guess a class for a requirement that matches nothing in the diagram", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    fireEvent.change(screen.getByLabelText("C1 finalized SRS text"), { target: { value: C1_TEXT } });
    fireEvent.change(screen.getByLabelText("C2 finalized PlantUML source"), { target: { value: ["@startuml", "class Invoice", "@enduml"].join(String.fromCharCode(10)) } });

    await user.click(screen.getByRole("button", { name: "Validate inputs" }));

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("No class in the diagram matches the requirement");
    expect(screen.queryByText("Inputs accepted")).not.toBeInTheDocument();
  });

  it("shows the backend's validation errors and does not mark the input accepted", async () => {
    const user = userEvent.setup();
    installFetch({
      ...baseRoutes(),
      "POST /api/v1/validate-input": () => jsonResponse({ errors: [{ code: "REQUIREMENT_NOT_APPROVED", field: "c1.requirements[0].status", message: "Requirement REQ-1 is not approved." }] }, 422),
    });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    fillDocuments();

    await user.click(screen.getByRole("button", { name: "Validate inputs" }));

    const panel = await screen.findByTestId("error-panel");
    expect(panel).toHaveTextContent("REQUIREMENT_NOT_APPROVED");
    expect(panel).toHaveTextContent("HTTP 422");
    expect(panel).toHaveTextContent("Requirement REQ-1 is not approved.");
    expect(screen.queryByText("Inputs accepted")).not.toBeInTheDocument();
  });

  it("shows an unreachable-backend error during validation without fake data", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    fillDocuments();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await user.click(screen.getByRole("button", { name: "Validate inputs" }));

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("Backend unreachable");
    expect(screen.queryByText("Inputs accepted")).not.toBeInTheDocument();
  });
});

describe("Code generation", () => {
  const approvedSession = () => ({
    validation: { ok: true, at: "2026-10-14T00:00:00Z", generationContext: GENERATION_CONTEXT },
    designContext: { design_context_version: "1.0" },
    stackReport: { selected_stack: {} },
    approval: { status: "APPROVED_FOR_MVP_GENERATION", approvedBy: "me", approvalReference: "ref", acknowledgesProvisionalPolicy: true },
  });

  it("drops the previous design, stack and approval as soon as the input is changed", async () => {
    const user = userEvent.setup();
    seedSession(approvedSession());
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    await user.type(screen.getByLabelText("C1 finalized SRS text"), " edited");
    await openPage(user, /Design & Stack/);

    expect(await screen.findByText("Select Analyze design to review the uploaded class diagram.")).toBeInTheDocument();
  });

  it("explains the missing approval and keeps generation disabled", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Code Generation/);

    expect(screen.getByText("Approved stack required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate with Ollama Local" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate with Google Colab" })).toBeDisabled();
  });

  it("generates a non-CRUD behaviour app and starts it on a new port", async () => {
    const user = userEvent.setup();
    seedSession({ ...approvedSession(), applicationProfile: "CUSTOM_NON_CRUD" });
    const attempt = (unit, verdict, codes = []) => ({
      unit, attempt: 1, temperature: 0, configured_model_identifier: "qwen2.5-coder:3b", response_model_identifier: "qwen2.5-coder:3b",
      prompt_template_version: "behaviour-domain-per-class-v0", prompt_text_sha256: "a".repeat(64), prompt_request_sha256: "b".repeat(64),
      client_inference_latency_ms: 10, verdict, syntax_check: "PASSED", findings: codes.map((code) => ({ code, message: code })),
    });
    const manifest = {
      generation_run_id: "run-b1", application_profile: "CUSTOM_NON_CRUD_BEHAVIOUR", facade_class: "Calculator", facade_rule: "FACADE_MOST_PUBLIC_METHODS_V0",
      prompt_template_version: "behaviour-domain-per-class-v0", artifact_digest_sha256: "c".repeat(64), trust_boundary: "Stage 0 boundary.",
      attempts: [attempt("Addition", "ACCEPTED"), attempt("Calculator", "REJECTED", ["PROBE_INPUT_IGNORED"]), attempt("Calculator", "ACCEPTED")],
      probe: { status: "PASSED", note: "probe note", plan: [], steps: [{ call: "enterNumber(12)", ok: true }], findings: [], warnings: [] },
      files: [{ relative_path: "frontend/src/App.jsx", origin: "TEMPLATE", sha256: "f".repeat(64), size_bytes: 10 }, { relative_path: "backend/src/domain.mjs", origin: "LOCAL_LLM", sha256: "d".repeat(64), size_bytes: 10 }, { relative_path: "backend/server.mjs", origin: "TEMPLATE", sha256: "e".repeat(64), size_bytes: 10 }],
    };
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/behaviour/generation-runs": { workspace_relative_path: "behaviour/x/run-b1", manifest_relative_path: "behaviour/x/run-b1/behaviour-manifest.json", manifest },
      "POST /api/v1/behaviour/apps/start": { workspace_relative_path: "behaviour/x/run-b1", generation_run_id: "run-b1", status: "RUNNING", url: "http://127.0.0.1:8231/", port: 8231, pid: 1, sandbox: "node --permission" },
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    await user.click(screen.getByRole("button", { name: "Generate with Ollama Local" }));

    expect(await screen.findByText("Behaviour run evidence")).toBeInTheDocument();
    expect(called("POST /api/v1/behaviour/generation-runs")[0].body.mode).toBe("LOCAL_LLM");
    expect(screen.queryByText("Model calls per class")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download project (.zip)" })).toHaveAttribute("href", expect.stringContaining("/behaviour/workspace/archive?workspace_relative_path=behaviour%2Fx%2Frun-b1"));
    expect(screen.getByTestId("folder-frontend")).toHaveTextContent("frontend/src/App.jsx");
    expect(screen.getByTestId("folder-frontend")).toHaveTextContent("React + Vite");
    expect(screen.getByTestId("folder-backend")).toHaveTextContent("backend/src/domain.mjs");
    expect(screen.getByTestId("folder-api")).toHaveTextContent("/api/invoke");
    expect(screen.queryByTestId("folder-db")).not.toBeInTheDocument();
    expect(screen.getByTestId("folder-test-seams")).toHaveTextContent("does not produce test seams");
    expect(screen.queryByRole("button", { name: "Start app on a new port" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue to Application Preview" }));
    await user.click(await screen.findByRole("button", { name: "Start app on a new port" }));
    expect(await screen.findByRole("link", { name: "Open generated app" })).toHaveAttribute("href", "http://127.0.0.1:8231/");
    expect(called("POST /api/v1/behaviour/apps/start")[0].body).toEqual({ workspace_relative_path: "behaviour/x/run-b1" });
  });

  it("drops a saved behaviour run from the older layout instead of showing it", async () => {
    const user = userEvent.setup();
    seedSession({
      ...approvedSession(),
      applicationProfile: "CUSTOM_NON_CRUD",
      behaviourRun: {
        durationMs: 1000,
        run: {
          workspace_relative_path: "behaviour/x/old-run",
          manifest: { generation_run_id: "old-run", probe: { status: "PASSED" }, files: [{ relative_path: "server.mjs" }, { relative_path: "public/app.js" }, { relative_path: "src/domain.mjs" }] },
        },
      },
    });
    installFetch({ ...baseRoutes() });
    render(<App />);
    await openPage(user, /Code Generation/);

    expect(await screen.findByRole("button", { name: "Generate with Ollama Local" })).toBeInTheDocument();
    expect(screen.queryByText("Behaviour run evidence")).not.toBeInTheDocument();
    expect(screen.queryByText(/older layout/)).not.toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem(Object.keys(window.sessionStorage).find((key) => key.toLowerCase().includes("session")) ?? "")).behaviourRun).toBeNull();
  });

  it("mentions only Ollama Local in the sidebar", async () => {
    seedSession(approvedSession());
    installFetch(baseRoutes());
    render(<App />);

    expect(await screen.findByText("Ollama Local ready")).toBeInTheDocument();
    expect(screen.getByText("qwen2.5-coder:3b")).toBeInTheDocument();
    expect(screen.queryByText(/TeamSocLo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/OpenRouter/i)).not.toBeInTheDocument();
  });

  it("points a list-of-items design to the GPA project card instead of the Ollama buttons", async () => {
    const user = userEvent.setup();
    const base = approvedSession();
    seedSession({
      ...base,
      applicationProfile: "CUSTOM_NON_CRUD",
      designContext: { ...base.designContext, classes: [{ name: "GpaCalculationService", methods: [{ name: "calculate", parameters: [{ name: "modules", type_name: "ModuleResult[]" }] }] }] },
    });
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /Code Generation/);

    expect(screen.queryByRole("button", { name: "Generate with Ollama Local" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate with Google Colab" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate project" })).toBeInTheDocument();
  });

  it("lets the behaviour generator use TeamSocLo explicitly", async () => {
    const user = userEvent.setup();
    seedSession({ ...approvedSession(), applicationProfile: "CUSTOM_NON_CRUD" });
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/behaviour/generation-runs": () => jsonResponse({ errors: [{ code: "TEAMSOCLO_REQUEST_TIMEOUT", field: "teamsoclo", message: "TeamSocLo request timed out." }] }, 504),
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    await user.click(screen.getByRole("button", { name: "Generate with Google Colab" }));

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("TEAMSOCLO_REQUEST_TIMEOUT");
    expect(called("POST /api/v1/behaviour/generation-runs")[0].body.mode).toBe("EXPERIMENTAL_CLAUDE");
  });

  it("renders a backend gate conflict (HTTP 409) as an error, not as a result", async () => {
    const user = userEvent.setup();
    seedSession(approvedSession());
    installFetch({
      ...baseRoutes(),
      "POST /api/v1/generation-runs": () => jsonResponse({ errors: [{ code: "GENERATOR_NOT_IMPLEMENTED", field: "stack", message: "No generator for the selected stack." }] }, 409),
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    await user.click(screen.getByRole("button", { name: "Generate with Ollama Local" }));

    const panel = await screen.findByTestId("error-panel");
    expect(panel).toHaveTextContent("GENERATOR_NOT_IMPLEMENTED");
    expect(panel).toHaveTextContent("HTTP 409");
    expect(screen.queryByText("Run evidence")).not.toBeInTheDocument();
  });

  it("shows loading, then run evidence with TEMPLATE and LOCAL_LLM origins, and previews via the API", async () => {
    const user = userEvent.setup();
    seedSession(approvedSession());
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const run = makeRun({ mode: "LOCAL_LLM", runId: "run-llm" });
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/generation-runs": async () => { await gate; return jsonResponse(run, 201); },
      "POST /api/v1/demo/code-preview": () => ({
        relative_path: "backend/src/services/taskService.js",
        artifact_type: "SOURCE",
        origin: "LOCAL_LLM",
        sha256: "a".repeat(64),
        size_bytes: 120,
        truncated: false,
        content: "export const x = '<script>alert(1)</script>';",
        execution_claim: "DISPLAY_ONLY_NOT_EXECUTED",
      }),
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    await user.click(screen.getByRole("button", { name: "Generate with Ollama Local" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Generating (Qwen Local)");
    release();

    expect(await screen.findByText("run-llm")).toBeInTheDocument();
    expect(called("POST /api/v1/generation-runs")[0].body.mode).toBe("LOCAL_LLM");
    expect(called("POST /api/v1/generation-runs")[0].body.stack_approval.status).toBe("APPROVED_FOR_MVP_GENERATION");
    expect(screen.getByText("NOT EXECUTED")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("LOCAL_LLM")).toHaveLength(1);
    expect(within(table).getAllByText("TEMPLATE")).toHaveLength(1);

    await user.click(screen.getByText("backend/src/services/taskService.js", { selector: "code" }));
    const block = await screen.findByTestId("code-block");
    expect(block).toHaveTextContent("<script>alert(1)</script>"); // escaped text, not markup
    expect(block.querySelector("script")).toBeNull();
    expect(screen.getByText("display only · never executed")).toBeInTheDocument();
    expect(called("POST /api/v1/demo/code-preview")[0].body.relative_path).toBe("backend/src/services/taskService.js");
  });

  it("uses the dedicated endpoint for an explicit external LLM experiment", async () => {
    const user = userEvent.setup();
    seedSession(approvedSession());
    const run = makeRun({ mode: "EXPERIMENTAL_CLAUDE", runId: "run-external" });
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/experiments/claude-generation": () => jsonResponse(run, 201),
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    expect(screen.queryByLabelText(/TEMPLATE_ONLY/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate with Google Colab" }));

    expect(await screen.findByText("run-external")).toBeInTheDocument();
    expect(called("POST /api/v1/experiments/claude-generation")[0].body.mode).toBe("EXPERIMENTAL_CLAUDE");
    expect(screen.getByText("teamsoclo-claude")).toBeInTheDocument();
    expect(screen.getAllByText("claude-haiku-4-5")).toHaveLength(2);
  });

  it("builds and starts a dynamic generated UI with one action and shows the new local port", async () => {
    const user = userEvent.setup();
    const run = makeRun({ runId: "dynamic-run", dynamic: true });
    seedSession({
      ...approvedSession(),
      generationRun: { run, mode: "TEMPLATE_ONLY", durationMs: 5, at: "2026-10-19T00:00:00Z" },
    });
    const built = {
      preview_id: "dynamic-run",
      generation_run_id: "dynamic-run",
      workspace_relative_path: run.workspace_relative_path,
      artifact_digest_sha256: run.manifest.artifact_digest_sha256,
      status: "BUILT",
      ui_url: "http://127.0.0.1:13056/",
      api_url: "http://127.0.0.1:13057/",
      ui_port: 13056,
      api_port: 13057,
      updated_at_utc: "2026-10-19T00:00:00Z",
      execution_claim: "GENERATED_JS_EXECUTES_ONLY_INSIDE_DISPOSABLE_DOCKER_CONTAINER_NOT_ON_HOST",
      runtime_db_claim: "IN_MEMORY",
      browser_verification_claim: false,
    };
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/demo/preview/build": built,
      "POST /api/v1/demo/preview/start": { ...built, status: "RUNNING" },
    });
    render(<App />);
    await openPage(user, /Code Generation/);

    await user.click(screen.getByRole("button", { name: "Build & Start Local Preview" }));

    expect(await screen.findByText("Generated application is running locally")).toBeInTheDocument();
    expect(screen.getAllByText("http://127.0.0.1:13056/").length).toBeGreaterThan(0);
    expect(called("POST /api/v1/demo/preview/build")).toHaveLength(1);
    expect(called("POST /api/v1/demo/preview/start")[0].body).toEqual({ preview_id: "dynamic-run" });
  });
});

describe("Application profile", () => {
  it("routes custom non-CRUD designs to the behaviour generator instead of substituting a CRUD app", async () => {
    const user = userEvent.setup();
    seedSession({ validation: { ok: true, generationContext: GENERATION_CONTEXT } });
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /Design & Stack/);

    await user.click(screen.getByRole("button", { name: /Custom \/ non-CRUD application/ }));

    expect(screen.queryByText("How custom application generation works")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Custom \/ non-CRUD application/ })).toHaveClass("profile-active");
  });
});

describe("Living traceability reports", () => {
  it("loads the versioned RTM and reports orphan and coverage-gap codes", async () => {
    const user = userEvent.setup();
    const snapshot = {
      graph_id: "graph-1",
      graph_version: 2,
      persisted_at_utc: "2026-10-19T00:00:00Z",
      generation_run_id: "run-1",
      artifact_digest_sha256: "a".repeat(64),
      graph_content_digest_sha256: "b".repeat(64),
      relation_direction_policy_version: "C3_GRAPH_RELATION_DIRECTION_V1",
      nodes: [{
        node_id: "REQUIREMENT:REQ-1",
        node_type: "REQUIREMENT",
        source_identity: "REQ-1",
        label: "Create task",
        lifecycle_status: "ACTIVE",
        attributes: {},
      }],
      links: [],
      coverage: {
        policy_version: "C3_REQUIREMENT_COVERAGE_V1",
        verified_count: 0,
        partial_count: 0,
        unresolved_count: 1,
        requirements: [{
          requirement_id: "REQ-1",
          status: "UNRESOLVED",
          implementing_node_ids: [],
          verifying_node_ids: [],
          unresolved_link_ids: [],
        }],
        diagnostics: { missing_evidence: ["REQ-1 has no code evidence"] },
      },
    };
    seedSession({
      generationRun: { run: makeRun(), mode: "TEMPLATE_ONLY", durationMs: 1, at: "now" },
      graph: { snapshot, versions: [], fetchedAt: "now" },
    });
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/traceability/graphs/graph-1/versions/2/rtm": {
        graph_id: "graph-1",
        graph_version: 2,
        rows: [{ requirement_id: "REQ-1", requirement_label: "Create task", uml_elements: [], code_modules: [], api_operations: [], database_entities: [], test_hooks: [] }],
        table_markdown: "| Requirement | UML Elements |\n|:---|:---|\n| REQ-1 | — |",
      },
      "GET /api/v1/traceability/graphs/graph-1/versions/2/metrics": {
        report_version: "1.0",
        graph_id: "graph-1",
        graph_version: 2,
        total_requirements: 1,
        covered_requirements: 0,
        coverage_rate: 0,
        coverage_gaps: ["REQ-1"],
        total_active_nodes: 2,
        orphan_node_count: 1,
        orphan_rate: 0.5,
        orphan_node_ids: ["CODE_MODULE:ORPHAN"],
        diagnostics: [
          { code: "ORPHAN_DOWNSTREAM_NODE", severity: "REVIEW_REQUIRED", affected_ids: ["CODE_MODULE:ORPHAN"], message: "One orphan requires review." },
          { code: "REQUIREMENT_COVERAGE_GAP", severity: "REVIEW_REQUIRED", affected_ids: ["REQ-1"], message: "One requirement lacks code coverage." },
        ],
      },
    });
    render(<App />);
    await openPage(user, /Living Traceability/);

    await user.click(screen.getByRole("button", { name: "Load RTM and diagnostics" }));

    expect(await screen.findByText("ORPHAN_DOWNSTREAM_NODE")).toBeInTheDocument();
    expect(screen.getByText("REQUIREMENT_COVERAGE_GAP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export RTM JSON" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export RTM table" })).toBeEnabled();
    expect(called("GET /api/v1/traceability/graphs/graph-1/versions/2/rtm")).toHaveLength(1);
    expect(called("GET /api/v1/traceability/graphs/graph-1/versions/2/metrics")).toHaveLength(1);
  });
});

describe("Scoped regeneration", () => {
  const scopedSession = () => ({
    fixtures: { inputPackage: null, defectScenarios: DEFECT_FIXTURE, stackCriteria: null },
    scoped: { scenarioId: "SIM-SCN-001-service", baseline: makeBaseline(), impact: null, runs: [] },
  });

  // The baseline card previews the injected module on mount.
  const previewRoute = {
    "POST /api/v1/demo/code-preview": {
      relative_path: "backend/src/services/taskService.js",
      artifact_type: "SOURCE",
      origin: "LOCAL_LLM",
      sha256: "a".repeat(64),
      size_bytes: 10,
      truncated: false,
      content: "// defective",
    },
  };

  it("builds the defect report from the real baseline and calls the read-only impact API", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    const { called } = installFetch({
      ...baseRoutes(),
      ...previewRoute,
      "POST /api/v1/impact-selections": {
        status: "REVIEW_REQUIRED",
        graph_version: 3,
        automatic_scope_limit: 1,
        reason_codes: ["SCOPE_TOO_BROAD"],
        selected_modules: [],
        defects: [{ defect_id: "SIM-DEF-001", exclusions: [{ node_id: "N1", relative_path: "backend/src/app.js", reason_codes: ["NOT_ON_FAILING_TEST_OR_API_PATH"] }], excluded_links: [] }],
      },
    });
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Preview impact selection" }));

    const result = await screen.findByTestId("impact-result");
    expect(result).toHaveTextContent("SCOPE_TOO_BROAD");
    expect(result).toHaveTextContent("NOT_ON_FAILING_TEST_OR_API_PATH");
    expect(result).toHaveTextContent("No module was selected automatically");
    const report = called("POST /api/v1/impact-selections")[0].body.defect_report;
    expect(report).toMatchObject({
      source_classification: "SIMULATED_C4_FIXTURE",
      source_generation_run_id: "baseline-run",
      source_graph_version: 3,
    });
  });

  it("separates MOCK and REAL_LOCAL_OLLAMA endpoints and shows REVIEW_REQUIRED honestly", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    const { called } = installFetch({
      ...baseRoutes(),
      ...previewRoute,
      "POST /api/v1/demo/scoped-regenerations/mock": makeRegenerationResult({ status: "REVIEW_REQUIRED", mock: true }),
      "POST /api/v1/scoped-regenerations": makeRegenerationResult({ status: "REVIEW_REQUIRED", mock: false }),
    });
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run MOCK regeneration" }));
    await screen.findByTestId("regeneration-result");
    await user.click(screen.getByRole("button", { name: "Run REAL Ollama regeneration" }));
    await waitFor(() => expect(called("POST /api/v1/scoped-regenerations")).toHaveLength(1));

    expect(called("POST /api/v1/demo/scoped-regenerations/mock")).toHaveLength(1);
    const result = await screen.findByTestId("regeneration-result");
    expect(result).toHaveTextContent("REAL local Ollama");
    expect(result).toHaveTextContent("Review required");
    expect(result).toHaveTextContent("Repair success: NOT EVALUATED");
    expect(result).toHaveTextContent("No handoff was produced");
    expect(result).toHaveTextContent("C4 retest is still PENDING");
    expect(result).toHaveTextContent("RAGA-CHUNK-001");
    expect(result).toHaveTextContent("node-svc-001");
  });

  it("shows a stale-report conflict from the backend as an error", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    installFetch({
      ...baseRoutes(),
      ...previewRoute,
      "POST /api/v1/demo/scoped-regenerations/mock": () => jsonResponse({ errors: [{ code: "STALE_DEFECT_REPORT", field: "defect_report.source_graph_version", message: "The report is not for the latest graph version." }] }, 409),
    });
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run MOCK regeneration" }));

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("STALE_DEFECT_REPORT");
    expect(screen.queryByTestId("regeneration-result")).not.toBeInTheDocument();
  });

  it("disables run buttons until a defect fixture and a baseline exist", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Scoped Regeneration/);

    expect(screen.getByRole("button", { name: "Run MOCK regeneration" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run REAL Ollama regeneration" })).toBeDisabled();
    expect(screen.getAllByText("SIMULATED C4 DEFECT").length).toBeGreaterThan(0);
  });
});

describe("Readiness", () => {
  it("shows only a short hint, not the old gate report, when nothing is generated", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Readiness/);

    expect(screen.getByText("Nothing generated yet")).toBeInTheDocument();
    expect(screen.queryByText("Workflow gates")).not.toBeInTheDocument();
    expect(screen.queryByText("Deployment")).not.toBeInTheDocument();
  });
});

describe("URL routing and navigation", () => {
  it("renders C1/C2 inputs directly when URL path is /inputs", async () => {
    installFetch(baseRoutes());
    window.history.pushState({}, "", "/inputs");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "C1/C2 Inputs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 C1\/C2 Inputs/ })).toHaveClass("nav-active");
  });

  it("renders Design & Stack directly when URL path is /dashboard/designstack", async () => {
    installFetch(baseRoutes());
    window.history.pushState({}, "", "/dashboard/designstack");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Design & Stack" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2 Design & Stack/ })).toHaveClass("nav-active");
  });
});

