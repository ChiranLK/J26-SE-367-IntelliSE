// Readiness is derived only from results that real API calls returned in this session.
// It can show PENDING or BLOCKED but it can never produce a Component 4 approval or a
// deployment approval: no such evidence exists in Component 3.

import { attentionLinks } from "./traceGraph.js";

export const GATE_STATUS = {
  SATISFIED: "SATISFIED",
  PROVISIONAL: "PROVISIONAL",
  PENDING: "PENDING",
  REVIEW_REQUIRED: "REVIEW_REQUIRED",
  BLOCKED: "BLOCKED",
  NOT_RUN: "NOT_RUN",
  NOT_INTEGRATED: "NOT_INTEGRATED",
};

const structuralStatus = (report) => {
  if (!report) return GATE_STATUS.NOT_RUN;
  if (report.overall_status === "PASS") return GATE_STATUS.SATISFIED;
  if (report.overall_status === "FAIL") return GATE_STATUS.BLOCKED;
  return GATE_STATUS.REVIEW_REQUIRED;
};

export function latestRegeneration(session) {
  const runs = session.scoped?.runs ?? [];
  return runs.length ? runs[runs.length - 1] : null;
}

export function deriveReadiness(session) {
  const gates = [];
  const add = (id, title, status, detail, source) =>
    gates.push({ id, title, status, detail, source });

  add(
    "input",
    "C1/C2 input accepted by C3 validation (SIMULATED)",
    session.validation?.ok ? GATE_STATUS.SATISFIED : session.validation ? GATE_STATUS.BLOCKED : GATE_STATUS.NOT_RUN,
    session.validation?.ok
      ? "POST /validate-input accepted the simulated package. This is not real C1/C2 approval."
      : session.validation
        ? "POST /validate-input rejected the package."
        : "Validation has not been run in this session.",
    "POST /api/v1/validate-input",
  );

  add(
    "stack",
    "Technology-stack approval",
    session.approval?.status === "APPROVED_FOR_MVP_GENERATION"
      ? GATE_STATUS.PROVISIONAL
      : session.stackReport
        ? GATE_STATUS.PENDING
        : GATE_STATUS.NOT_RUN,
    session.approval?.status === "APPROVED_FOR_MVP_GENERATION"
      ? "Caller-asserted provisional approval. The approving identity is not authenticated."
      : session.stackReport
        ? "A researcher must approve the selected stack before generation."
        : "Stack selection has not been run.",
    "POST /api/v1/stack-selection",
  );

  const run = session.generationRun?.run;
  add(
    "generation",
    "Code generated and manifest verified",
    run ? GATE_STATUS.SATISFIED : GATE_STATUS.NOT_RUN,
    run
      ? `Run ${run.manifest.generation_run_id}. Execution status: ${run.manifest.execution_status}. Generated code was never executed.`
      : "No generation run in this session.",
    "POST /api/v1/generation-runs",
  );

  add(
    "structural",
    "C3 structural verification (static, not testing)",
    structuralStatus(session.structural),
    session.structural
      ? `Overall ${session.structural.overall_status}: ${session.structural.summary.pass_count} pass, ${session.structural.summary.fail_count} fail, ${session.structural.summary.review_required_count} review.`
      : "Structural verification has not been run.",
    "POST /api/v1/structural-verifications",
  );

  const snapshot = session.graph?.snapshot;
  const attention = snapshot ? attentionLinks(snapshot).length : 0;
  add(
    "traceability",
    "Living traceability graph persisted",
    !snapshot ? GATE_STATUS.NOT_RUN : attention > 0 ? GATE_STATUS.REVIEW_REQUIRED : GATE_STATUS.SATISFIED,
    snapshot
      ? `Graph v${snapshot.graph_version}: ${attention} link(s) are unresolved or need review.`
      : "No graph has been built in this session.",
    "POST /api/v1/traceability/graphs",
  );

  const regen = latestRegeneration(session);
  let regenStatus = GATE_STATUS.NOT_RUN;
  let regenDetail = "No scoped regeneration has been run in this session.";
  if (regen) {
    const result = regen.result;
    if (result.status === "PATCHED_PENDING_INDEPENDENT_RETEST") {
      regenStatus = GATE_STATUS.PENDING;
      regenDetail = `${regen.mode} run produced a patch awaiting independent C4 retest. Repair is not verified.`;
    } else if (result.status === "REVIEW_REQUIRED") {
      regenStatus = GATE_STATUS.REVIEW_REQUIRED;
      regenDetail = `${regen.mode} run needs human review (${result.reason_codes.join(", ")}).`;
    } else {
      regenStatus = GATE_STATUS.BLOCKED;
      regenDetail = `${regen.mode} run failed (${result.reason_codes.join(", ")}).`;
    }
  }
  add("regeneration", "Defect-feedback scoped regeneration", regenStatus, regenDetail, "POST /api/v1/scoped-regenerations");

  const handoff = regen?.result?.c4_retest_handoff;
  add(
    "c4-retest",
    "Independent Component 4 retest",
    handoff ? GATE_STATUS.PENDING : GATE_STATUS.NOT_RUN,
    handoff
      ? `Handoff status ${handoff.retest_status}; independent C4 evidence: ${handoff.independent_c4_evidence}. Component 3 cannot record a C4 result.`
      : "No retest has been requested. No C4 evidence exists.",
    "C4RetestHandoff",
  );

  add(
    "c4-xai",
    "Component 4 XAI and semantic-preservation analysis",
    GATE_STATUS.NOT_INTEGRATED,
    "Component 4 is not integrated. No XAI, semantic-preservation, or convergence result exists.",
    "none",
  );

  // C4 evidence can never be produced inside Component 3, so these two blockers are
  // always present; deployment therefore stays BLOCKED until C4 is integrated.
  const blockers = [
    "Independent C4 retest evidence is missing.",
    "C4 XAI and semantic-preservation evidence is missing.",
  ];
  if (!session.validation?.ok) blockers.push("C1/C2 input has not been validated.");
  if (session.approval?.status !== "APPROVED_FOR_MVP_GENERATION") {
    blockers.push("Stack selection has no explicit researcher approval.");
  } else {
    blockers.push("Stack approval is provisional and its approver is not authenticated.");
  }
  if (!run) blockers.push("No generated artifact set exists.");
  if (session.structural && session.structural.overall_status !== "PASS") {
    blockers.push(`Structural verification is ${session.structural.overall_status}.`);
  }
  if (!session.structural && run) blockers.push("Structural verification has not been run.");
  if (attention > 0) blockers.push(`${attention} traceability link(s) are unresolved or need review.`);
  blockers.push("Deployment is not implemented in Component 3.");

  return {
    gates,
    deployment: { status: "BLOCKED", blockers: [...new Set(blockers)] },
  };
}
