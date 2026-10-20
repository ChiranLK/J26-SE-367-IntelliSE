const lineValue = (text, label) => {
  const match = text.match(new RegExp(`^${label}:\\s*(.+?)\\s*$`, "mi"));
  return match?.[1]?.trim() ?? null;
};

export function inspectC1SrsDocument(text) {
  const source = text ?? "";
  const requirementPattern =
    /^R(?<ordinal>\d+)\s*\|\s*(?<kind>FR|NFR)[^\n]*\n(?<statement>[^\n]+)\nRequirement ID:\s*(?<id>[A-Za-z0-9][A-Za-z0-9._:-]*)\s*$/gim;
  const requirements = [...source.matchAll(requirementPattern)].map((match) => ({
    label: `R${match.groups.ordinal}`,
    kind: match.groups.kind.toUpperCase(),
    requirement_id: match.groups.id,
    statement: match.groups.statement.trim(),
  }));
  const issues = [];

  if (!source.trim()) issues.push({ code: "C1_SRS_DOCUMENT_EMPTY", message: "Select the finalized C1 SRS text file." });
  if (source.trim() && requirements.length === 0) {
    issues.push({ code: "C1_REQUIREMENT_IDS_NOT_FOUND", message: "No C1 requirement blocks with stable Requirement ID values were found." });
  }
  if (/Unreviewed model prediction/i.test(source)) {
    issues.push({ code: "C1_REQUIREMENTS_NOT_REVIEWED", message: "The supplied C1 document labels its requirements as unreviewed model predictions." });
  }
  if (/No client approval or independent verification is implied/i.test(source)) {
    issues.push({ code: "C1_APPROVAL_NOT_ESTABLISHED", message: "The supplied C1 document explicitly says it does not establish client approval or independent verification." });
  }

  return {
    title: source.split(/\r?\n/).find((line) => line.trim())?.trim() ?? null,
    project_id: lineValue(source, "Project"),
    model_version: lineValue(source, "Model version"),
    source_sha256: lineValue(source, "Source SHA-256"),
    requirements,
    issues,
  };
}

export function inspectC2PlantUmlDocument(text) {
  const source = text ?? "";
  const issues = [];
  const constructChecks = [
    ["C2_UNSUPPORTED_SKINPARAM", /^\s*skinparam\b/im, "skinparam directives are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_ABSTRACT_CLASS", /^\s*abstract\s+class\b/im, "Abstract classes are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_ENUM", /^\s*enum\b/im, "Enums are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_INTERFACE", /^\s*interface\b/im, "Interfaces are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_PACKAGE", /^\s*package\b/im, "Packages are outside the current C3 parser subset."],
  ];

  if (!source.trim()) issues.push({ code: "C2_PLANTUML_DOCUMENT_EMPTY", message: "Select the finalized C2 PlantUML file." });
  if (source.trim() && (!/^\s*@startuml\b/im.test(source) || !/^\s*@enduml\s*$/im.test(source))) {
    issues.push({ code: "C2_INCOMPLETE_PLANTUML_DOCUMENT", message: "The document must contain @startuml and @enduml." });
  }
  for (const [code, pattern, message] of constructChecks) {
    if (pattern.test(source)) issues.push({ code, message });
  }

  const concreteClasses = [...source.matchAll(/^\s*class\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);
  const abstractClasses = [...source.matchAll(/^\s*abstract\s+class\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);
  const enums = [...source.matchAll(/^\s*enum\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);

  return {
    valid_envelope: /^\s*@startuml\b/im.test(source) && /^\s*@enduml\s*$/im.test(source),
    concrete_classes: concreteClasses,
    abstract_classes: abstractClasses,
    enums,
    issues,
    missing_contract_evidence: [
      { code: "C2_RELEASE_METADATA_MISSING", message: "A .puml file alone has no project/SRS/UML version or validated-release status." },
      { code: "C2_VALIDATION_REPORT_REF_MISSING", message: "A C2 validation report reference is not present in the .puml file." },
      { code: "C2_REQUIREMENT_ANCHORS_MISSING", message: "Requirement-to-UML anchors are not present in the .puml file." },
      { code: "C2_UI_ARTIFACT_MISSING", message: "No structured UI/wireframe artifact was supplied with this PlantUML file." },
    ],
  };
}
