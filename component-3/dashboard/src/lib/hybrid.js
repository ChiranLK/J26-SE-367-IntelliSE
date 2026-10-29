// Pure derivations for the Hybrid GPA page. Everything here is computed from API
// responses only; nothing is invented when evidence is missing.

const active = (graph) => (graph?.links ?? []).filter((link) => link.status === "ACTIVE");

function keyOf(graph, nodeId) {
  return graph.nodes.find((node) => node.node_id === nodeId)?.key ?? nodeId;
}

// Requirement -> UML -> Rule -> Module/Code -> API -> DB -> Test seam, per requirement.
export function traceChains(graph) {
  if (!graph?.nodes) return [];
  const links = active(graph);
  const out = (source, relation) => links.filter((l) => l.source === source && l.relation === relation);
  const into = (target, relation) => links.filter((l) => l.target === target && l.relation === relation);
  return graph.nodes
    .filter((node) => node.node_type === "REQUIREMENT")
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((requirement) => {
      const id = requirement.node_id;
      const modules = out(id, "IMPLEMENTED_BY").filter((l) => l.evidence === "DIRECT").map((l) => l.target);
      const files = modules.flatMap((module) => out(module, "CONTAINS").map((l) => l.target));
      const rules = [...new Set(files.flatMap((file) => into(file, "PRODUCED").map((l) => keyOf(graph, l.source))))].sort();
      return {
        requirementId: requirement.key,
        version: requirement.attributes?.requirement_version,
        type: requirement.attributes?.requirement_type,
        uml: out(id, "DESIGNED_BY").map((l) => keyOf(graph, l.target)),
        rules,
        modules: modules.map((m) => keyOf(graph, m)).sort(),
        files: files.map((f) => keyOf(graph, f)).sort(),
        api: out(id, "EXPOSED_BY").map((l) => keyOf(graph, l.target)),
        db: out(id, "STORED_BY").map((l) => keyOf(graph, l.target)),
        seams: out(id, "VERIFIED_THROUGH").map((l) => keyOf(graph, l.target)),
      };
    });
}

export function verificationCounts(verification) {
  return {
    pass: verification?.pass_count ?? 0,
    review: verification?.review_count ?? 0,
    fail: verification?.fail_count ?? 0,
  };
}

export function ragRows(manifest) {
  return (manifest?.rag?.retrievals ?? []).flatMap((retrieval) =>
    retrieval.hits.map((hit) => ({
      key: `${retrieval.module_id}:${hit.chunk_id}`,
      module: retrieval.module_id,
      chunk: hit.chunk_id,
      version: hit.version,
      score: hit.score,
      applied: retrieval.applied_to_prompt,
    })),
  );
}

export function acceptanceFrom(template, acceptedBy) {
  if (!template) return null;
  return {
    policy_id: template.policy_id,
    policy_version: template.policy_version,
    policy_digest_sha256: template.policy_digest_sha256,
    accepted_by: acceptedBy,
    acceptance_reference: "DASHBOARD-RESEARCHER-ACCEPTANCE",
    acknowledges_sample_status: template.authority_status === "SAMPLE_RESEARCH_POLICY",
  };
}
