const CRUD_TEMPLATE_SET = "react-node-crud-scaffold-v1";

export function isDynamicCrudManifest(manifest) {
  if (!manifest?.run_evidence) return false;
  return (
    manifest.run_evidence.generator_version === "react-node-crud-generator-v1" ||
    manifest.run_evidence.template_set_version === CRUD_TEMPLATE_SET
  );
}

export function entityClasses(designContext) {
  if (!designContext?.classes) return [];
  return designContext.classes.filter(
    (item) => !item.name.endsWith("Service") && !item.name.endsWith("Repository"),
  );
}

export function summarizeDynamicRun({ designContext, manifest }) {
  const entities = entityClasses(designContext).map((cls) => ({
    name: cls.name,
    fields: cls.attributes.map((attribute) => ({
      name: attribute.name,
      type: attribute.type_name,
    })),
  }));
  const apiPaths = [];
  const operationIds = [];
  for (const reference of manifest?.api_references ?? []) {
    for (const operation of reference.operations ?? []) {
      apiPaths.push(`${operation.method} ${operation.route_path}`);
      operationIds.push(operation.operation_id);
    }
  }
  const sqlTables = [];
  for (const reference of manifest?.database_references ?? []) {
    for (const table of reference.tables ?? []) {
      sqlTables.push(table.name);
    }
  }
  const reviewFindings =
    manifest?.files
      ?.flatMap((file) => file.requirement_ids ?? [])
      .filter(Boolean) ?? [];
  return {
    entities,
    apiPaths: [...new Set(apiPaths)].sort(),
    operationIds: [...new Set(operationIds)].sort(),
    sqlTables: [...new Set(sqlTables)].sort(),
    fileCount: manifest?.files?.length ?? 0,
    artifactDigest: manifest?.artifact_digest_sha256 ?? "",
    traceHint: "Create a graph on the Living Traceability step after structural verification.",
    reviewRequired: [
      "SIMULATED C1/C2 upstream inputs — not real integration.",
      "Browser UI behavior requires isolated Docker preview; static verification marks UI REVIEW_REQUIRED.",
      "Runtime repository is IN_MEMORY — not production database persistence.",
      "C4 independent retest remains PENDING after scoped regeneration.",
    ],
    linkedRequirementCount: new Set(reviewFindings).size,
  };
}
