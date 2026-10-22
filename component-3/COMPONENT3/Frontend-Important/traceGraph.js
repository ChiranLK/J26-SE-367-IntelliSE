/*
 * TRACEABILITY GRAPH HELPERS
 * Converts graph nodes and links into requirement chains and summary values for the UI.
 * Original: component-3/dashboard/src/lib/traceGraph.js
 */

// Pure helpers that read a TraceGraphSnapshot exactly as returned by the C3 API.
// Direction follows the C3 policy C3_GRAPH_RELATION_DIRECTION_V1: code, design
// anchors and UML point toward requirements, and code points to APIs, database
// artifacts, and test hooks. Nothing here adds or removes graph content.

export const NODE_TYPE_ORDER = [
  "REQUIREMENT",
  "UML_ELEMENT",
  "DESIGN_ANCHOR",
  "UI_ARTIFACT",
  "CODE_MODULE",
  "API_OPERATION",
  "DATABASE_ARTIFACT",
  "TEST_HOOK",
];

const isActive = (item) => item.lifecycle_status === "ACTIVE";

export const activeNodes = (snapshot) => snapshot.nodes.filter(isActive);
export const activeLinks = (snapshot) => snapshot.links.filter(isActive);

export function linkNeedsAttention(link) {
  return link.resolution_status !== "RESOLVED" || link.review_status === "REVIEW_REQUIRED";
}

function countBy(items, keyFn) {
  const counts = {};
  for (const item of items) {
    const key = keyFn(item);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

export function summarizeGraph(snapshot) {
  const nodes = activeNodes(snapshot);
  const links = activeLinks(snapshot);
  return {
    graphVersion: snapshot.graph_version,
    activeNodeCount: nodes.length,
    retiredNodeCount: snapshot.nodes.length - nodes.length,
    activeLinkCount: links.length,
    retiredLinkCount: snapshot.links.length - links.length,
    resolvedLinkCount: links.filter((link) => link.resolution_status === "RESOLVED").length,
    unresolvedLinkCount: links.filter((link) => link.resolution_status !== "RESOLVED").length,
    reviewRequiredLinkCount: links.filter((link) => link.review_status === "REVIEW_REQUIRED")
      .length,
    nodeCountsByType: countBy(nodes, (node) => node.node_type),
    linkCountsByRelation: countBy(links, (link) => link.relation_type),
  };
}

export function nodeIndex(snapshot) {
  return new Map(snapshot.nodes.map((node) => [node.node_id, node]));
}

// One row per requirement. Each cell lists the nodes reached through ACTIVE typed
// links, together with the link that connects them, so a reader can see whether
// each hop is RESOLVED or needs review.
export function buildRequirementChains(snapshot) {
  const nodes = nodeIndex(snapshot);
  const links = activeLinks(snapshot);
  const byTarget = (nodeId) => links.filter((link) => link.target_node_id === nodeId);
  const bySource = (nodeId) => links.filter((link) => link.source_node_id === nodeId);
  const typeOf = (nodeId) => nodes.get(nodeId)?.node_type;

  const chains = [];
  const requirements = activeNodes(snapshot)
    .filter((node) => node.node_type === "REQUIREMENT")
    .sort((a, b) => a.source_identity.localeCompare(b.source_identity));

  for (const requirement of requirements) {
    const design = new Map();
    const addDesign = (nodeId, link) => {
      if (!design.has(nodeId)) design.set(nodeId, link);
    };
    for (const link of byTarget(requirement.node_id)) {
      const sourceType = typeOf(link.source_node_id);
      if (sourceType === "UML_ELEMENT" || sourceType === "DESIGN_ANCHOR") {
        addDesign(link.source_node_id, link);
        if (sourceType === "DESIGN_ANCHOR") {
          for (const next of bySource(link.source_node_id)) {
            if (typeOf(next.target_node_id) === "UML_ELEMENT") {
              addDesign(next.target_node_id, next);
            }
          }
        }
      }
    }

    const code = new Map();
    for (const link of byTarget(requirement.node_id)) {
      if (typeOf(link.source_node_id) === "CODE_MODULE" && link.relation_type === "IMPLEMENTS") {
        if (!code.has(link.source_node_id)) code.set(link.source_node_id, link);
      }
    }

    const api = new Map();
    const database = new Map();
    const tests = new Map();
    for (const codeId of code.keys()) {
      for (const link of bySource(codeId)) {
        const targetType = typeOf(link.target_node_id);
        const target = link.target_node_id;
        if (targetType === "API_OPERATION" && !api.has(target)) api.set(target, link);
        else if (targetType === "DATABASE_ARTIFACT" && !database.has(target)) {
          database.set(target, link);
        } else if (
          (targetType === "TEST_HOOK" || (targetType === "CODE_MODULE" && link.relation_type === "VERIFIED_BY")) &&
          !tests.has(target)
        ) {
          tests.set(target, link);
        }
      }
    }

    const cell = (map) =>
      [...map.entries()]
        .map(([nodeId, link]) => ({ node: nodes.get(nodeId), link }))
        .filter((entry) => entry.node)
        .sort((a, b) => a.node.node_id.localeCompare(b.node.node_id));

    chains.push({
      requirement,
      design: cell(design),
      code: cell(code),
      api: cell(api),
      database: cell(database),
      tests: cell(tests),
    });
  }
  return chains;
}

export function attentionLinks(snapshot) {
  return activeLinks(snapshot).filter(linkNeedsAttention);
}

export function labelFor(nodes, nodeId) {
  const node = nodes.get(nodeId);
  return node ? `${node.label}` : nodeId;
}

// Compare two stored snapshots by stable identity (read-only; for the version view).
export function diffSnapshots(base, next) {
  const key = (link) => link.logical_link_id;
  const baseLinks = new Map(activeLinks(base).map((link) => [key(link), link]));
  const nextLinks = new Map(activeLinks(next).map((link) => [key(link), link]));
  const baseNodes = new Map(activeNodes(base).map((node) => [node.node_id, node]));
  const nextNodes = new Map(activeNodes(next).map((node) => [node.node_id, node]));
  const changedNodes = [...nextNodes.keys()].filter(
    (id) =>
      baseNodes.has(id) && JSON.stringify(baseNodes.get(id)) !== JSON.stringify(nextNodes.get(id)),
  );
  return {
    addedLinks: [...nextLinks.keys()].filter((id) => !baseLinks.has(id)),
    removedLinks: [...baseLinks.keys()].filter((id) => !nextLinks.has(id)),
    changedLinks: [...nextLinks.keys()].filter(
      (id) =>
        baseLinks.has(id) && JSON.stringify(baseLinks.get(id)) !== JSON.stringify(nextLinks.get(id)),
    ),
    addedNodes: [...nextNodes.keys()].filter((id) => !baseNodes.has(id)),
    removedNodes: [...baseNodes.keys()].filter((id) => !nextNodes.has(id)),
    changedNodes,
  };
}
