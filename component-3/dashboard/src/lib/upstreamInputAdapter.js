const C1_REQUIREMENT_FIELDS = new Set(["requirement_id", "title", "status"]);

const pickDefined = (entries) => Object.fromEntries(entries.filter(([, value]) => value !== undefined));

function needsC1CompatibilityMapping(value) {
  return (value?.requirements ?? []).some((requirement) =>
    Object.keys(requirement ?? {}).some((key) => !C1_REQUIREMENT_FIELDS.has(key)),
  );
}

function needsC2CompatibilityMapping(value) {
  return (
    (value?.uml_elements ?? []).some((element) => element?.element_id || element?.type) ||
    (value?.ui_artifacts ?? []).some((artifact) => artifact?.artifact_id || artifact?.type) ||
    (value?.requirement_uml_anchors ?? []).some((anchor) => anchor?.uml_element_id || !anchor?.anchor_id)
  );
}

function adaptC1(value) {
  if (!needsC1CompatibilityMapping(value)) return { value, adapted: false };

  return {
    adapted: true,
    value: pickDefined([
      ["contract_version", value.contract_version],
      ["project_id", value.project_id],
      ["srs_version", value.srs_version],
      ["approval_status", value.approval_status],
      ["approval_provenance_ref", value.approval_provenance_ref],
      ["validation_report_ref", value.validation_report_ref],
      ["design_uml_version_ref", value.design_uml_version_ref],
      [
        "requirements",
        (value.requirements ?? []).map((requirement) =>
          pickDefined([
            ["requirement_id", requirement.requirement_id],
            ["title", requirement.title],
            ["status", requirement.status],
          ]),
        ),
      ],
    ]),
  };
}

function adaptC2(value, validationReportRef) {
  if (!needsC2CompatibilityMapping(value)) return { value, adapted: false, generatedAnchorIds: false };

  let generatedAnchorIds = false;
  return {
    adapted: true,
    generatedAnchorIds: (value.requirement_uml_anchors ?? []).some((anchor) => !anchor.anchor_id),
    value: pickDefined([
      ["contract_version", value.contract_version],
      ["project_id", value.project_id],
      ["source_srs_version", value.source_srs_version],
      ["uml_version", value.uml_version],
      ["release_status", value.release_status],
      ["validation_state", value.validation_state],
      ["validation_report_ref", value.validation_report_ref || validationReportRef || undefined],
      [
        "uml_elements",
        (value.uml_elements ?? []).map((element) =>
          pickDefined([
            ["uml_id", element.uml_id ?? element.element_id],
            ["element_type", element.element_type ?? element.type],
            ["name", element.name],
            ["plantuml_source", element.plantuml_source],
          ]),
        ),
      ],
      [
        "ui_artifacts",
        (value.ui_artifacts ?? []).map((artifact) => {
          const id = artifact.ui_id ?? artifact.artifact_id;
          return pickDefined([
            ["ui_id", id],
            ["artifact_type", artifact.artifact_type ?? artifact.type],
            ["source_ref", artifact.source_ref ?? (id ? `c2-json://ui_artifacts/${id}` : undefined)],
          ]);
        }),
      ],
      [
        "requirement_uml_anchors",
        (value.requirement_uml_anchors ?? []).map((anchor, index) => {
          if (!anchor.anchor_id) generatedAnchorIds = true;
          return pickDefined([
            ["anchor_id", anchor.anchor_id ?? `C3-PP1-ADAPTER-ANCHOR-${String(index + 1).padStart(3, "0")}`],
            ["requirement_id", anchor.requirement_id],
            ["uml_id", anchor.uml_id ?? anchor.uml_element_id],
          ]);
        }),
      ],
    ]),
  };
}

/**
 * Compatibility adapter for the limited PP1 C1/C2 JSON examples.
 * It maps field names only; it never invents requirements, UML elements,
 * approval evidence, or validation evidence.
 */
export function adaptUpstreamInputs(c1, c2, { c2ValidationReportRef = "" } = {}) {
  const c1Result = adaptC1(c1);
  const c2Result = adaptC2(c2, c2ValidationReportRef.trim());
  const errors = [];
  const warnings = [];

  if (c2Result.adapted && !c2Result.value.validation_report_ref) {
    errors.push({
      code: "C2_VALIDATION_REPORT_REF_REQUIRED",
      message: "The C2 JSON does not include validation_report_ref. Enter the real or clearly labelled PP1 reference before validation.",
    });
  }
  if (c1Result.adapted) {
    warnings.push("C1 research-detail fields remain in the uploaded JSON but are excluded from the strict provisional C3 transport payload.");
  }
  if (c2Result.adapted) {
    warnings.push("C2 PP1 field names were mapped to the provisional C3 contract without changing the PlantUML source or upstream IDs.");
  }
  if (c2Result.generatedAnchorIds) {
    warnings.push("C2 supplied mappings without anchor IDs; C3 assigned clearly labelled adapter IDs. These are not authoritative C2 anchor identities.");
  }

  return {
    c1: c1Result.value,
    c2: c2Result.value,
    adapted: c1Result.adapted || c2Result.adapted,
    errors,
    warnings,
  };
}
