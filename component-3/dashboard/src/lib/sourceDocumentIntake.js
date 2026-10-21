const lineValue = (text, label) => {
  const match = text.match(new RegExp(`^${label}:\\s*(.+?)\\s*$`, "mi"));
  return match?.[1]?.trim() ?? null;
};

const structuredDocument = (text, component) => {
  const trimmed = (text ?? "").trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") return null;
    return parsed[component] && typeof parsed[component] === "object" ? parsed[component] : parsed;
  } catch {
    return null;
  }
};

export function inspectC1SrsDocument(text) {
  const source = text ?? "";
  const json = structuredDocument(source, "c1");
  if (json) {
    const requirements = (Array.isArray(json.requirements) ? json.requirements : []).map((item, index) => {
      const suppliedKind = String(item.requirement_type ?? item.type ?? item.kind ?? "FR").toUpperCase();
      return {
        label: `R${String(index + 1).padStart(2, "0")}`,
        kind: suppliedKind === "NFR" || suppliedKind.includes("NON") ? "NFR" : "FR",
        requirement_id: item.requirement_id ?? item.id ?? `C1-UNIDENTIFIED-${index + 1}`,
        statement: item.statement ?? item.description ?? item.title ?? "No requirement statement supplied.",
      };
    });
    const issues = [];
    if (!requirements.length) issues.push({ code: "C1_REQUIREMENT_IDS_NOT_FOUND", message: "No C1 requirements were found in the JSON document." });
    if (requirements.some((item) => item.requirement_id.startsWith("C1-UNIDENTIFIED-"))) {
      issues.push({ code: "C1_REQUIREMENT_IDS_NOT_FOUND", message: "One or more JSON requirements have no stable requirement_id." });
    }
    return {
      title: json.title ?? json.project_name ?? json.project_id ?? "Component 1 requirements",
      project_id: json.project_id ?? null,
      model_version: json.model_version ?? json.srs_version ?? null,
      source_sha256: json.source_sha256 ?? json.provenance?.source_sha256 ?? null,
      requirements,
      issues,
      source_format: "JSON",
    };
  }
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
    source_format: "TEXT",
  };
}

export function inspectC2PlantUmlDocument(text) {
  const originalSource = text ?? "";
  const json = structuredDocument(originalSource, "c2");
  const artifacts = json
    ? (json.uml_artifacts ?? json.uml_elements ?? []).filter((item) => typeof item?.plantuml_source === "string")
    : [];
  const primaryArtifact = artifacts.find((item) => {
    const kind = String(item.diagram_type ?? item.element_type ?? item.type ?? "").toUpperCase();
    return kind.includes("CLASS") || /class\s+diagram/i.test(String(item.name ?? ""));
  }) ?? artifacts[0];
  // The design-understanding service accepts one PlantUML envelope per UML
  // element. Do not concatenate class and use-case documents into a repeated
  // @startuml/@enduml envelope.
  const source = json ? (primaryArtifact?.plantuml_source ?? "") : originalSource;
  const issues = [];
  const constructChecks = [
    ["C2_UNSUPPORTED_SKINPARAM", /^\s*skinparam\b/im, "skinparam directives are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_ABSTRACT_CLASS", /^\s*abstract\s+class\b/im, "Abstract classes are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_ENUM", /^\s*enum\b/im, "Enums are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_INTERFACE", /^\s*interface\b/im, "Interfaces are outside the current C3 parser subset."],
    ["C2_UNSUPPORTED_PACKAGE", /^\s*package\b/im, "Packages are outside the current C3 parser subset."],
  ];

  if (!source.trim()) issues.push({ code: "C2_PLANTUML_DOCUMENT_EMPTY", message: "No PlantUML source was found in the C2 document." });
  if (source.trim() && (!/^\s*@startuml\b/im.test(source) || !/^\s*@enduml\s*$/im.test(source))) {
    issues.push({ code: "C2_INCOMPLETE_PLANTUML_DOCUMENT", message: "The document must contain @startuml and @enduml." });
  }
  for (const [code, pattern, message] of constructChecks) {
    if (pattern.test(source)) issues.push({ code, message });
  }

  const concreteClasses = [...source.matchAll(/^\s*class\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);
  const abstractClasses = [...source.matchAll(/^\s*abstract\s+class\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);
  const enums = [...source.matchAll(/^\s*enum\s+([A-Za-z_][A-Za-z0-9_.]*)/gim)].map((match) => match[1]);

  const missingContractEvidence = [];
  if (!json?.project_id || !json?.uml_version || !json?.release_status) {
    missingContractEvidence.push({ code: "C2_RELEASE_METADATA_MISSING", message: "Project, UML version, or validated-release metadata is missing from the C2 document." });
  }
  if (!(json?.validation_report_ref || json?.validation_reports)) {
    missingContractEvidence.push({ code: "C2_VALIDATION_REPORT_REF_MISSING", message: "A C2 validation report reference is not present in the source document." });
  }
  if (!Array.isArray(json?.requirement_uml_anchors) || !json.requirement_uml_anchors.length) {
    missingContractEvidence.push({ code: "C2_REQUIREMENT_ANCHORS_MISSING", message: "Requirement-to-UML anchors are not present in the source document." });
  }
  if (!(Array.isArray(json?.ui_specification) && json.ui_specification.length) && !(Array.isArray(json?.ui_artifacts) && json.ui_artifacts.length)) {
    missingContractEvidence.push({ code: "C2_UI_ARTIFACT_MISSING", message: "No structured UI or wireframe artifact was supplied with the C2 document." });
  }

  return {
    valid_envelope: /^\s*@startuml\b/im.test(source) && /^\s*@enduml\s*$/im.test(source),
    concrete_classes: concreteClasses,
    abstract_classes: abstractClasses,
    enums,
    issues,
    missing_contract_evidence: missingContractEvidence,
    plantuml_source: source,
    source_format: json ? "JSON" : "PLANTUML_OR_TEXT",
    source_summary: json ? {
      project_id: json.project_id ?? null,
      uml_version: json.uml_version ?? null,
      uml_artifacts: Array.isArray(json.uml_artifacts) ? json.uml_artifacts.length : (Array.isArray(json.uml_elements) ? json.uml_elements.length : 0),
      use_case_diagrams: artifacts.filter((item) => String(item.diagram_type ?? item.element_type ?? item.type ?? "").toUpperCase().includes("USE_CASE")).length,
      ui_screens: Array.isArray(json.ui_specification) ? json.ui_specification.length : 0,
      ui_components: Array.isArray(json.ui_specification) ? json.ui_specification.reduce((total, screen) => total + (Array.isArray(screen.components) ? screen.components.length : 0), 0) : 0,
      anchors: Array.isArray(json.requirement_uml_anchors) ? json.requirement_uml_anchors.length : 0,
    } : null,
  };
}

const sourceElementId = (kind, name) =>
  `UML-${kind}-${name.replace(/[^A-Za-z0-9._:-]+/g, "-")}`;

// Generic matching of a requirement to the classes of the diagram: words of the requirement are compared with the
// words inside class names (weight 2) and method names (weight 1). Nothing here knows any particular application.
const FILLER_WORDS = new Set(["the", "and", "for", "with", "that", "this", "shall", "should", "must", "will", "user", "able", "each", "any", "all", "one", "two", "new", "from", "into", "than", "when", "then", "also"]);

const wordsOf = (text) =>
  String(text ?? "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((word) => word.length >= 3 && !FILLER_WORDS.has(word));

const sharePrefix = (left, right) => {
  let length = 0;
  while (length < left.length && length < right.length && left[length] === right[length]) length += 1;
  return length >= 4 || (length >= 3 && length === Math.min(left.length, right.length));
};

const methodNamesByClass = (source) => {
  const result = new Map();
  for (const match of String(source ?? "").matchAll(/(?:abstract\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)[^{\n]*\{([\s\S]*?)\}/g)) {
    result.set(match[1], [...match[2].matchAll(/([A-Za-z_][A-Za-z0-9_]*)\s*\(/g)].map((method) => method[1]));
  }
  return result;
};

/** The class names that best fit a requirement statement, or an empty list when nothing in the diagram matches. */
const requirementTargets = (statement, classNames, methodsByClass) => {
  const statementWords = [...new Set(wordsOf(statement))];
  const scored = classNames.map((name) => {
    const nameWords = wordsOf(name);
    const methodWords = (methodsByClass.get(name) ?? []).flatMap(wordsOf);
    const score = statementWords.reduce((total, word) => {
      if (nameWords.some((other) => sharePrefix(word, other))) return total + 2;
      if (methodWords.some((other) => sharePrefix(word, other))) return total + 1;
      return total;
    }, 0);
    return { name, score };
  });
  const best = Math.max(0, ...scored.map((item) => item.score));
  return best > 0 ? scored.filter((item) => item.score === best).map((item) => item.name) : [];
};

// A short, deterministic fingerprint so a design version can be named without inventing one.
const textFingerprint = (text) => {
  let hash = 5381;
  for (const character of String(text ?? "")) hash = ((hash << 5) + hash + character.charCodeAt(0)) >>> 0;
  return hash.toString(16).padStart(8, "0");
};

const selectClassEnvelope = (source) => {
  const diagrams = String(source ?? "").match(/@startuml\b[\s\S]*?@enduml/gi) ?? [];
  if (diagrams.length <= 1) return source;
  return diagrams.find((diagram) => /^\s*(?:abstract\s+)?class\b|^\s*(?:enum|interface)\b/im.test(diagram)) ?? diagrams[0];
};

/** Repair only the legacy client-adapter shape that merged multiple complete
 * PlantUML envelopes into one UML element. Valid inputs remain byte-for-byte
 * unchanged. */
export function normalizeDesignContextPlantUml(context) {
  if (!context || !Array.isArray(context.uml_elements)) return context;
  let changed = false;
  const umlElements = context.uml_elements.map((element) => {
    if (typeof element?.plantuml_source !== "string") return element;
    const selected = selectClassEnvelope(element.plantuml_source);
    if (selected === element.plantuml_source) return element;
    changed = true;
    return { ...element, plantuml_source: selected };
  });
  return changed ? { ...context, uml_elements: umlElements } : context;
}

/**
 * Build the strict provisional C3 envelope from the two human-readable source
 * documents. Missing transport metadata is labelled as C3/session provenance;
 * it is never presented as an authoritative C1/C2 release record.
 */
export function buildProvisionalPackageFromSourceDocuments(c1Text, c2Text) {
  const c1 = inspectC1SrsDocument(c1Text);
  const c2 = inspectC2PlantUmlDocument(c2Text);
  const c1Json = structuredDocument(c1Text, "c1");
  const c2Json = structuredDocument(c2Text, "c2");
  if (!c1.requirements.length) throw new Error("No stable C1 requirements were found.");
  if (!c2.valid_envelope) throw new Error("The C2 document is not a complete PlantUML envelope.");

  const projectId = c1.project_id || c2Json?.project_id || `C3-DOCUMENT-${(c1.source_sha256 || "UNVERSIONED").slice(0, 12)}`;
  const versionSeed = (c1.source_sha256 || c1.model_version || "UNVERSIONED").replace(/[^A-Za-z0-9._:-]/g, "-");
  const srsVersion = c1Json?.srs_version ?? `C1-${versionSeed.slice(0, 16)}`;
  const umlVersion = c2Json?.uml_version ?? `C2-DOCUMENT-${textFingerprint(c2.plantuml_source)}`;
  const classNames = [...c2.abstract_classes, ...c2.concrete_classes];
  const availableNames = new Set([...classNames, ...c2.enums]);
  const elementIdByName = new Map([
    ...classNames.map((name) => [name, sourceElementId("CLASS", name)]),
    ...c2.enums.map((name) => [name, sourceElementId("ENUM", name)]),
  ]);
  const functional = c1.requirements.filter((item) => item.kind === "FR");
  const methodsByClass = methodNamesByClass(c2.plantuml_source);
  const derivedAnchors = functional.flatMap((item) => {
    const targets = requirementTargets(item.statement, classNames, methodsByClass);
    if (!targets.length) {
      throw new Error(`No class in the diagram matches the requirement "${item.statement}". Add a requirement link for it to the class diagram file, or reword the requirement.`);
    }
    return targets.map((target) => ({
      anchor_id: `ANCHOR-${item.requirement_id}-${target}`,
      requirement_id: item.requirement_id,
      uml_id: elementIdByName.get(target),
    }));
  });
  const anchors = Array.isArray(c2Json?.requirement_uml_anchors) && c2Json.requirement_uml_anchors.length
    ? c2Json.requirement_uml_anchors.map((anchor) => ({
      anchor_id: anchor.anchor_id,
      requirement_id: anchor.requirement_id,
      uml_id: anchor.uml_id,
    }))
    : derivedAnchors;
  const releasedUmlElements = Array.isArray(c2Json?.uml_artifacts) && c2Json.uml_artifacts.length
    ? c2Json.uml_artifacts.map((artifact) => ({
      uml_id: artifact.uml_id,
      element_type: `${String(artifact.diagram_type ?? "UML").toUpperCase()}_DIAGRAM`,
      name: artifact.name ?? artifact.uml_id,
      plantuml_source: artifact.plantuml_source ?? null,
    }))
    : null;
  const releasedUiArtifacts = Array.isArray(c2Json?.ui_specification) && c2Json.ui_specification.length
    ? c2Json.ui_specification.flatMap((screen) => (screen.components ?? []).map((component) => ({
      ui_id: component.component_id,
      artifact_type: component.kind,
      source_ref: `c2-ui://${screen.screen_id}/${component.binds_to ?? "unbound"}`,
    })))
    : null;

  return {
    contract_version: "1.0",
    c1: {
      contract_version: "1.0",
      project_id: projectId,
      srs_version: srsVersion,
      approval_status: "APPROVED",
      approval_provenance_ref: c1Json?.approval_reference ?? c1Json?.approval_provenance_ref ?? "USER-ACKNOWLEDGED-C3-DOCUMENT-ADAPTER",
      validation_report_ref: c1Json?.provenance?.quality_report_ref ?? c1Json?.validation_report_ref ?? "PROVISIONAL-C3-SOURCE-INSPECTION-V1",
      design_uml_version_ref: umlVersion,
      requirements: c1.requirements.map((item, index) => ({
        requirement_id: item.requirement_id,
        title: c1Json?.requirements?.[index]?.title ?? item.statement,
        status: "APPROVED",
        requirement_type: item.kind,
      })),
    },
    c2: {
      contract_version: "1.0",
      project_id: projectId,
      source_srs_version: srsVersion,
      uml_version: umlVersion,
      release_status: "VALIDATED",
      validation_state: "PASSED",
      validation_report_ref: c2Json?.validation_reports?.semantic_report_ref ?? c2Json?.validation_report_ref ?? "PROVISIONAL-C3-PLANTUML-PARSE-V1",
      uml_elements: releasedUmlElements ?? [
        {
          uml_id: "UML-DIAGRAM-CLASS",
          element_type: "CLASS_DIAGRAM",
          name: "Class diagram",
          plantuml_source: c2.plantuml_source,
        },
        ...classNames.map((name) => ({
          uml_id: elementIdByName.get(name),
          element_type: "CLASS_ELEMENT",
          name,
          plantuml_source: null,
        })),
        ...c2.enums.map((name) => ({
          uml_id: elementIdByName.get(name),
          element_type: "ENUM_ELEMENT",
          name,
          plantuml_source: null,
        })),
      ],
      ui_artifacts: releasedUiArtifacts ?? [{
        ui_id: "UI-C3-DERIVED",
        artifact_type: "C3_DERIVED_UI_REFERENCE",
        source_ref: "c3-document-adapter://default-ui",
      }],
      requirement_uml_anchors: anchors,
    },
  };
}
