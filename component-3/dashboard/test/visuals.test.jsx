import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../src/App.jsx";
import { api } from "../src/api/endpoints.js";
import { EvidenceChip } from "../src/components/visuals.jsx";
import { ModeBadge } from "../src/components/ui.jsx";
import { buildUnifiedDiff } from "../src/lib/diff.js";
import { buildTimeline } from "../src/lib/timeline.js";
import {
  DEFECT_FIXTURE,
  baseRoutes,
  installFetch,
  jsonResponse,
  makeBaseline,
  makeRegenerationResult,
  makeRun,
  seedSession,
} from "./helpers.js";

const nav = () => within(screen.getByRole("navigation"));
const openPage = async (user, name) => user.click(nav().getByRole("button", { name }));

beforeEach(() => {
  window.history.pushState({}, "", "/dashboard");
});

// ----------------------------------------------------------------- pure helpers

describe("buildUnifiedDiff", () => {
  it("marks added and removed lines with old/new line numbers and a hunk header", () => {
    const diff = buildUnifiedDiff("a\nold\nc\n", "a\nnew1\nnew2\nc\n");

    expect(diff.added).toBe(2);
    expect(diff.removed).toBe(1);
    expect(diff.hunks).toHaveLength(1);
    expect(diff.hunks[0].header).toBe("@@ -1,3 +1,4 @@");
    expect(diff.hunks[0].lines.map((line) => [line.type, line.oldNo, line.newNo, line.text])).toEqual([
      ["ctx", 1, 1, "a"],
      ["del", 2, null, "old"],
      ["add", null, 2, "new1"],
      ["add", null, 3, "new2"],
      ["ctx", 3, 4, "c"],
    ]);
  });

  it("reports no hunks for identical text", () => {
    expect(buildUnifiedDiff("x\ny\n", "x\ny\n")).toMatchObject({ hunks: [], added: 0, removed: 0 });
  });
});

describe("buildTimeline", () => {
  const session = (extra = {}) => ({ inputSources: {}, scoped: { runs: [] }, generationRun: null, ...extra });

  it("shows every stage as NOT_RUN when nothing was called (no invented values)", () => {
    const stages = buildTimeline([], session());

    expect(stages).toHaveLength(7);
    expect(stages.every((stage) => stage.status === "NOT_RUN")).toBe(true);
    expect(stages.every((stage) => stage.durationMs === undefined)).toBe(true);
  });

  it("takes status and duration from logged calls and labels evidence", () => {
    const log = [
      { method: "POST", path: "/validate-input", ok: true, status: 200, durationMs: 42, at: "t" },
      { method: "POST", path: "/design-context", ok: false, status: 422, errorCode: "UNSUPPORTED_PLANTUML_CONSTRUCT", durationMs: 7, at: "t" },
    ];
    const stages = buildTimeline(log, session({ inputSources: { c1: "SIMULATED_FIXTURE", c2: "SIMULATED_FIXTURE" } }));

    expect(stages[0]).toMatchObject({ id: "input", status: "DONE", durationMs: 42, evidence: { kind: "simulated" } });
    expect(stages[1]).toMatchObject({ id: "design", status: "REFUSED", durationMs: 7 });
    expect(stages[1].detail).toContain("UNSUPPORTED_PLANTUML_CONSTRUCT");
    expect(stages[6]).toMatchObject({ id: "retest", status: "NOT_RUN", evidence: { kind: "none" } });
  });
});

describe("evidence colour code", () => {
  it("uses real=green, simulated=amber, mock=purple, not integrated=red/grey classes", () => {
    render(
      <div>
        <EvidenceChip kind="real" />
        <EvidenceChip kind="simulated" />
        <EvidenceChip kind="mock" />
        <EvidenceChip kind="none" />
        <ModeBadge mode="MOCK" />
        <ModeBadge mode="REAL_LOCAL_OLLAMA" />
      </div>,
    );

    expect(screen.getByText("REAL", { selector: ".badge" })).toHaveClass("badge-real");
    expect(screen.getByText("SIMULATED")).toHaveClass("badge-sim");
    expect(screen.getByText("MOCKED_TEST_DOUBLE")).toHaveClass("badge-mock");
    expect(screen.getByText("NOT INTEGRATED")).toHaveClass("badge-bad-soft");
    expect(screen.getByText("MOCK model")).toHaveClass("badge-mock");
    expect(screen.getByText("REAL local Ollama")).toHaveClass("badge-real");
  });
});

// ----------------------------------------------------------------- scoped regeneration

const SERVICE = "backend/src/services/taskService.js";
const BEFORE = "a\nold\nc\n";
const AFTER = "a\nnew1\nnew2\nc\n";

const patchedResult = () => ({
  ...makeRegenerationResult({ status: "PATCHED_PENDING_INDEPENDENT_RETEST", mock: true }),
  patches: [{ relative_path: SERVICE, lines_added: 2, lines_removed: 1, source_size_bytes: 10, new_size_bytes: 20, attempts_used: 1 }],
  patch_attempts: [{ relative_path: SERVICE, attempt_number: 1, accepted: true, rejection_code: null, model_identifier: "test", client_inference_latency_ms: 5, prompt_template_version: "v" }],
  artifact_versioning: {
    source_generation_run_id: "baseline-run",
    new_generation_run_id: "new-run",
    source_workspace_relative_path: "demo/baseline-run",
    new_workspace_relative_path: "demo/new-run",
    source_artifact_digest_sha256: "1".repeat(64),
    new_artifact_digest_sha256: "2".repeat(64),
    source_run_preserved: true,
  },
  preservation: {
    unchanged_file_count: 2,
    changed_file_count: 1,
    collateral_edit_count: 0,
    all_unselected_files_byte_identical: true,
    entries: [
      { relative_path: SERVICE, selected: true, byte_identical: false, source_sha256: "a".repeat(64), new_sha256: "b".repeat(64) },
      { relative_path: "backend/src/app.js", selected: false, byte_identical: true, source_sha256: "c".repeat(64), new_sha256: "c".repeat(64) },
      { relative_path: "package.json", selected: false, byte_identical: true, source_sha256: "d".repeat(64), new_sha256: "d".repeat(64) },
    ],
  },
  graph_versioning: {
    graph_id: "g-1",
    base_graph_version: 1,
    new_graph_version: 2,
    base_graph_content_digest_sha256: "3".repeat(64),
    new_graph_content_digest_sha256: "4".repeat(64),
    change_report: { artifacts: { changed: [SERVICE], unchanged: [] }, preserved_link_ids: [], revalidated_link_ids: [], added_link_ids: [], retired_link_ids: [] },
  },
  c4_retest_handoff: {
    retest_status: "PENDING",
    independent_c4_evidence: "NONE",
    repair_verification: "NOT_ASSERTED_PENDING_INDEPENDENT_C4_RETEST",
    requirement_ids_to_retest: ["REQ-1"],
    failing_tests_to_rerun: [],
    changed_modules: [SERVICE],
    unchanged_module_count: 2,
    required_c4_actions: ["RERUN_FAILING_TESTS"],
  },
  metrics: {
    total_latency_ms: 1,
    llm_call_count: 0,
    rejected_attempt_count: 0,
    within_request_attempt_count: 1,
    within_request_attempt_limit: 2,
    repair_success: "NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST",
  },
});

const previewBody = (content) => ({
  relative_path: SERVICE,
  artifact_type: "SOURCE",
  origin: "LOCAL_LLM",
  sha256: "a".repeat(64),
  size_bytes: 10,
  truncated: false,
  content,
});

const scopedSession = () => ({
  fixtures: { inputPackage: null, defectScenarios: DEFECT_FIXTURE, stackCriteria: null },
  scoped: { scenarioId: "SIM-SCN-001-service", baseline: makeBaseline(), impact: null, runs: [] },
});

const scopedRoutes = (overrides = {}) => ({
  ...baseRoutes(),
  "POST /api/v1/demo/workspace-run": (body) => makeRun({ runId: body.workspace_relative_path.split("/")[1] }),
  "POST /api/v1/demo/code-preview": (body) =>
    previewBody(body.workspace_relative_path === "demo/new-run" ? AFTER : BEFORE),
  ...overrides,
});

describe("Scoped regeneration outcome board", () => {
  it("shows the file grid, headline, diff, validator verdict and C4 handoff for a patched run", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    installFetch(scopedRoutes({ "POST /api/v1/demo/scoped-regenerations/mock": patchedResult() }));
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run MOCK regeneration" }));

    const headline = await screen.findByTestId("outcome-headline");
    expect(headline).toHaveTextContent("1 of 3 files changed");
    expect(headline).toHaveTextContent("graph v1 → v2");
    const tiles = screen.getAllByTestId("file-tile");
    expect(tiles).toHaveLength(3);
    expect(tiles.filter((tile) => tile.dataset.state === "patched")).toHaveLength(1);
    expect(tiles.filter((tile) => tile.dataset.state === "identical")).toHaveLength(2);
    const patched = tiles.find((tile) => tile.dataset.state === "patched");
    expect(patched).toHaveTextContent("taskService.js");
    expect(patched).toHaveTextContent("patched");
    tiles.filter((tile) => tile.dataset.state === "identical").forEach((tile) => expect(tile).toHaveTextContent("byte-identical"));

    const diff = await screen.findByTestId("diff-view");
    expect(within(diff).getAllByTestId("diff-add")).toHaveLength(2);
    expect(within(diff).getAllByTestId("diff-del")).toHaveLength(1);
    expect(within(diff).getAllByTestId("diff-add")[0]).toHaveTextContent("new1");
    expect(within(diff).getByTestId("diff-del")).toHaveTextContent("old");
    expect(diff).toHaveTextContent("@@ -1,3 +1,4 @@");

    const board = headline.closest(".outcome-board");
    expect(board).toHaveTextContent("validator: ACCEPTED");
    expect(board).toHaveTextContent("attempts used 1/2");
    expect(board).toHaveTextContent("C4 retest PENDING");
    expect(board).toHaveTextContent("NOT INTEGRATED");
    expect(board).toHaveTextContent("SIMULATED defect");
    expect(screen.getByTestId("regeneration-result")).toHaveTextContent("MOCK model");
  });

  it("shows a rejected validator verdict with its code and does not claim any file changed", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    const rejected = {
      ...makeRegenerationResult({ status: "FAILED", mock: false }),
      reason_codes: ["PATCH_ATTEMPTS_EXHAUSTED"],
      patch_attempts: [1, 2].map((attempt_number) => ({
        relative_path: SERVICE,
        attempt_number,
        accepted: false,
        rejection_code: "PATCH_NO_OP",
        model_identifier: "test",
        client_inference_latency_ms: 5,
        prompt_template_version: "v",
      })),
      metrics: { ...makeRegenerationResult().metrics, within_request_attempt_count: 2, rejected_attempt_count: 2, llm_call_count: 2 },
    };
    installFetch(scopedRoutes({ "POST /api/v1/scoped-regenerations": rejected }));
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run REAL Ollama regeneration" }));

    const headline = await screen.findByTestId("outcome-headline");
    expect(headline).toHaveTextContent("0 of 2 files changed");
    expect(headline).toHaveTextContent("graph unchanged");
    const board = headline.closest(".outcome-board");
    expect(board).toHaveTextContent("validator: REJECTED · PATCH_NO_OP");
    expect(board).toHaveTextContent("attempts used 2/2");
    expect(board).toHaveTextContent("REAL local Ollama".replace("REAL local Ollama", "C4 retest PENDING"));
    const tiles = screen.getAllByTestId("file-tile");
    expect(tiles).toHaveLength(2);
    expect(tiles.every((tile) => tile.dataset.state === "untouched")).toBe(true);
    expect(screen.queryByText(/byte-identical/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("diff-view")).not.toBeInTheDocument();
  });

  it("shows a live elapsed counter and skeleton tiles while the call is running", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    installFetch(scopedRoutes({
      "POST /api/v1/demo/scoped-regenerations/mock": async () => {
        await gate;
        return patchedResult();
      },
    }));
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run MOCK regeneration" }));

    const board = await screen.findByTestId("running-board");
    expect(board).toHaveTextContent("waiting for the backend");
    expect(within(board).getByLabelText("Elapsed time")).toHaveTextContent(/\d+\.\d s/);
    release();
    expect(await screen.findByTestId("outcome-headline")).toBeInTheDocument();
    expect(screen.queryByTestId("running-board")).not.toBeInTheDocument();
  });

  it("shows the backend error code verbatim when the diff cannot be read", async () => {
    const user = userEvent.setup();
    seedSession(scopedSession());
    installFetch(scopedRoutes({
      "POST /api/v1/demo/scoped-regenerations/mock": patchedResult(),
      "POST /api/v1/demo/workspace-run": () => jsonResponse({ errors: [{ code: "WORKSPACE_INTEGRITY_FAILED", field: "manifest", message: "hash mismatch" }] }, 409),
    }));
    render(<App />);
    await openPage(user, /Scoped Regeneration/);

    await user.click(screen.getByRole("button", { name: "Run MOCK regeneration" }));

    await waitFor(() => expect(screen.getAllByTestId("error-panel").some((panel) => panel.textContent.includes("WORKSPACE_INTEGRITY_FAILED"))).toBe(true));
    expect(screen.getByTestId("outcome-headline")).toHaveTextContent("1 of 3 files changed");
  });
});

// ----------------------------------------------------------------- living traceability chain

const node = (node_id, node_type, source_identity = node_id, label = node_id) => ({
  node_id,
  node_type,
  source_identity,
  label,
  lifecycle_status: "ACTIVE",
  attributes: {},
});
const link = (link_id, source, relation, target, resolution = "RESOLVED") => ({
  link_id,
  logical_link_id: link_id,
  source_node_id: source,
  relation_type: relation,
  target_node_id: target,
  resolution_status: resolution,
  review_status: "NOT_REQUIRED",
  lifecycle_status: "ACTIVE",
  provenance: { evidence_kind: "DETERMINISTIC_MAPPING_RULE", mapping_rule_id: "R", evidence_refs: [], details: "" },
});

const chainSnapshot = () => ({
  graph_id: "graph-1",
  graph_version: 2,
  persisted_at_utc: "2026-10-19T00:00:00Z",
  generation_run_id: "run-1",
  artifact_digest_sha256: "a".repeat(64),
  graph_content_digest_sha256: "b".repeat(64),
  relation_direction_policy_version: "C3_GRAPH_RELATION_DIRECTION_V1",
  nodes: [
    node("REQUIREMENT:REQ-1", "REQUIREMENT", "REQ-1", "Create task"),
    node("REQUIREMENT:REQ-2", "REQUIREMENT", "REQ-2", "List tasks"),
    node("UML:1", "UML_ELEMENT", "UML-1", "TaskModel"),
    node("CODE:1", "CODE_MODULE", "svc", "taskService.js"),
    node("API:1", "API_OPERATION", "api", "POST /tasks"),
    node("DB:1", "DATABASE_ARTIFACT", "db", "tasks table"),
    node("TEST:1", "TEST_HOOK", "t", "task-test"),
  ],
  links: [
    link("L1", "UML:1", "DERIVED_FROM", "REQUIREMENT:REQ-1"),
    link("L2", "CODE:1", "IMPLEMENTS", "REQUIREMENT:REQ-1"),
    link("L3", "CODE:1", "EXPOSES", "API:1"),
    link("L4", "CODE:1", "PERSISTS_TO", "DB:1"),
    link("L5", "CODE:1", "VERIFIED_BY", "TEST:1"),
    link("L6", "UML:1", "DERIVED_FROM", "REQUIREMENT:REQ-2", "UNRESOLVED"),
  ],
  coverage: {
    policy_version: "C3_REQUIREMENT_COVERAGE_V1",
    verified_count: 1,
    partial_count: 0,
    unresolved_count: 1,
    requirements: [],
    diagnostics: { missing_evidence: [] },
  },
});

describe("Living traceability chain visual", () => {
  const seed = () =>
    seedSession({
      generationRun: { run: makeRun(), mode: "TEMPLATE_ONLY", durationMs: 1, at: "now" },
      graph: { snapshot: chainSnapshot(), versions: [], fetchedAt: "now" },
    });

  it("draws one connected node per chain stage for the selected requirement and switches requirement", async () => {
    const user = userEvent.setup();
    seed();
    installFetch(baseRoutes());
    render(<App />);
    await openPage(user, /Living Traceability/);

    const chain = await screen.findByTestId("chain-visual");
    expect(within(chain).getAllByTestId("chain-stage")).toHaveLength(6);
    const nodes = within(chain).getAllByTestId("chain-node");
    expect(nodes).toHaveLength(6);
    expect(nodes.map((item) => item.dataset.nodeType)).toEqual([
      "REQUIREMENT",
      "UML_ELEMENT",
      "CODE_MODULE",
      "API_OPERATION",
      "DATABASE_ARTIFACT",
      "TEST_HOOK",
    ]);

    await user.click(screen.getByRole("button", { name: "REQ-2" }));

    const second = within(screen.getByTestId("chain-visual")).getAllByTestId("chain-node");
    expect(second.map((item) => item.dataset.nodeType)).toEqual(["REQUIREMENT", "UML_ELEMENT"]);
    expect(second[1].className).toContain("chain-node-warn");
  });

  it("highlights the impact set returned by the impact endpoint", async () => {
    const user = userEvent.setup();
    seed();
    const { called } = installFetch({
      ...baseRoutes(),
      "GET /api/v1/traceability/graphs/graph-1/versions/2/impact/REQ-1": {
        requirement_id: "REQ-1",
        affected_node_ids: ["CODE:1", "API:1"],
        module_paths: ["backend/src/services/taskService.js"],
      },
    });
    render(<App />);
    await openPage(user, /Living Traceability/);
    const chain = await screen.findByTestId("chain-visual");
    expect(within(chain).getAllByTestId("chain-node").every((item) => item.dataset.impacted === "false")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Compute impact set for REQ-1" }));

    await waitFor(() => expect(screen.getByTestId("impact-summary")).toHaveTextContent("2 node(s), 1 module(s); 2 highlighted"));
    expect(called("GET /api/v1/traceability/graphs/graph-1/versions/2/impact/REQ-1")).toHaveLength(1);
    const impacted = within(screen.getByTestId("chain-visual")).getAllByTestId("chain-node").filter((item) => item.dataset.impacted === "true");
    expect(impacted.map((item) => item.dataset.nodeType)).toEqual(["CODE_MODULE", "API_OPERATION"]);
  });

  it("explains the next step when no graph exists", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Living Traceability/);

    expect(screen.getByText("Generation run required")).toBeInTheDocument();
    expect(screen.queryByTestId("chain-visual")).not.toBeInTheDocument();
  });
});

// ----------------------------------------------------------------- design coverage

const GENERATION_CONTEXT = {
  project_id: "P-1",
  srs_version: "SRS-1",
  uml_version: "UML-1",
  requirements: [{}],
  uml_elements: [{}],
  ui_artifacts: [],
  requirement_uml_anchors: [{}],
  upstream_provenance: { c1_approval_provenance_ref: "C1", c2_validation_report_ref: "C2" },
};

const COVERAGE_REPORT = {
  requirements: [
    { requirement_id: "FR-1", requirement_type: "FR", anchored_uml_ids: ["UML-CLASS-A"], status: "ANCHORED" },
    { requirement_id: "FR-2", requirement_type: "FR", anchored_uml_ids: ["UML-CLASS-B"], status: "ANCHORED" },
    { requirement_id: "FR-3", requirement_type: "FR", anchored_uml_ids: [], status: "UNANCHORED_FR" },
    { requirement_id: "NFR-1", requirement_type: "NFR", anchored_uml_ids: [], status: "NFR_NOT_APPLICABLE" },
    { requirement_id: "NFR-2", requirement_type: "NFR", anchored_uml_ids: [], status: "NFR_NOT_APPLICABLE" },
    { requirement_id: "NFR-3", requirement_type: "NFR", anchored_uml_ids: [], status: "NFR_NOT_APPLICABLE" },
  ],
  uml_elements: [
    { uml_id: "UML-CLASS-A", name: "Alpha", kind: "CLASS", anchored_requirement_ids: ["FR-1"], status: "ANCHORED" },
    { uml_id: "UML-CLASS-B", name: "Beta", kind: "CLASS", anchored_requirement_ids: ["FR-2"], status: "ANCHORED" },
    { uml_id: "UML-CLASS-X", name: "Extra", kind: "CLASS", anchored_requirement_ids: [], status: "EXTRA_NO_REQUIREMENT" },
  ],
  totals: { frs_anchored: 2, frs_unanchored: 1, nfrs: 3, uml_anchored: 2, uml_extra: 1 },
  diagnostics: [
    { code: "FR_WITHOUT_ANCHOR", subject_id: "FR-3", message: "no anchor" },
    { code: "UML_ELEMENT_WITHOUT_REQUIREMENT", subject_id: "UML-CLASS-X", message: "extra" },
  ],
  note: "Anchors are supplied by C2 and are taken as given; no semantic correctness is claimed.",
};

describe("Design coverage card", () => {
  const seed = () =>
    seedSession({
      validation: { ok: true, at: "now", generationContext: GENERATION_CONTEXT },
      inputSources: { c1: "SIMULATED_FIXTURE", c2: "SIMULATED_FIXTURE" },
    });

  it("calls /design-coverage with the validated context and renders ring, chips and the note", async () => {
    const user = userEvent.setup();
    seed();
    const { called } = installFetch({ ...baseRoutes(), "POST /api/v1/design-coverage": COVERAGE_REPORT });
    render(<App />);
    await openPage(user, /Design & Stack/);

    await user.click(screen.getByRole("button", { name: "Check requirement coverage" }));

    const card = await screen.findByTestId("coverage-card");
    expect(called("POST /api/v1/design-coverage")[0].body).toEqual(GENERATION_CONTEXT);
    expect(within(card).getByTestId("coverage-ring")).toHaveTextContent("2/3");
    expect(within(card).getByTestId("coverage-ring")).toHaveTextContent("requirements linked");
    expect(within(card).getAllByTestId("nfr-chip")).toHaveLength(3);
    expect(within(card).getAllByTestId("nfr-chip")[0]).toHaveTextContent("Quality rule");
    const uml = within(within(card).getByTestId("coverage-uml")).getAllByText(/Alpha|Beta|Extra/);
    expect(uml).toHaveLength(3);
    expect(uml.filter((chip) => chip.dataset.status === "ANCHORED")).toHaveLength(2);
    expect(uml.filter((chip) => chip.dataset.status === "EXTRA_NO_REQUIREMENT")).toHaveLength(1);
    expect(within(card).getByTestId("coverage-requirements")).toHaveTextContent("✗ FR-3 · not linked");
    expect(within(card).queryByTestId("coverage-note")).not.toBeInTheDocument();
    expect(within(card).queryByTestId("coverage-diagnostics")).not.toBeInTheDocument();
    expect(screen.getAllByText("SIMULATED C1/C2 input").length).toBeGreaterThan(0);
  });

  it("does not reuse a coverage report cached only by release labels", async () => {
    const user = userEvent.setup();
    seedSession({
      validation: { ok: true, at: "now", generationContext: GENERATION_CONTEXT },
      designCoverage: {
        contextKey: "P-1|SRS-1|UML-1",
        at: "before-anchor-rebuild",
        report: COVERAGE_REPORT,
      },
    });
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Design & Stack/);

    expect(screen.queryByTestId("coverage-card")).not.toBeInTheDocument();
    expect(screen.getByText(/Select Check requirement coverage/i)).toBeInTheDocument();
  });

  it("recommends the custom profile for calculation inputs without maturity labels", async () => {
    const user = userEvent.setup();
    seedSession({
      validation: {
        ok: true,
        at: "now",
        generationContext: {
          ...GENERATION_CONTEXT,
          requirements: [{ requirement_id: "REQ-GPA-1", statement: "Calculate a credit-weighted GPA using the grading policy." }],
          uml_elements: [{ uml_id: "UML-GPA", name: "GpaCalculationService", plantuml_source: "class GpaCalculationService { calculate() }" }],
        },
      },
    });
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Design & Stack/);

    expect(screen.getByText("Recommended for this input: Custom / non-CRUD application")).toBeInTheDocument();
    expect(screen.getByText(/deterministic rules over C1 requirement text and C2 UML names and methods/i)).toBeInTheDocument();
    expect(screen.queryByText("IMPLEMENTED MVP")).not.toBeInTheDocument();
    expect(screen.queryByText(/EXPERIMENTAL.*STAGE 0/i)).not.toBeInTheDocument();
  });

  it("shows a human-readable design error without transport details", async () => {
    const user = userEvent.setup();
    seed();
    installFetch({
      ...baseRoutes(),
      "POST /api/v1/design-coverage": () => jsonResponse({ errors: [{ code: "UNSUPPORTED_PLANTUML_CONSTRUCT", field: "uml_elements.0", message: "bad syntax" }] }, 422),
    });
    render(<App />);
    await openPage(user, /Design & Stack/);

    await user.click(screen.getByRole("button", { name: "Check requirement coverage" }));

    const panel = await screen.findByTestId("error-panel");
    expect(panel).toHaveTextContent("bad syntax");
    expect(panel).not.toHaveTextContent("UNSUPPORTED_PLANTUML_CONSTRUCT");
    expect(panel).not.toHaveTextContent("HTTP 422");
    expect(screen.queryByTestId("coverage-card")).not.toBeInTheDocument();
  });

  it("disables the button and explains the next step without a validated context", async () => {
    const user = userEvent.setup();
    installFetch(baseRoutes());
    render(<App />);

    await openPage(user, /Design & Stack/);

    expect(screen.getByRole("button", { name: "Check requirement coverage" })).toBeDisabled();
    expect(screen.getByText(/Review the C1\/C2 input first/)).toBeInTheDocument();
  });
});

describe("api.designCoverage", () => {
  it("posts the same body shape the design-context endpoint takes", async () => {
    const { called } = installFetch({ "POST /api/v1/design-coverage": COVERAGE_REPORT });

    await api.designCoverage(GENERATION_CONTEXT);

    expect(called("POST /api/v1/design-coverage")[0].body).toEqual(GENERATION_CONTEXT);
  });
});

// ----------------------------------------------------------------- overview timeline, header, advanced

describe("Dashboard overview", () => {
  it("has no pipeline timeline and no cross-component integration table", async () => {
    installFetch(baseRoutes());
    render(<App />);

    await screen.findByRole("heading", { name: "From approved design evidence to a traceable application" });

    expect(screen.queryByTestId("pipeline-timeline")).not.toBeInTheDocument();
    expect(screen.queryByText("Pipeline timeline")).not.toBeInTheDocument();
    expect(screen.queryByText("Cross-component integration status")).not.toBeInTheDocument();
  });

  it("shows no DEPLOYMENT BLOCKED pill in the header", async () => {
    installFetch(baseRoutes());
    render(<App />);

    await screen.findByRole("heading", { name: "From approved design evidence to a traceable application" });

    expect(screen.queryByText("DEPLOYMENT BLOCKED")).not.toBeInTheDocument();
  });

  it("has no deployment-gate card in the hero, only the headline", async () => {
    installFetch(baseRoutes());
    render(<App />);

    expect(await screen.findByRole("heading", { name: "From approved design evidence to a traceable application" })).toBeInTheDocument();
    expect(screen.queryByTestId("hero-gate")).not.toBeInTheDocument();
    expect(screen.queryByText("Awaiting C4 readiness")).not.toBeInTheDocument();
    const flow = screen.getByTestId("hero-flow");
    expect(flow).toHaveTextContent("Requirements");
    expect(flow).toHaveTextContent("Design");
    expect(flow).not.toHaveTextContent("You are here");
    expect(screen.queryByText("What you can do here")).not.toBeInTheDocument();
    expect(screen.queryByText(/verifiable application/)).not.toBeInTheDocument();
  });
});
