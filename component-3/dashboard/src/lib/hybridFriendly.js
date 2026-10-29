// Plain-language wording for the Hybrid GPA results. Pure functions: nothing here invents data,
// it only renames what the API already returned.

export const MODULE_LABELS = {
  "fe.app-shell": "Frontend shell",
  "fe.gpa-form": "GPA form",
  "fe.validation": "Form validation",
  "fe.policy": "Grading-policy display",
  "fe.ui": "Frontend UI",
  "be.app": "Backend wiring",
  "be.routes": "API routes",
  "be.controller": "API controller",
  "be.service": "GPA calculation service",
  "be.policy": "Grading policy",
  "be.validation": "Input validation",
  "be.repository": "History storage",
  "be.smoke": "Backend smoke tests",
  "db.schema": "Database schema",
  "api.openapi": "API contract (OpenAPI)",
  "test-seams": "Test seams for C4",
  deployment: "Docker / deployment files",
  docs: "Documentation",
};

export const moduleLabel = (moduleId) => MODULE_LABELS[moduleId] ?? moduleId;

// Modules that check or describe the code (not part of the app's own behaviour).
export const SUPPORT_MODULES = new Set(["be.smoke", "api.openapi", "test-seams"]);

const FRIENDLY_ERRORS = {
  STALE_BASE_RUN:
    "A newer version of this project already exists, or this version was already changed once. Each change builds on the latest version, so generate a fresh one on Code Generation, then try again.",
  SRS_VERSION_NOT_BUMPED:
    "A change must arrive under a new approved requirements version. This change is not newer than the run it would be applied to.",
  REQUIREMENT_CHANGED_WITHOUT_VERSION_BUMP:
    "A requirement's wording changed without a new version number, so it is refused. Only client-approved new versions are accepted.",
  NO_APPROVED_CHANGE: "Nothing changed compared with the current run, so there is nothing to regenerate.",
  FULL_REGENERATION_REQUIRED:
    "This change adds or removes requirements or design classes, which is more than a scoped regeneration can handle. Generate a new run instead.",
  IMPACT_SET_INCOMPLETE:
    "Some modules that were not traced as affected would still change, so the regeneration was stopped rather than touching them silently.",
  LLM_MODULE_IMPACTED_REQUIRES_REVIEW:
    "The change reaches code written by a language model. That needs a new reviewed model call, so it is not done automatically.",
  STALE_DEFECT_REPORT: "The defect report refers to an older version of the app than the current run.",
  STALE_MODULE_DIGEST: "The defect report refers to an older version of the module than the current run.",
  DOCKER_UNAVAILABLE: "Docker is not running. Start Docker Desktop, wait until it says it is running, then try again.",
};

export function friendlyMessage(error) {
  const codes = (error?.errors ?? []).map((item) => item.code);
  for (const code of codes) if (FRIENDLY_ERRORS[code]) return FRIENDLY_ERRORS[code];
  if (/docker/i.test(error?.message ?? "") && /unavailable|not running|cannot connect/i.test(error?.message ?? "")) {
    return FRIENDLY_ERRORS.DOCKER_UNAVAILABLE;
  }
  return null;
}

export function describeChange(result) {
  const lineage = result?.manifest?.lineage;
  const counts = {};
  for (const row of lineage?.preservation ?? []) counts[row.state] = (counts[row.state] ?? 0) + 1;
  return {
    runId: result?.generation_run_id,
    modules: (lineage?.impact_set ?? []).map(moduleLabel),
    // A requirement change names the changed requirements; a defect repair names those its module traces to.
    requirements: lineage?.changed_requirement_ids ?? result?.c4_handoff?.requirement_ids_to_reverify ?? [],
    changedFiles: counts.REGENERATED_CHANGED ?? 0,
    identicalFiles: counts.REGENERATED_IDENTICAL ?? 0,
    untouchedFiles: counts.PRESERVED_UNTOUCHED ?? 0,
    unexpected: counts.UNEXPECTED_CHANGE ?? 0,
    changedPaths: (lineage?.preservation ?? []).filter((row) => row.state === "REGENERATED_CHANGED").map((row) => row.path),
    retest: result?.c4_handoff?.retest_status ?? null,
    links: result?.link_changes ?? null,
  };
}

// key -> display label for every node of the trace graph (requirement titles, "POST /api/..." operations, ...).
export function nodeLabels(graph) {
  const labels = {};
  for (const node of graph?.nodes ?? []) labels[`${node.node_type}:${node.key}`] = node.label ?? node.key;
  return labels;
}
