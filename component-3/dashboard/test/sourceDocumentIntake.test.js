import { describe, expect, it } from "vitest";
import { buildProvisionalPackageFromSourceDocuments, inspectC1SrsDocument, inspectC2PlantUmlDocument, normalizeDesignContextPlantUml } from "../src/lib/sourceDocumentIntake.js";

describe("PP1 finalized source-document intake", () => {
  it("extracts exact C1 requirement identities without upgrading review status", () => {
    const text = `Create a Calculator
Project: project-1
Model version: model-1

R01 | FR (Functional) | Unreviewed model prediction
User shall add two numbers.
Requirement ID: req-111

Source SHA-256: ${"a".repeat(64)}
No client approval or independent verification is implied.`;
    const result = inspectC1SrsDocument(text);
    expect(result.project_id).toBe("project-1");
    expect(result.requirements).toEqual([{ label: "R01", kind: "FR", requirement_id: "req-111", statement: "User shall add two numbers." }]);
    expect(result.issues.map((issue) => issue.code)).toEqual(expect.arrayContaining(["C1_REQUIREMENTS_NOT_REVIEWED", "C1_APPROVAL_NOT_ESTABLISHED"]));
  });

  it("accepts the PlantUML envelope but reports unsupported calculator constructs", () => {
    const result = inspectC2PlantUmlDocument(`@startuml
skinparam classAttributeIconSize 0
abstract class Operation
class Addition
enum Status
Operation <|-- Addition
@enduml`);
    expect(result.valid_envelope).toBe(true);
    expect(result.concrete_classes).toEqual(["Addition"]);
    expect(result.abstract_classes).toEqual(["Operation"]);
    expect(result.enums).toEqual(["Status"]);
    expect(result.issues.map((issue) => issue.code)).toEqual(expect.arrayContaining([
      "C2_UNSUPPORTED_SKINPARAM", "C2_UNSUPPORTED_ABSTRACT_CLASS", "C2_UNSUPPORTED_ENUM",
    ]));
    expect(result.missing_contract_evidence.map((issue) => issue.code)).toContain("C2_REQUIREMENT_ANCHORS_MISSING");
  });

  it("reports malformed or empty source documents explicitly", () => {
    expect(inspectC1SrsDocument("").issues[0].code).toBe("C1_SRS_DOCUMENT_EMPTY");
    expect(inspectC2PlantUmlDocument("class MissingEnvelope").issues.map((issue) => issue.code)).toContain("C2_INCOMPLETE_PLANTUML_DOCUMENT");
  });

  it("repairs a legacy merged UML element by retaining its class diagram", () => {
    const merged = "@startuml\nactor User\n@enduml\n\n@startuml\nclass Calculator\n@enduml";
    const context = { project_id: "P1", uml_elements: [{ uml_id: "U1", plantuml_source: merged }] };

    const normalized = normalizeDesignContextPlantUml(context);

    expect(normalized.uml_elements[0].plantuml_source).toContain("class Calculator");
    expect(normalized.uml_elements[0].plantuml_source).not.toContain("actor User");
    expect(normalized.uml_elements[0].plantuml_source.match(/@startuml/g)).toHaveLength(1);
  });

  it("reads standalone or wrapped C1/C2 JSON documents without losing their source semantics", () => {
    const c1 = JSON.stringify({
      c1: {
        project_id: "GPA-1",
        srs_version: "SRS-2",
        requirements: [
          { requirement_id: "REQ-1", requirement_type: "FUNCTIONAL", statement: "Calculate GPA." },
          { requirement_id: "REQ-2", requirement_type: "NON_FUNCTIONAL", statement: "Respond quickly." },
        ],
      },
    });
    const c2 = JSON.stringify({
      project_id: "GPA-1",
      uml_version: "UML-2",
      release_status: "VALIDATED",
      validation_reports: { syntax_report_ref: "REPORT-1" },
      uml_artifacts: [
        { diagram_type: "USE_CASE", plantuml_source: "@startuml\nactor Student\n@enduml" },
        { diagram_type: "CLASS", plantuml_source: "@startuml\nclass Calculator\n@enduml" },
      ],
      ui_specification: [{ screen_id: "UI-1" }],
      requirement_uml_anchors: [{ requirement_id: "REQ-1", uml_id: "UML-1" }],
    });

    const c1Result = inspectC1SrsDocument(c1);
    const c2Result = inspectC2PlantUmlDocument(c2);

    expect(c1Result.source_format).toBe("JSON");
    expect(c1Result.requirements.map((item) => item.kind)).toEqual(["FR", "NFR"]);
    expect(c2Result.source_format).toBe("JSON");
    expect(c2Result.valid_envelope).toBe(true);
    expect(c2Result.concrete_classes).toEqual(["Calculator"]);
    expect(c2Result.plantuml_source.match(/@startuml/g)).toHaveLength(1);
    expect(c2Result.missing_contract_evidence).toEqual([]);
  });

  it("builds a transparent provisional calculator package with FR anchors and NFR labels", () => {
    const c1 = `Create a Calculator
Project: project-1
Model version: model-1

R01 | FR (Functional) | Unreviewed model prediction
User shall be able to add two numbers.
Requirement ID: req-add

R02 | NFR (Non-functional) | Unreviewed model prediction
Results shall appear within one second.
Requirement ID: req-speed

Source SHA-256: ${"a".repeat(64)}`;
    const c2 = `@startuml
abstract class Operation
class Addition { + calculate(firstNumber : double, secondNumber : double) : double }
class Calculator { + calculateResult() : void }
enum Status { SUCCESS }
Operation <|-- Addition
@enduml`;

    const result = buildProvisionalPackageFromSourceDocuments(c1, c2);

    expect(result.c1.project_id).toBe("project-1");
    expect(result.c1.requirements.map((item) => item.requirement_type)).toEqual(["FR", "NFR"]);
    expect(result.c2.uml_elements[0].plantuml_source).toBe(c2);
    expect(result.c2.requirement_uml_anchors).toEqual([
      expect.objectContaining({ requirement_id: "req-add", uml_id: "UML-CLASS-Addition" }),
    ]);
    expect(result.c1.approval_provenance_ref).toContain("USER-ACKNOWLEDGED");
    expect(result.c2.validation_report_ref).toContain("PROVISIONAL-C3");
  });

  it("preserves released C2 JSON diagrams, UI components, versions, and all trace links", () => {
    const c1 = JSON.stringify({
      project_id: "PROJECT-1", srs_version: "SRS-2.0", approval_reference: "APPROVAL-1",
      requirements: [{ requirement_id: "REQ-1", requirement_type: "FR", title: "Calculate", statement: "Calculate a result." }],
    });
    const c2 = JSON.stringify({
      project_id: "PROJECT-1", srs_version: "SRS-2.0", uml_version: "UML-2.0", release_status: "VALIDATED",
      validation_reports: { semantic_report_ref: "C2-REPORT" },
      uml_artifacts: [
        { uml_id: "UML-CLASS-1", diagram_type: "CLASS", name: "Classes", plantuml_source: "@startuml\nclass Calculator\nclass Result\nCalculator --> Result\n@enduml" },
        { uml_id: "UML-USECASE-1", diagram_type: "USE_CASE", name: "Use cases", plantuml_source: "@startuml\nactor User\n@enduml" },
      ],
      ui_specification: [{ screen_id: "UI-SCREEN-1", components: [
        { component_id: "UI-BUTTON-1", kind: "BUTTON", binds_to: "Calculator.calculate" },
        { component_id: "UI-RESULT-1", kind: "RESULT_PANEL", binds_to: "Result.value" },
      ] }],
      requirement_uml_anchors: [
        { anchor_id: "ANCHOR-1", requirement_id: "REQ-1", uml_id: "UML-CLASS-1", uml_element: "Calculator" },
        { anchor_id: "ANCHOR-2", requirement_id: "REQ-1", uml_id: "UML-CLASS-1", uml_element: "Result" },
      ],
    });

    const result = buildProvisionalPackageFromSourceDocuments(c1, c2);

    expect(result.c1.srs_version).toBe("SRS-2.0");
    expect(result.c2.uml_version).toBe("UML-2.0");
    expect(result.c2.uml_elements).toHaveLength(2);
    expect(result.c2.ui_artifacts).toHaveLength(2);
    expect(result.c2.requirement_uml_anchors).toEqual([
      { anchor_id: "ANCHOR-1", requirement_id: "REQ-1", uml_id: "UML-CLASS-1" },
      { anchor_id: "ANCHOR-2", requirement_id: "REQ-1", uml_id: "UML-CLASS-1" },
    ]);
  });
});
