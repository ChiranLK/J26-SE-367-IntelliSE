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

    expect(await screen.findByText(/intelise-component-3 · ok/)).toBeInTheDocument();
    expect(screen.getByText("reachable · model installed")).toBeInTheDocument();
    expect(called("GET /api/v1/health")).toHaveLength(1);
    expect(called("GET /api/v1/demo/overview")).toHaveLength(1);
    expect(screen.getByText("SIMULATED FIXTURE")).toBeInTheDocument();
    expect(screen.getByText("NOT INTEGRATED")).toBeInTheDocument();
  });

  it("shows the API as unreachable instead of pretending it is healthy", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByText("unreachable")).toBeInTheDocument();
    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
    expect(screen.getByTestId("error-panel")).toHaveTextContent("Backend unreachable");
    expect(screen.getByText("Ollama unknown")).toBeInTheDocument();
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

    expect(await screen.findByText("reachable · model missing")).toBeInTheDocument();
    expect(screen.getByText("Local-model steps are unavailable")).toBeInTheDocument();
  });
});

describe("C1/C2 inputs", () => {
  it("loads the simulated fixture and sends exactly that package to the validation API", async () => {
    const user = userEvent.setup();
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/demo/fixtures/input-package": { fixture_id: "input-package", classification: "SIMULATED_C1_C2_FIXTURE", notice: "SIMULATED fixture notice", payload: INPUT_PACKAGE },
      "POST /api/v1/validate-input": GENERATION_CONTEXT,
    });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    await user.click(screen.getByRole("button", { name: "Load Task Management fixture" }));
    expect(await screen.findByText("SIMULATED fixture notice")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Validate C1/C2 inputs" }));

    expect(await screen.findByText("ACCEPTED by C3 validation")).toBeInTheDocument();
    expect(called("POST /api/v1/validate-input")[0].body).toEqual(INPUT_PACKAGE);
    expect(screen.getAllByText("SIMULATED C1/C2 FIXTURE").length).toBeGreaterThan(0);
  });

  it("shows the backend's validation errors and does not mark the input accepted", async () => {
    const user = userEvent.setup();
    installFetch({
      ...baseRoutes(),
      "GET /api/v1/demo/fixtures/input-package": { fixture_id: "input-package", classification: "SIMULATED_C1_C2_FIXTURE", notice: "n", payload: INPUT_PACKAGE },
      "POST /api/v1/validate-input": () => jsonResponse({ errors: [{ code: "REQUIREMENT_NOT_APPROVED", field: "c1.requirements[0].status", message: "Requirement REQ-1 is not approved." }] }, 422),
    });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    await user.click(screen.getByRole("button", { name: "Load Task Management fixture" }));

    await user.click(await screen.findByRole("button", { name: "Make a requirement DRAFT" }));
    await user.click(screen.getByRole("button", { name: "Validate C1/C2 inputs" }));

    const panel = await screen.findByTestId("error-panel");
    expect(panel).toHaveTextContent("REQUIREMENT_NOT_APPROVED");
    expect(panel).toHaveTextContent("HTTP 422");
    expect(panel).toHaveTextContent("Requirement REQ-1 is not approved.");
    expect(screen.queryByText("ACCEPTED by C3 validation")).not.toBeInTheDocument();
  });

  it("shows an unreachable-backend error during validation without fake data", async () => {
    const user = userEvent.setup();
    installFetch({
      ...baseRoutes(),
      "GET /api/v1/demo/fixtures/input-package": { fixture_id: "input-package", classification: "SIMULATED_C1_C2_FIXTURE", notice: "n", payload: INPUT_PACKAGE },
    });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);
    await user.click(screen.getByRole("button", { name: "Load Task Management fixture" }));
    await screen.findByRole("button", { name: "Validate C1/C2 inputs" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await user.click(screen.getByRole("button", { name: "Validate C1/C2 inputs" }));

    expect(await screen.findByTestId("error-panel")).toHaveTextContent("Backend unreachable");
    expect(screen.queryByText("ACCEPTED by C3 validation")).not.toBeInTheDocument();
  });

  it("combines separately pasted C1 and C2 outputs without inventing upstream fields", async () => {
    const user = userEvent.setup();
    const { called } = installFetch({
      ...baseRoutes(),
      "POST /api/v1/validate-input": GENERATION_CONTEXT,
    });
    render(<App />);
    await openPage(user, /C1\/C2 Inputs/);

    fireEvent.change(screen.getByLabelText("Component 1 JSON"), {
      target: { value: JSON.stringify(INPUT_PACKAGE.c1) },
    });
    fireEvent.change(screen.getByLabelText("Component 2 JSON"), {
      target: { value: JSON.stringify(INPUT_PACKAGE.c2) },
    });
    await user.click(screen.getByRole("button", { name: "Validate C1/C2 inputs" }));

    expect(await screen.findByText("ACCEPTED by C3 validation")).toBeInTheDocument();
    expect(called("POST /api/v1/validate-input")[0].body).toEqual(INPUT_PACKAGE);
    expect(screen.getAllByText("PASTED_OR_EDITED")).toHaveLength(2);
  });
});

describe("Code generation", () => {
  const approvedSession = () => ({
    validation: { ok: true, at: "2026-10-14T00:00:00Z", generationContext: GENERATION_CONTEXT },
    designContext: { design_context_version: "1.0" },
    stackReport: { selected_stack: {} },
    approval: { status: "APPROVED_FOR_MVP_GENERATION", approvedBy: "me", approvalReference: "ref", acknowledgesProvisionalPolicy: true },
  });

  it("explains the missing approval and keeps generation disabled", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Code Generation/);

    expect(screen.getByText("Approved stack required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate with/ })).toBeDisabled();
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

    await user.click(screen.getByRole("button", { name: "Generate with TEMPLATE_ONLY" }));

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

    await user.click(screen.getByLabelText(/LOCAL_LLM/));
    await user.click(screen.getByRole("button", { name: "Generate with LOCAL_LLM" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Generating (LOCAL_LLM)");
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
  it("blocks custom non-CRUD generation instead of substituting an unrelated CRUD app", async () => {
    const user = userEvent.setup();
    seedSession({ validation: { ok: true, generationContext: GENERATION_CONTEXT } });
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /Design & Stack/);

    await user.click(screen.getByRole("button", { name: /Custom \/ non-CRUD application/ }));

    expect(screen.getByText("Custom generation is not implemented yet")).toBeInTheDocument();
    expect(screen.getByText(/will not silently generate an unrelated CRUD application/)).toBeInTheDocument();
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
  it("shows C4 retest pending or not run, and deployment blocked, without any approval", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Readiness/);

    expect(screen.getAllByText("DEPLOYMENT BLOCKED").length).toBeGreaterThan(0);
    expect(screen.getByText("C4 RETEST PENDING")).toBeInTheDocument();
    expect(screen.getByTestId("deployment-blockers")).toHaveTextContent("Independent C4 retest evidence is missing.");
    expect(screen.queryByText(/approved for deployment/i)).not.toBeInTheDocument();
  });
});
