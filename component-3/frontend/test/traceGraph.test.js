import { describe, expect, it } from "vitest";
import { attentionLinks, buildRequirementChains, diffSnapshots, linkNeedsAttention, summarizeGraph } from "../src/lib/traceGraph.js";

// Hand-built input for the pure graph helpers. It mirrors the shape of
// TraceGraphSnapshot only to exercise the helpers; it is not a claim about any real graph.
const node = (node_id, node_type, extra = {}) => ({
  node_id,
  node_type,
  source_identity: extra.source_identity ?? node_id,
  label: extra.label ?? node_id,
  lifecycle_status: extra.lifecycle_status ?? "ACTIVE",
});
const link = (link_id, source, relation, target, extra = {}) => ({
  link_id,
  logical_link_id: extra.logical ?? link_id,
  source_node_id: source,
  relation_type: relation,
  target_node_id: target,
  resolution_status: extra.resolution ?? "RESOLVED",
  review_status: extra.review ?? "NOT_REQUIRED",
  lifecycle_status: extra.lifecycle ?? "ACTIVE",
  provenance: { evidence_kind: "DETERMINISTIC_MAPPING_RULE", mapping_rule_id: "R", evidence_refs: [], details: "" },
});

const snapshot = () => ({
  graph_version: 2,
  nodes: [
    node("REQ1", "REQUIREMENT", { source_identity: "REQ-1" }),
    node("REQ2", "REQUIREMENT", { source_identity: "REQ-2" }),
    node("UML1", "UML_ELEMENT"),
    node("CODE1", "CODE_MODULE"),
    node("API1", "API_OPERATION"),
    node("DB1", "DATABASE_ARTIFACT"),
    node("TEST1", "TEST_HOOK"),
    node("OLD", "CODE_MODULE", { lifecycle_status: "RETIRED" }),
  ],
  links: [
    link("L1", "UML1", "DERIVED_FROM", "REQ1"),
    link("L2", "CODE1", "IMPLEMENTS", "REQ1"),
    link("L3", "CODE1", "EXPOSES", "API1"),
    link("L4", "CODE1", "PERSISTS_TO", "DB1"),
    link("L5", "CODE1", "VERIFIED_BY", "TEST1"),
    link("L6", "UML1", "DERIVED_FROM", "REQ2", { resolution: "UNRESOLVED" }),
    link("L7", "OLD", "IMPLEMENTS", "REQ2", { lifecycle: "RETIRED" }),
  ],
});

describe("summarizeGraph", () => {
  it("counts only ACTIVE nodes and links and reports retired ones separately", () => {
    const summary = summarizeGraph(snapshot());

    expect(summary).toMatchObject({
      graphVersion: 2,
      activeNodeCount: 7,
      retiredNodeCount: 1,
      activeLinkCount: 6,
      retiredLinkCount: 1,
      resolvedLinkCount: 5,
      unresolvedLinkCount: 1,
    });
    expect(summary.nodeCountsByType.REQUIREMENT).toBe(2);
  });
});

describe("attention links", () => {
  it("flags unresolved and review-required links but not resolved ones", () => {
    expect(linkNeedsAttention(link("a", "x", "IMPLEMENTS", "y"))).toBe(false);
    expect(linkNeedsAttention(link("b", "x", "IMPLEMENTS", "y", { review: "REVIEW_REQUIRED" }))).toBe(true);
    expect(attentionLinks(snapshot()).map((item) => item.link_id)).toEqual(["L6"]);
  });
});

describe("buildRequirementChains", () => {
  it("walks requirement to design, code, API, database, and test hook", () => {
    const [first, second] = buildRequirementChains(snapshot());

    expect(first.requirement.source_identity).toBe("REQ-1");
    expect(first.design.map((cell) => cell.node.node_id)).toEqual(["UML1"]);
    expect(first.code.map((cell) => cell.node.node_id)).toEqual(["CODE1"]);
    expect(first.api.map((cell) => cell.node.node_id)).toEqual(["API1"]);
    expect(first.database.map((cell) => cell.node.node_id)).toEqual(["DB1"]);
    expect(first.tests.map((cell) => cell.node.node_id)).toEqual(["TEST1"]);

    expect(second.requirement.source_identity).toBe("REQ-2");
    expect(second.design[0].link.resolution_status).toBe("UNRESOLVED");
    expect(second.code).toEqual([]); // the only implementing link is retired
  });

  it("does not invent chain entries when the graph has no links", () => {
    const empty = { graph_version: 1, nodes: [node("REQ1", "REQUIREMENT")], links: [] };

    const [chain] = buildRequirementChains(empty);

    expect([chain.design, chain.code, chain.api, chain.database, chain.tests]).toEqual([[], [], [], [], []]);
  });
});

describe("diffSnapshots", () => {
  it("reports added, removed, and changed links by logical identity", () => {
    const base = snapshot();
    const next = snapshot();
    next.links = next.links.filter((item) => item.link_id !== "L5");
    next.links.push(link("L8", "CODE1", "EXPOSES", "API1", { logical: "NEW" }));
    next.links.find((item) => item.link_id === "L6").review_status = "REVIEW_REQUIRED";

    const diff = diffSnapshots(base, next);

    expect(diff.addedLinks).toEqual(["NEW"]);
    expect(diff.removedLinks).toEqual(["L5"]);
    expect(diff.changedLinks).toEqual(["L6"]);
  });
});
