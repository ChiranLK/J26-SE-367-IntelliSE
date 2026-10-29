import { describe, expect, it } from "vitest";
import { adaptUpstreamInputs } from "../src/lib/upstreamInputAdapter.js";

const limitedC1 = {
  contract_version: "1.0",
  project_id: "PROJECT-GPA-CALC-001",
  srs_version: "SRS-GPACALC-1.0",
  approval_status: "APPROVED",
  approval_provenance_ref: "C1-APPROVAL-GPACALC",
  validation_report_ref: "C1-VALIDATION-GPACALC",
  requirements: [{
    requirement_id: "REQ-GPACALC-001",
    type: "FUNCTIONAL",
    title: "Add a course grade",
    description: "Detailed SRS text",
    priority: "MUST",
    status: "APPROVED",
    acceptance_criteria: ["Entry is stored"],
  }],
};

const limitedC2 = {
  contract_version: "1.0",
  project_id: "PROJECT-GPA-CALC-001",
  source_srs_version: "SRS-GPACALC-1.0",
  uml_version: "UML-GPACALC-1.0",
  release_status: "VALIDATED",
  validation_state: "PASSED",
  uml_elements: [{
    element_id: "UML-GPACALC-CLASS-001",
    type: "CLASS_DIAGRAM",
    name: "GPA Calculator",
    plantuml_source: "@startuml\nclass CourseEntry\n@enduml",
  }],
  ui_artifacts: [{ artifact_id: "UI-GPACALC-001", type: "WIREFRAME", name: "Screen" }],
  requirement_uml_anchors: [{ requirement_id: "REQ-GPACALC-001", uml_element_id: "UML-GPACALC-CLASS-001" }],
};

describe("PP1 upstream input compatibility adapter", () => {
  it("keeps the optional C1 design_uml_version_ref so C3 can check the C2 uml_version", () => {
    const result = adaptUpstreamInputs(
      { ...limitedC1, design_uml_version_ref: "UML-GPACALC-1.0" },
      limitedC2,
      { c2ValidationReportRef: "SIMULATED-PP1-C2-REPORT" },
    );

    expect(result.c1.design_uml_version_ref).toBe("UML-GPACALC-1.0");
    expect(adaptUpstreamInputs(limitedC1, limitedC2, { c2ValidationReportRef: "R" }).c1).not.toHaveProperty(
      "design_uml_version_ref",
    );
  });

  it("keeps requirement_type only when it is exactly FR or NFR", () => {
    const withTypes = {
      ...limitedC1,
      requirements: [
        { ...limitedC1.requirements[0], requirement_id: "R-FR", requirement_type: "FR" },
        { ...limitedC1.requirements[0], requirement_id: "R-NFR", requirement_type: "NFR" },
        { ...limitedC1.requirements[0], requirement_id: "R-BAD", requirement_type: "functional" },
        { ...limitedC1.requirements[0], requirement_id: "R-NONE" },
      ],
    };

    const { c1 } = adaptUpstreamInputs(withTypes, limitedC2, { c2ValidationReportRef: "R" });
    const byId = Object.fromEntries(c1.requirements.map((item) => [item.requirement_id, item]));

    expect(byId["R-FR"].requirement_type).toBe("FR");
    expect(byId["R-NFR"].requirement_type).toBe("NFR");
    expect(byId["R-BAD"]).not.toHaveProperty("requirement_type");
    expect(byId["R-NONE"]).not.toHaveProperty("requirement_type");
  });

  it("maps the limited C1/C2 JSON without rewriting source identities or PlantUML", () => {
    const result = adaptUpstreamInputs(limitedC1, limitedC2, { c2ValidationReportRef: "SIMULATED-PP1-C2-REPORT" });

    expect(result.errors).toEqual([]);
    expect(result.c1.requirements).toEqual([
      { requirement_id: "REQ-GPACALC-001", title: "Add a course grade", status: "APPROVED" },
    ]);
    expect(result.c2.uml_elements[0]).toEqual({
      uml_id: "UML-GPACALC-CLASS-001",
      element_type: "CLASS_DIAGRAM",
      name: "GPA Calculator",
      plantuml_source: "@startuml\nclass CourseEntry\n@enduml",
    });
    expect(result.c2.ui_artifacts[0]).toEqual({
      ui_id: "UI-GPACALC-001",
      artifact_type: "WIREFRAME",
      source_ref: "c2-json://ui_artifacts/UI-GPACALC-001",
    });
    expect(result.c2.requirement_uml_anchors[0]).toEqual({
      anchor_id: "C3-PP1-ADAPTER-ANCHOR-001",
      requirement_id: "REQ-GPACALC-001",
      uml_id: "UML-GPACALC-CLASS-001",
    });
  });

  it("blocks readiness instead of inventing a missing C2 validation report reference", () => {
    const result = adaptUpstreamInputs(limitedC1, limitedC2);
    expect(result.c2.validation_report_ref).toBeUndefined();
    expect(result.errors).toEqual([
      expect.objectContaining({ code: "C2_VALIDATION_REPORT_REF_REQUIRED" }),
    ]);
  });

  it("leaves an already canonical package byte-for-byte equivalent", () => {
    const canonicalC1 = { project_id: "P", requirements: [{ requirement_id: "R", title: "T", status: "APPROVED" }] };
    const canonicalC2 = {
      validation_report_ref: "C2-R",
      uml_elements: [{ uml_id: "U", element_type: "CLASS", name: "N" }],
      ui_artifacts: [{ ui_id: "UI", artifact_type: "WIRE", source_ref: "ref" }],
      requirement_uml_anchors: [{ anchor_id: "A", requirement_id: "R", uml_id: "U" }],
    };
    const result = adaptUpstreamInputs(canonicalC1, canonicalC2);
    expect(result.adapted).toBe(false);
    expect(result.c1).toBe(canonicalC1);
    expect(result.c2).toBe(canonicalC2);
  });
});
