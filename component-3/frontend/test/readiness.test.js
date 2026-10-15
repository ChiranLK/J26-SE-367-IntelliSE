import { describe, expect, it } from "vitest";
import { deriveReadiness } from "../src/lib/readiness.js";
import { emptySession } from "../src/state/session.jsx";
import { makeRegenerationResult, makeRun } from "./helpers.js";

const gate = (readiness, id) => readiness.gates.find((item) => item.id === id);

describe("deriveReadiness", () => {
  it("starts with nothing satisfied and deployment BLOCKED", () => {
    const readiness = deriveReadiness(emptySession());

    expect(readiness.deployment.status).toBe("BLOCKED");
    expect(readiness.gates.every((item) => item.status !== "SATISFIED")).toBe(true);
    expect(gate(readiness, "c4-retest").status).toBe("NOT_RUN");
    expect(gate(readiness, "c4-xai").status).toBe("NOT_INTEGRATED");
  });

  it("never marks the C4 retest satisfied and keeps deployment blocked after a patch", () => {
    const session = emptySession();
    session.validation = { ok: true };
    session.approval = { status: "APPROVED_FOR_MVP_GENERATION" };
    session.generationRun = { run: makeRun(), mode: "TEMPLATE_ONLY" };
    const result = makeRegenerationResult({ status: "PATCHED_PENDING_INDEPENDENT_RETEST" });
    result.c4_retest_handoff = { retest_status: "PENDING", independent_c4_evidence: "NONE" };
    session.scoped.runs = [{ mode: "MOCK", result }];

    const readiness = deriveReadiness(session);

    expect(gate(readiness, "stack").status).toBe("PROVISIONAL");
    expect(gate(readiness, "generation").status).toBe("SATISFIED");
    expect(gate(readiness, "regeneration").status).toBe("PENDING");
    expect(gate(readiness, "c4-retest").status).toBe("PENDING");
    expect(readiness.gates.some((item) => item.id.startsWith("c4") && item.status === "SATISFIED")).toBe(false);
    expect(readiness.deployment.status).toBe("BLOCKED");
    expect(readiness.deployment.blockers).toEqual(expect.arrayContaining([
      "Independent C4 retest evidence is missing.",
      "C4 XAI and semantic-preservation evidence is missing.",
      "Deployment is not implemented in Component 3.",
    ]));
  });

  it("surfaces review-required and failed regenerations as such", () => {
    const review = emptySession();
    review.scoped.runs = [{ mode: "REAL_LOCAL_OLLAMA", result: makeRegenerationResult({ status: "REVIEW_REQUIRED", mock: false }) }];
    const failed = emptySession();
    failed.scoped.runs = [{ mode: "MOCK", result: makeRegenerationResult({ status: "FAILED" }) }];

    expect(gate(deriveReadiness(review), "regeneration").status).toBe("REVIEW_REQUIRED");
    expect(gate(deriveReadiness(failed), "regeneration").status).toBe("BLOCKED");
    expect(gate(deriveReadiness(failed), "c4-retest").status).toBe("NOT_RUN");
  });

  it("reports unresolved graph links as a blocker", () => {
    const session = emptySession();
    session.generationRun = { run: makeRun(), mode: "TEMPLATE_ONLY" };
    session.graph = {
      snapshot: {
        graph_version: 1,
        nodes: [],
        links: [{ link_id: "L", lifecycle_status: "ACTIVE", resolution_status: "UNRESOLVED", review_status: "REVIEW_REQUIRED" }],
      },
    };

    const readiness = deriveReadiness(session);

    expect(gate(readiness, "traceability").status).toBe("REVIEW_REQUIRED");
    expect(readiness.deployment.blockers.some((item) => item.includes("unresolved or need review"))).toBe(true);
  });
});
