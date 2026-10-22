/*
 * HYBRID WORKFLOW STATE
 * Calls generation, preview and traceability APIs and stores their results in the session.
 * Original: component-3/dashboard/src/state/useHybridRun.js
 */

import { useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { acceptanceFrom } from "../lib/hybrid.js";
import { pace } from "../components/RunningSteps.jsx";
import { useSession } from "./session.jsx";
import { useAction } from "./useAction.js";

const ACCEPTED_BY = "research-supervisor";

// Demo pacing: starting the preview stays on screen for about this long in total, with its steps ticking over.
// Set VITE_PREVIEW_START_SECONDS=0 to turn it off.
export const PREVIEW_START_MS = import.meta.env.MODE === "test" ? 0 : Number(import.meta.env.VITE_PREVIEW_START_SECONDS ?? 50) * 1000;

// The Hybrid GPA run lives in session.hybrid (written by the Hybrid GPA Benchmark page). The workflow pages
// (Traceability, Preview, Scoped Regeneration, Readiness) read it and run the follow-up actions through this hook.
export function useHybridRun({ needOverview = false } = {}) {
  const { session, update } = useSession();
  const hybrid = session.hybrid ?? {};
  const put = (key, value) => update("hybrid", (current) => ({ ...(current ?? {}), [key]: value }));
  const [overview, setOverview] = useState(null);
  const run = hybrid.run;
  const projectId = run?.manifest?.input?.project_id;
  const latestRunId = hybrid.defect?.generation_run_id ?? hybrid.change?.generation_run_id ?? run?.generation_run_id;

  useEffect(() => {
    if (!needOverview) return;
    api.hybridOverview().then(setOverview).catch(() => setOverview(null));
  }, [needOverview]);

  const loadTrace = useAction(async () => put("trace", await api.hybridTrace(projectId)));

  const checkPreviews = useAction(async () => {
    const result = await api.hybridPreviews();
    // The backend knows what is really running: adopt the preview of the current run (else any running one) and
    // forget a remembered preview that has since been stopped outside this page.
    const running = result.previews.filter((preview) => preview.status === "RUNNING");
    const actual = running.find((preview) => preview.generation_run_id === latestRunId) ?? running[0] ?? null;
    if (actual) put("preview", actual);
    else if (hybrid.preview?.status === "RUNNING") put("preview", null);
    return result;
  });
  const startPreview = useAction(async () => {
    const begun = Date.now();
    put("gpaCheck", null);
    // A preview of an earlier version is replaced: only one app of this project runs at a time.
    if (hybrid.preview?.status === "RUNNING") {
      await api.hybridPreviewStop(hybrid.preview.preview_id);
      put("preview", null);
    }
    const started = await api.hybridPreviewStart(latestRunId);
    await pace(begun, PREVIEW_START_MS);
    put("preview", started);
  });
  const stopPreview = useAction(async () => put("preview", await api.hybridPreviewStop(hybrid.preview.preview_id)));
  const gpaCheck = useAction(async () => put("gpaCheck", await api.hybridPreviewGpaCheck(hybrid.preview.preview_id)));

  // `source` is a sample fixture id, or the changed C1/C2 package the user chose.
  const applyChange = useAction(async (source) => {
    const fixture = typeof source === "string" ? await api.hybridFixture(source) : { payload: source };
    const result = await api.hybridRequirementChange({
      base_generation_run_id: latestRunId,
      package: fixture.payload,
      policy_acceptance: acceptanceFrom(overview?.policy_acceptance_template, ACCEPTED_BY),
    });
    put("change", result);
    put("trace", await api.hybridTrace(result.manifest.input.project_id));
    return result;
  });

  const defectFlow = useAction(async () => {
    const injected = await api.hybridInjectDefect(latestRunId);
    const fixture = await api.hybridSimulatedDefect(injected.generation_run_id);
    const repaired = await api.hybridDefect(fixture.submission);
    put("defect", { ...repaired, injected_run_id: injected.generation_run_id, report: fixture.submission.report });
    put("trace", await api.hybridTrace(repaired.manifest.input.project_id));
  });

  return {
    hybrid, run, overview, projectId, latestRunId, overviewReady: Boolean(overview?.policy_acceptance_template),
    loadTrace, checkPreviews, startPreview, stopPreview, gpaCheck, applyChange, defectFlow,
  };
}
