import { describe, expect, it } from "vitest";
import { inspectC1SrsDocument, inspectC2PlantUmlDocument } from "../src/lib/sourceDocumentIntake.js";

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
});
