import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../src/App.jsx";
import { acceptanceFrom, ragRows, traceChains } from "../src/lib/hybrid.js";
import { baseRoutes, installFetch, jsonResponse, seedSession } from "./helpers.js";

// Response bodies below are test inputs standing in for the C3 API; they are not
// evidence about real generation, Docker or Component 4 behaviour.

const GRAPH = {
  version: 1,
  nodes: [
    { node_id: "REQUIREMENT:REQ-GPA-102", node_type: "REQUIREMENT", key: "REQ-GPA-102", attributes: { requirement_version: 1, requirement_type: "FR" } },
    { node_id: "UML_ELEMENT:UML-1#GpaCalculationService", node_type: "UML_ELEMENT", key: "UML-1#GpaCalculationService", attributes: {} },
    { node_id: "MODULE:be.service", node_type: "MODULE", key: "be.service", attributes: {} },
    { node_id: "MODULE:docs", node_type: "MODULE", key: "docs", attributes: {} },
    { node_id: "CODE_FILE:backend/src/services/gpaCalculationService.js", node_type: "CODE_FILE", key: "backend/src/services/gpaCalculationService.js", attributes: {} },
    { node_id: "RULE:R-GPA-CALC-001", node_type: "RULE", key: "R-GPA-CALC-001", attributes: {} },
    { node_id: "API_OPERATION:calculateGpa", node_type: "API_OPERATION", key: "calculateGpa", attributes: {} },
    { node_id: "TEST_SEAM:SEAM-GPA-SERVICE", node_type: "TEST_SEAM", key: "SEAM-GPA-SERVICE", attributes: {} },
  ],
  links: [
    { source: "REQUIREMENT:REQ-GPA-102", relation: "DESIGNED_BY", target: "UML_ELEMENT:UML-1#GpaCalculationService", status: "ACTIVE", evidence: "DIRECT" },
    { source: "REQUIREMENT:REQ-GPA-102", relation: "IMPLEMENTED_BY", target: "MODULE:be.service", status: "ACTIVE", evidence: "DIRECT" },
    { source: "REQUIREMENT:REQ-GPA-102", relation: "IMPLEMENTED_BY", target: "MODULE:docs", status: "ACTIVE", evidence: "HOSTING_CLOSURE" },
    { source: "MODULE:be.service", relation: "CONTAINS", target: "CODE_FILE:backend/src/services/gpaCalculationService.js", status: "ACTIVE" },
    { source: "RULE:R-GPA-CALC-001", relation: "PRODUCED", target: "CODE_FILE:backend/src/services/gpaCalculationService.js", status: "ACTIVE" },
    { source: "REQUIREMENT:REQ-GPA-102", relation: "EXPOSED_BY", target: "API_OPERATION:calculateGpa", status: "ACTIVE" },
    { source: "REQUIREMENT:REQ-GPA-102", relation: "VERIFIED_THROUGH", target: "TEST_SEAM:SEAM-GPA-SERVICE", status: "ACTIVE" },
    { source: "REQUIREMENT:REQ-GPA-102", relation: "EXPOSED_BY", target: "API_OPERATION:old", status: "SUPERSEDED" },
  ],
};

describe("hybrid derivations", () => {
  it("builds requirement chains from ACTIVE direct links only", () => {
    const [chain] = traceChains(GRAPH);
    expect(chain.requirementId).toBe("REQ-GPA-102");
    expect(chain.modules).toEqual(["be.service"]);
    expect(chain.rules).toEqual(["R-GPA-CALC-001"]);
    expect(chain.api).toEqual(["calculateGpa"]);
    expect(chain.seams).toEqual(["SEAM-GPA-SERVICE"]);
  });

  it("summarizes RAG rows and acceptance without inventing values", () => {
    expect(ragRows({ rag: { retrievals: [{ module_id: "m", applied_to_prompt: false, hits: [{ chunk_id: "c", version: "1", score: 3 }] }] } }))
      .toEqual([{ key: "m:c", module: "m", chunk: "c", version: "1", score: 3, applied: false }]);
    expect(acceptanceFrom({ policy_id: "P", policy_version: "1", policy_digest_sha256: "d", authority_status: "SAMPLE_RESEARCH_POLICY" }, "me"))
      .toMatchObject({ acknowledges_sample_status: true, accepted_by: "me" });
    expect(acceptanceFrom(null, "me")).toBeNull();
  });
});

const OVERVIEW = {
  pp1_scope: {},
  knowledge_base: {
    kb_version: "1.0.0",
    kb_digest_sha256: "a".repeat(64),
    gpa_policy: {
      policy_id: "SLIIT-UG-GPA-SAMPLE", policy_version: "1.0.0", authority_status: "SAMPLE_RESEARCH_POLICY",
      authority_status_reason: "Research transcription, not institution-approved.", sources: [],
    },
  },
  rule_set: { rule_set_version: "1.0.0", rule_set_digest_sha256: "b".repeat(64), rules: [{}, {}] },
  policy_acceptance_template: { policy_id: "SLIIT-UG-GPA-SAMPLE", policy_version: "1.0.0", policy_digest_sha256: "c".repeat(64), authority_status: "SAMPLE_RESEARCH_POLICY" },
};

const RUN = {
  generation_run_id: "run-gpa-1",
  status: "ACCEPTED",
  manifest: {
    artifact_digest_sha256: "d".repeat(64),
    input: { project_id: "PROJECT-GPA-HYBRID-001" },
    modules: [{ module_id: "be.service", layer: "SERVICE", origin: "TEMPLATE", files: ["x.js"], direct_requirement_ids: ["REQ-GPA-102"], module_digest_sha256: "e".repeat(64) }],
    files: [
      { path: "README.md", size_bytes: 1273 },
      { path: "frontend/src/App.jsx", size_bytes: 1215 },
      { path: "frontend/src/components/HistoryList.jsx", size_bytes: 624 },
      { path: "backend/src/services/gpaCalculationService.js", size_bytes: 3290 },
      { path: "database/migrations/001_create_gpa_calculations.sql", size_bytes: 1143 },
      { path: "deployment/backend.Dockerfile", size_bytes: 744 },
    ],
    rule_set: { selected_rules: ["R-GPA-CALC-001@1.0.0"] },
    stack: { stack_id: "react-nodejs", frontend: "REACT", backend: "NODE_JS", database: "POSTGRESQL", reason: "top score", criteria_source: "SIMULATED_RESEARCHER_CRITERIA" },
    templates: { template_set: "c3-gpa-react-node-postgres@1.0.0" },
    llm: { provider: "openrouter", configured_model: "m", prompt_version: "p", calls: 0, cache_hits: 0, prompt_tokens: 0, completion_tokens: 0, ledger: [], deterministic_modules: ["be.service"], model_modules: [] },
    rag: { retrievals: [{ module_id: "be.service", applied_to_prompt: false, hits: [{ chunk_id: "node-svc-001#node-svc-001", version: "1.0.0", score: 41 }] }] },
    review_items: [],
  },
  verification: {
    design_to_code: { status: "PASS", pass_count: 10, review_count: 0, fail_count: 0, findings: [] },
    architecture: { status: "PASS", pass_count: 1, review_count: 0, fail_count: 0, findings: [] },
  },
};

const PREVIEW = {
  preview_id: "ihp-1",
  status: "RUNNING",
  execution: "LOCAL_SANDBOX_PREVIEW_NOT_DEPLOYED",
  generation_run_id: "run-gpa-1",
  artifact_digest_sha256: "d".repeat(64),
  frontend_url: "http://127.0.0.1:51001",
  api_url: "http://127.0.0.1:51002",
  api_health_url: "http://127.0.0.1:51002/api/health",
  started_at_utc: "2026-10-20T10:00:00Z",
  container_name: "ihp-1-web / ihp-1-api / ihp-1-db",
  database_exposure: "NOT_PUBLISHED (internal Docker network only)",
  health: { api_healthy: true, frontend_healthy: true, api_health_body: { status: "UP", database: "UP" } },
  isolation: ["non-root users"],
};

describe("GPA generation on the Code Generation page", () => {
  it("generates from the uploaded C1/C2 2.0 files when they are there, not from the sample", async () => {
    const user = userEvent.setup();
    const c1 = { contract_version: "2.0", project_id: "PROJECT-GPA-HYBRID-001" };
    const c2 = { contract_version: "2.0", project_id: "PROJECT-GPA-HYBRID-001" };
    seedSession({ behaviourRun: { run: { manifest: {} } }, sourceDocuments: { c1Name: "my_c1.json", c1Text: JSON.stringify(c1), c2Name: "my_c2.json", c2Text: JSON.stringify(c2) } });
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "POST /api/v1/hybrid/contracts/validate": {
        status: "ACCEPTED", input_classification: "VALIDATED_CONTRACT_INPUT", project_id: "PROJECT-GPA-HYBRID-001", srs_version: "SRS-GPA-2.0",
        uml_version: "UML-GPA-2.0", rule_ids: [], findings: [],
      },
      "POST /api/v1/hybrid/runs": RUN,
      "GET /api/v1/hybrid/runs/run-gpa-1/location": { run_id: "run-gpa-1", path: "C:/work/run-gpa-1/generated-project" },
      "GET /api/v1/hybrid/projects/PROJECT-GPA-HYBRID-001/trace": { graph: GRAPH, coverage: { traced_count: 1, total: 1, orphan_artifacts: [] } },
    });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Code Generation/ }));

    await user.click(await screen.findByRole("button", { name: "Generate project" }));
    expect(await screen.findByText("run-gpa-1")).toBeInTheDocument();
    expect(called("GET /api/v1/hybrid/fixtures/gpa-input")).toHaveLength(0);
    expect(called("POST /api/v1/hybrid/runs")[0].body.package).toEqual({ contract_version: "2.0", input_classification: "VALIDATED_CONTRACT_INPUT", c1, c2 });
  });

  it("generates the GPA project with one click and records the acceptance", async () => {
    const user = userEvent.setup();
    seedSession({ behaviourRun: { run: { manifest: {} } } }); // the card appears after a generation has finished
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/fixtures/gpa-input": { payload: { contract_version: "2.0" } },
      "POST /api/v1/hybrid/contracts/validate": {
        status: "ACCEPTED", input_classification: "VALIDATED_CONTRACT_INPUT", c1_evidence_class: "SIMULATED_FIXTURE",
        c2_evidence_class: "SIMULATED_FIXTURE", project_id: "PROJECT-GPA-HYBRID-001", srs_version: "SRS-GPA-2.0",
        uml_version: "UML-GPA-2.0", rule_ids: ["R-INPUT-001@1.0.0"], findings: [],
      },
      "POST /api/v1/hybrid/runs": RUN,
      "GET /api/v1/hybrid/runs/run-gpa-1/location": { run_id: "run-gpa-1", path: "C:/work/hybrid/gpa-dashboard/run-gpa-1/generated-project" },
      "POST /api/v1/hybrid/runs/run-gpa-1/open-folder": { run_id: "run-gpa-1", opened: true },
      "GET /api/v1/hybrid/projects/PROJECT-GPA-HYBRID-001/trace": { graph: GRAPH, coverage: { traced_count: 1, total: 1, orphan_artifacts: [] } },
    });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Code Generation/ }));
    expect(screen.queryByText(/Hybrid/i)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Generate project" }));
    expect(await screen.findByText("run-gpa-1")).toBeInTheDocument();
    expect(screen.getByText("ACCEPTED", { selector: "span" })).toBeInTheDocument();
    const request = called("POST /api/v1/hybrid/runs")[0].body;
    expect(request.policy_acceptance).toMatchObject({ policy_id: "SLIIT-UG-GPA-SAMPLE", acknowledges_sample_status: true, accepted_by: "researcher (dashboard)" });
    expect(request.allow_llm_for_unsupported).toBe(false);
    expect(request.llm_backend_logic).toBe(false);
    expect(request.llm_frontend).toBe(false);

    // the generated project as a folder tree with a zip of exactly these files
    expect(screen.getByTestId("project-zip")).toHaveAttribute("href", "/api/v1/hybrid/runs/run-gpa-1/archive");
    expect(screen.getByText(/6 files in 4 folders/)).toBeInTheDocument();
    expect(await screen.findByTestId("project-location")).toHaveTextContent("C:/work/hybrid/gpa-dashboard/run-gpa-1/generated-project");
    await user.click(screen.getByRole("button", { name: "Open folder" }));
    await waitFor(() => expect(called("POST /api/v1/hybrid/runs/run-gpa-1/open-folder")).toHaveLength(1));
    const tree = screen.getByTestId("project-tree");
    expect(within(tree).getByTestId("project-folder-frontend/src/components")).toHaveTextContent("Screens and widgets");
    expect(within(tree).getByText("gpaCalculationService.js")).toBeInTheDocument();
    expect(within(tree).getByText("Computes the credit-weighted GPA with half-up rounding.")).toBeInTheDocument();
    expect(within(tree).getByText("001_create_gpa_calculations.sql")).toBeInTheDocument();
    expect(within(tree).getByText("generation-manifest.json")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse all folders" }));
    expect(screen.getByRole("button", { name: "Expand all folders" })).toBeInTheDocument();
  });
});

describe("Hybrid run in the preview", () => {
  it("finds the running preview on the Application Preview page, checks it and stops it", async () => {
    const user = userEvent.setup();
    seedSession({ hybrid: { run: RUN } });
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/preview": { docker: { available: true }, previews: [PREVIEW] },
      "POST /api/v1/hybrid/preview/ihp-1/gpa-check": {
        passed: true, expected_gpa_text: "3.42", observed_gpa_text: "3.42", derivation: "41.0 / 12", classification: "C3_GENERATED_APP_SMOKE_CHECK",
      },
      "POST /api/v1/hybrid/preview/stop": { ...PREVIEW, status: "STOPPED", frontend_url: null, api_url: null, containers: [] },
    });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Application Preview/ }));
    const link = await screen.findByTestId("preview-frontend-url");
    expect(link).toHaveAttribute("href", "http://127.0.0.1:51001");
    expect(screen.getByTestId("preview-api-url")).toHaveAttribute("href", "http://127.0.0.1:51002/api/health");
    expect(screen.getByTestId("open-generated-app")).toHaveAttribute("target", "_blank");
    await user.click(screen.getByRole("button", { name: "Run known GPA check" }));
    expect(await screen.findByText("The app gives the right answer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(called("POST /api/v1/hybrid/preview/stop")[0].body).toEqual({ preview_id: "ihp-1" }));
    expect(await screen.findByRole("button", { name: "Start preview" })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ workflow pages fed by the Hybrid run
const GRAPH_WITH_LABELS = {
  ...GRAPH,
  nodes: GRAPH.nodes.map((node) =>
    node.key === "REQ-GPA-102" ? { ...node, label: "Calculate credit-weighted GPA" }
      : node.key === "calculateGpa" ? { ...node, label: "POST /api/v1/gpa/calculations" } : node),
};

const openPage = async (user, name) =>
  user.click(within(screen.getByRole("navigation")).getByRole("button", { name }));

describe("workflow pages use the Hybrid GPA run", () => {
  const hybridSession = (extra = {}) => seedSession({ hybrid: { run: RUN, trace: { graph: GRAPH_WITH_LABELS, coverage: { traced_count: 1, total: 1, orphan_artifacts: [] } }, ...extra } });

  it("Living Traceability shows each requirement with plain-language code, API and test hooks", async () => {
    const user = userEvent.setup();
    hybridSession();
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);
    await openPage(user, /Living Traceability/);
    expect(await screen.findByText("Showing your GPA project run")).toBeInTheDocument();
    expect(screen.getByText("Calculate credit-weighted GPA")).toBeInTheDocument();
    expect(screen.getByText("GPA calculation service")).toBeInTheDocument();
    expect(screen.getByText("POST /api/v1/gpa/calculations")).toBeInTheDocument();
    expect(screen.getByText("SEAM-GPA-SERVICE")).toBeInTheDocument();
    expect(screen.queryByText("Generation run required")).not.toBeInTheDocument();
  });

  it("Application Preview offers the running app and a known-answer check", async () => {
    const user = userEvent.setup();
    hybridSession({ preview: PREVIEW });
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/preview": { docker: { available: true }, previews: [PREVIEW] },
      "POST /api/v1/hybrid/preview/ihp-1/gpa-check": { passed: true, expected_gpa_text: "3.42", observed_gpa_text: "3.42", derivation: "41.0 / 12" },
    });
    render(<App />);
    await openPage(user, /Application Preview/);
    expect(await screen.findByRole("link", { name: "Open the GPA Calculator" })).toHaveAttribute("href", "http://127.0.0.1:51001");
    expect(screen.getByText("Things to try")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run known GPA check" }));
    expect(await screen.findByText("The app gives the right answer")).toBeInTheDocument();
    expect(called("POST /api/v1/hybrid/preview/ihp-1/gpa-check")).toHaveLength(1);
  });

  it("Application Preview warns when the running preview belongs to an older run", async () => {
    const user = userEvent.setup();
    const older = { ...PREVIEW, generation_run_id: "older-run" };
    hybridSession({ preview: older });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW, "GET /api/v1/hybrid/preview": { docker: { available: true }, previews: [older] } });
    render(<App />);
    await openPage(user, /Application Preview/);
    expect(await screen.findByText("This preview shows an earlier version of the app")).toBeInTheDocument();
  });

  it("Application Preview replaces an earlier-version preview: stops it, then starts the current run", async () => {
    const user = userEvent.setup();
    const older = { ...PREVIEW, generation_run_id: "older-run" };
    hybridSession({ preview: older });
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/preview": { docker: { available: true }, previews: [older] },
      "POST /api/v1/hybrid/preview/stop": { ...older, status: "STOPPED", frontend_url: null, api_url: null, containers: [] },
      "POST /api/v1/hybrid/preview/start": { ...PREVIEW, preview_id: "ihp-2", generation_run_id: RUN.generation_run_id },
    });
    render(<App />);
    await openPage(user, /Application Preview/);

    await user.click(await screen.findByRole("button", { name: "Replace with the current version" }));

    await waitFor(() => expect(called("POST /api/v1/hybrid/preview/start")).toHaveLength(1));
    expect(called("POST /api/v1/hybrid/preview/stop")[0].body).toEqual({ preview_id: "ihp-1" });
    expect(await screen.findByText("Your app is running")).toBeInTheDocument();
  });

  it("Application Preview forgets a remembered preview that the backend no longer runs", async () => {
    const user = userEvent.setup();
    hybridSession({ preview: { ...PREVIEW, generation_run_id: "older-run" } });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW, "GET /api/v1/hybrid/preview": { docker: { available: true }, previews: [] } });
    render(<App />);
    await openPage(user, /Application Preview/);
    expect(await screen.findByRole("button", { name: "Start preview" })).toBeInTheDocument();
    expect(screen.queryByText("This preview shows an earlier version of the app")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open the GPA Calculator" })).not.toBeInTheDocument();
  });

  it("Application Preview explains when Docker is not running", async () => {
    const user = userEvent.setup();
    hybridSession();
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW, "GET /api/v1/hybrid/preview": { docker: { available: false }, previews: [] } });
    render(<App />);
    await openPage(user, /Application Preview/);
    expect(await screen.findByText("Docker is not running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start preview" })).toBeInTheDocument();
    expect(screen.queryByText("Things to try")).not.toBeInTheDocument();
  });

  it("Scoped Regeneration applies an approved change and summarises it in plain words", async () => {
    const user = userEvent.setup();
    hybridSession();
    const change = {
      generation_run_id: "run-gpa-2", status: "ACCEPTED",
      manifest: { input: { project_id: "PROJECT-GPA-HYBRID-001" }, lineage: {
        changed_requirement_ids: ["REQ-GPA-104"], impact_set: ["be.service", "fe.app-shell"],
        preservation: [{ path: "a.js", state: "REGENERATED_CHANGED" }, { path: "b.js", state: "PRESERVED_UNTOUCHED" }, { path: "c.js", state: "PRESERVED_UNTOUCHED" }, { path: "d.js", state: "REGENERATED_IDENTICAL" }] } },
      c4_handoff: { retest_status: "PENDING" },
    };
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/fixtures/gpa-input-req104-v2": { payload: { contract_version: "2.0" } },
      "POST /api/v1/hybrid/regenerations/requirement-change": change,
      "GET /api/v1/hybrid/projects/PROJECT-GPA-HYBRID-001/trace": { graph: { ...GRAPH_WITH_LABELS, version: 2 }, coverage: { traced_count: 1, total: 1, orphan_artifacts: [] } },
    });
    render(<App />);
    await openPage(user, /Scoped Regeneration/);
    const button = await screen.findByRole("button", { name: /let the user clear the history/ });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    expect(await screen.findByText("Requirement change applied")).toBeInTheDocument();
    expect(screen.getByText("GPA calculation service")).toBeInTheDocument();
    expect(screen.getByText("Frontend shell")).toBeInTheDocument();
    expect(called("POST /api/v1/hybrid/regenerations/requirement-change")[0].body).toMatchObject({ base_generation_run_id: "run-gpa-1" });
  });

  it("Scoped Regeneration turns a stale-run error into a sentence a person can act on", async () => {
    const user = userEvent.setup();
    hybridSession();
    installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "GET /api/v1/hybrid/fixtures/gpa-input-req103-v2": { payload: {} },
      "POST /api/v1/hybrid/regenerations/requirement-change": () => new Response(JSON.stringify({ errors: [{ code: "STALE_BASE_RUN", field: null, message: "stale" }] }), { status: 409, headers: { "content-type": "application/json" } }),
    });
    render(<App />);
    await openPage(user, /Scoped Regeneration/);
    const button = await screen.findByRole("button", { name: /module code must look like/ });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    expect(await screen.findByText(/A newer version of this project already exists/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to Code Generation" })).toBeInTheDocument();
  });

  it("Readiness lists the checks and keeps deployment blocked without showing a deployment gate", async () => {
    const user = userEvent.setup();
    hybridSession();
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);
    await openPage(user, /Readiness/);
    expect(await screen.findByText("Code matches the design")).toBeInTheDocument();
    expect(screen.getByText("10 pass · 0 review · 0 fail")).toBeInTheDocument();
    expect(screen.queryByText("DEPLOYMENT BLOCKED")).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing your GPA project run/)).not.toBeInTheDocument();
    expect(screen.queryByText("Deployment gate")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /C4 sign-off/ })).not.toBeInTheDocument();
  });

  it("Readiness shows the run evidence and an audit report button", async () => {
    const user = userEvent.setup();
    hybridSession({ contract: { status: "ACCEPTED", classification: "VALIDATED_CONTRACT_INPUT", project_id: "PROJECT-GPA-HYBRID-001", srs_version: "SRS-GPA-2.0", uml_version: "UML-GPA-2.0" } });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);
    await openPage(user, /Readiness/);
    expect(await screen.findByText("Run evidence")).toBeInTheDocument();
    expect(await screen.findByText("SLIIT-UG-GPA-SAMPLE v1.0.0")).toBeInTheDocument();
    expect(screen.getByText(/react-nodejs \(REACT \+ NODE_JS \+ POSTGRESQL\)/)).toBeInTheDocument();
    expect(screen.getByTestId("audit-report")).toHaveAttribute("href", "/api/v1/hybrid/runs/run-gpa-1/audit");
  });

  it("an empty session points at Code Generation instead of a dead end", async () => {
    const user = userEvent.setup();
    installFetch({ ...baseRoutes() });
    render(<App />);
    await openPage(user, /Living Traceability/);
    expect(await screen.findByText("Using the GPA project?")).toBeInTheDocument();
  });
});

describe("GPA project input errors", () => {
  it("explains a not-allowed evidence_class in plain words", async () => {
    const user = userEvent.setup();
    const c1 = { contract_version: "2.0", evidence_class: "FIXTURE" };
    const c2 = { contract_version: "2.0", evidence_class: "FIXTURE" };
    seedSession({ behaviourRun: { run: { manifest: {} } }, sourceDocuments: { c1Name: "c1.json", c1Text: JSON.stringify(c1), c2Name: "c2.json", c2Text: JSON.stringify(c2) } });
    installFetch({
      ...baseRoutes(),
      "GET /api/v1/hybrid/overview": OVERVIEW,
      "POST /api/v1/hybrid/contracts/validate": () => jsonResponse({ errors: [
        { code: "SCHEMA_VALIDATION_ERROR", field: "c1.evidence_class", message: "Input should be 'SIMULATED_FIXTURE' or 'UPSTREAM_COMPONENT_OUTPUT'" },
        { code: "SCHEMA_VALIDATION_ERROR", field: "c2.evidence_class", message: "Input should be 'SIMULATED_FIXTURE' or 'UPSTREAM_COMPONENT_OUTPUT'" },
      ] }, 422),
    });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Code Generation/ }));
    await user.click(await screen.findByRole("button", { name: "Generate project" }));

    const help = await screen.findByTestId("evidence-class-help");
    expect(help).toHaveTextContent("C1 and C2 file: the evidence_class value is not allowed.");
    expect(help).toHaveTextContent('C1 has "FIXTURE"');
  });
});

describe("Workflow ticks in the sidebar", () => {
  const trace = { graph: { version: 1, nodes: [], links: [] }, coverage: { traced_count: 1, total: 1, orphan_artifacts: [] } };
  const sidebarStep = (name) => within(screen.getByRole("navigation", { name: "Demo workflow" })).getByRole("button", { name });

  it("ticks Traceability after generation but not Readiness until the preview of that run is running", async () => {
    seedSession({ hybrid: { run: RUN, trace } });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);

    await screen.findByRole("navigation", { name: "Demo workflow" });
    expect(sidebarStep(/Living Traceability/)).toHaveClass("nav-done");
    expect(sidebarStep(/Readiness/)).not.toHaveClass("nav-done");
    expect(sidebarStep(/Application Preview/)).not.toHaveClass("nav-done");
  });

  it("ticks Readiness once the run, its trace and its running preview all exist", async () => {
    seedSession({ hybrid: { run: RUN, trace, preview: { ...PREVIEW, status: "RUNNING", generation_run_id: RUN.generation_run_id } } });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);

    await screen.findByRole("navigation", { name: "Demo workflow" });
    expect(sidebarStep(/Readiness/)).toHaveClass("nav-done");
  });
});

describe("GPA project card visibility", () => {
  it("is hidden until a generation has finished", async () => {
    const user = userEvent.setup();
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Code Generation/ }));

    expect(screen.queryByRole("button", { name: "Generate project" })).not.toBeInTheDocument();
  });

  it("appears once a generation has been tried, even when it did not finish", async () => {
    const user = userEvent.setup();
    seedSession({ generationAttempted: true });
    installFetch({ ...baseRoutes(), "GET /api/v1/hybrid/overview": OVERVIEW });
    render(<App />);
    await user.click(within(screen.getByRole("navigation")).getByRole("button", { name: /Code Generation/ }));

    expect(await screen.findByRole("button", { name: "Generate project" })).toBeInTheDocument();
  });
});
