// Pure builders that assemble request bodies for existing C3 contracts from data the
// real API already returned. They add no evidence of their own.

export const SIMULATED_PROJECT_NOTE =
  "SIMULATED C1/C2 fixture. Not approved Component 1 or Component 2 output.";

// Optional fault injection for the validation demo. The error shown afterwards is the
// real answer of POST /validate-input; nothing here predicts or fakes it.
export const FAULT_PRESETS = [
  {
    id: "draft-requirement",
    label: "Make a requirement DRAFT",
    description: "Sets c1.requirements[0].status to DRAFT (not approved).",
    apply: (pkg) => {
      pkg.c1.requirements[0].status = "DRAFT";
    },
  },
  {
    id: "missing-requirement-id",
    label: "Remove a requirement_id",
    description: "Deletes c1.requirements[0].requirement_id.",
    apply: (pkg) => {
      delete pkg.c1.requirements[0].requirement_id;
    },
  },
  {
    id: "duplicate-requirement",
    label: "Duplicate a requirement ID",
    description: "Appends a second requirement with an existing requirement_id.",
    apply: (pkg) => {
      pkg.c1.requirements.push({
        ...pkg.c1.requirements[0],
        title: "Duplicate of the first requirement",
      });
    },
  },
  {
    id: "dangling-anchor",
    label: "Point an anchor at an unknown UML element",
    description: "Sets c2.requirement_uml_anchors[0].uml_id to UML-DOES-NOT-EXIST.",
    apply: (pkg) => {
      pkg.c2.requirement_uml_anchors[0].uml_id = "UML-DOES-NOT-EXIST";
    },
  },
];

export function applyFault(payload, presetId) {
  const preset = FAULT_PRESETS.find((item) => item.id === presetId);
  if (!preset) throw new Error(`Unknown fault preset: ${presetId}`);
  const copy = JSON.parse(JSON.stringify(payload));
  preset.apply(copy);
  return copy;
}

export const APPROVAL_STATUS = {
  PENDING: "PENDING",
  APPROVED: "APPROVED_FOR_MVP_GENERATION",
  REJECTED: "REJECTED",
};

export function buildStackSelectionRequest({ designContext, criteria }) {
  return { design_context: designContext, criteria };
}

export function buildGenerationRequest({
  generationContext,
  designContext,
  stackReport,
  approval,
  mode,
  workspaceName,
}) {
  return {
    generation_context: generationContext,
    design_context: designContext,
    stack_selection_report: stackReport,
    stack_approval: {
      status: approval.status,
      approval_reference: approval.approvalReference,
      approved_by: approval.approvedBy,
      acknowledges_provisional_policy: approval.acknowledgesProvisionalPolicy,
    },
    mode,
    workspace_name: workspaceName,
  };
}

export function buildDefectReport({ scenario, manifest, graphVersion, reportId, now }) {
  return {
    source_classification: "SIMULATED_C4_FIXTURE",
    defect_report_id: reportId,
    reported_at_utc: (now ?? new Date()).toISOString(),
    source_generation_run_id: manifest.generation_run_id,
    source_artifact_digest_sha256: manifest.artifact_digest_sha256,
    source_graph_version: graphVersion,
    defects: scenario.defects,
  };
}

export function buildScopedRequest({ defectReport, baseline }) {
  return {
    defect_report: defectReport,
    manifest: baseline.generation_run.manifest,
    workspace_relative_path: baseline.generation_run.workspace_relative_path,
    design_context: baseline.design_context,
  };
}

export function buildStructuralRequest({ run, designContext }) {
  return {
    manifest: run.manifest,
    workspace_relative_path: run.workspace_relative_path,
    design_context: designContext,
  };
}

export function buildGraphCreateRequest(run) {
  return {
    manifest: run.manifest,
    workspace_relative_path: run.workspace_relative_path,
  };
}

export function buildPreviewRequest({ run, relativePath }) {
  return {
    manifest: run.manifest,
    workspace_relative_path: run.workspace_relative_path,
    relative_path: relativePath,
  };
}
