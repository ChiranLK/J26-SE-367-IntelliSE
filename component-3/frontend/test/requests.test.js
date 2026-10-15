import { describe, expect, it } from "vitest";
import { FAULT_PRESETS, applyFault, buildDefectReport, buildGenerationRequest, buildScopedRequest } from "../src/lib/requests.js";
import { makeBaseline, makeManifest } from "./helpers.js";

describe("request builders", () => {
  it("builds the defect report from the real baseline manifest and graph version", () => {
    const manifest = makeManifest({ runId: "run-xyz" });
    const scenario = { scenario_id: "S", defects: [{ defect_id: "D1" }] };

    const report = buildDefectReport({ scenario, manifest, graphVersion: 3, reportId: "SIM-R-1", now: new Date("2026-10-14T00:00:00Z") });

    expect(report).toEqual({
      source_classification: "SIMULATED_C4_FIXTURE",
      defect_report_id: "SIM-R-1",
      reported_at_utc: "2026-10-14T00:00:00.000Z",
      source_generation_run_id: "run-xyz",
      source_artifact_digest_sha256: manifest.artifact_digest_sha256,
      source_graph_version: 3,
      defects: [{ defect_id: "D1" }],
    });
  });

  it("builds the scoped request from the baseline without inventing fields", () => {
    const baseline = makeBaseline();
    const request = buildScopedRequest({ defectReport: { id: 1 }, baseline });

    expect(Object.keys(request).sort()).toEqual(["defect_report", "design_context", "manifest", "workspace_relative_path"]);
    expect(request.manifest).toBe(baseline.generation_run.manifest);
  });

  it("maps the approval decision into the generation request", () => {
    const request = buildGenerationRequest({
      generationContext: { g: 1 },
      designContext: { d: 1 },
      stackReport: { s: 1 },
      approval: { status: "APPROVED_FOR_MVP_GENERATION", approvedBy: "me", approvalReference: "ref", acknowledgesProvisionalPolicy: true },
      mode: "LOCAL_LLM",
      workspaceName: "demo",
    });

    expect(request.stack_approval).toEqual({
      status: "APPROVED_FOR_MVP_GENERATION",
      approval_reference: "ref",
      approved_by: "me",
      acknowledges_provisional_policy: true,
    });
    expect(request.mode).toBe("LOCAL_LLM");
    expect(request.workspace_name).toBe("demo");
  });

  it("fault presets copy the payload and change only the intended field", () => {
    const pkg = {
      c1: { requirements: [{ requirement_id: "R1", status: "APPROVED" }] },
      c2: { requirement_uml_anchors: [{ anchor_id: "A", uml_id: "U" }] },
    };
    const before = JSON.stringify(pkg);

    const draft = applyFault(pkg, "draft-requirement");
    const dangling = applyFault(pkg, "dangling-anchor");

    expect(JSON.stringify(pkg)).toBe(before);
    expect(draft.c1.requirements[0].status).toBe("DRAFT");
    expect(dangling.c2.requirement_uml_anchors[0].uml_id).toBe("UML-DOES-NOT-EXIST");
    expect(FAULT_PRESETS.length).toBeGreaterThanOrEqual(4);
    expect(() => applyFault(pkg, "nope")).toThrow();
  });
});
