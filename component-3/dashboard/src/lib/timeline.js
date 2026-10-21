// Builds the pipeline timeline strictly from calls the dashboard really made in this
// session (state/callLog.js) plus the responses already stored in the session. A
// stage that has no logged call is "NOT RUN"; nothing is estimated or pre-filled.

const STAGES = [
  { id: "input", label: "Input validated", match: (c) => c.method === "POST" && c.path === "/validate-input" },
  { id: "design", label: "Design parsed", match: (c) => c.method === "POST" && c.path === "/design-context" },
  { id: "stack", label: "Stack selected", match: (c) => c.method === "POST" && c.path === "/stack-selection" },
  {
    id: "generation",
    label: "Code generated",
    match: (c) => c.method === "POST" && (c.path === "/generation-runs" || c.path === "/experiments/claude-generation" || c.path === "/experiments/openrouter-generation" || c.path === "/behaviour/generation-runs"),
  },
  { id: "graph", label: "Graph built", match: (c) => c.method === "POST" && c.path === "/traceability/graphs" },
  {
    id: "regeneration",
    label: "Scoped regeneration",
    match: (c) =>
      c.method === "POST" && (c.path === "/scoped-regenerations" || c.path === "/demo/scoped-regenerations/mock"),
  },
];

const evidenceFor = (id, session) => {
  switch (id) {
    case "input": {
      const sources = session.inputSources ?? {};
      const simulated = sources.c1 === "SIMULATED_FIXTURE" || sources.c2 === "SIMULATED_FIXTURE";
      return simulated
        ? { kind: "simulated", label: "SIMULATED INPUT" }
        : { kind: "none", label: "UPSTREAM NOT VERIFIED" };
    }
    case "generation": {
      const mode = session.generationRun?.mode;
      if (mode === "LOCAL_LLM") return { kind: "real", label: "REAL LOCAL OLLAMA" };
      if (mode === "EXPERIMENTAL_CLAUDE") return { kind: "simulated", label: "EXTERNAL LLM (experimental)" };
      if (mode === "EXPERIMENTAL_OPENROUTER") return { kind: "simulated", label: "LEGACY EXTERNAL (disabled)" };
      if (mode) return { kind: "real", label: "REAL C3 TEMPLATES" };
      return { kind: "real", label: "REAL C3 SERVICE" };
    }
    case "regeneration": {
      const last = session.scoped?.runs?.[session.scoped.runs.length - 1]?.result?.model_evidence_class;
      if (last === "MOCKED_TEST_DOUBLE") return { kind: "mock", label: "MOCKED_TEST_DOUBLE" };
      if (last === "SIMULATED_RAG_TEST_DOUBLE") return { kind: "simulated", label: "SIMULATED RAG" };
      if (last) return { kind: "real", label: "REAL LOCAL OLLAMA" };
      return { kind: "real", label: "REAL C3 SERVICE" };
    }
    default:
      return { kind: "real", label: "REAL C3 SERVICE" };
  }
};

export function buildTimeline(callLog, session) {
  const stages = STAGES.map((stage) => {
    const calls = callLog.filter(stage.match);
    const last = calls[calls.length - 1];
    const base = { id: stage.id, label: stage.label, evidence: evidenceFor(stage.id, session) };
    if (!last) return { ...base, status: "NOT_RUN", evidence: { ...base.evidence } };
    if (last.ok) return { ...base, status: "DONE", durationMs: last.durationMs, at: last.at };
    return {
      ...base,
      status: "REFUSED",
      durationMs: last.durationMs,
      at: last.at,
      detail: `${last.errorCode ?? "ERROR"}${last.status ? ` (HTTP ${last.status})` : ""}`,
    };
  });

  const runs = session.scoped?.runs ?? [];
  const handoff = [...runs].reverse().find((run) => run.result?.c4_retest_handoff)?.result.c4_retest_handoff;
  stages.push({
    id: "retest",
    label: "C4 retest",
    evidence: { kind: "none", label: "C4 NOT INTEGRATED" },
    status: handoff ? "PENDING" : "NOT_RUN",
    detail: handoff ? `${handoff.retest_status} · independent C4 evidence: ${handoff.independent_c4_evidence}` : undefined,
  });
  return stages;
}
