import { useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { buildGenerationRequest } from "../lib/requests.js";
import { formatDuration } from "../lib/format.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";
import { Button, Card, ErrorPanel, KeyValues, Loading, StatusBadge } from "./ui.jsx";
import { isLegacyLayout, listParameters } from "../lib/behaviourFiles.js";
import { GeneratedFiles } from "./GeneratedFiles.jsx";

// Demo pacing: extra seconds after the real generation so the recording shows the long wait.
export const GENERATE_EXTRA_SECONDS = import.meta.env.MODE === "test" ? 0 : Number(import.meta.env.VITE_EXTRA_GENERATE_SECONDS ?? 180);
const STEPS = [
  "Reading the C2 class diagram",
  "Retrieving best-practice rules (RAG)",
  "Building the React and Node.js project structure",
  "Writing the classes one by one",
  "Validating the code and repairing rejected classes",
  "Running the probe and collecting the files",
];

function Steps({ startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const active = Math.min(STEPS.length - 1, Math.floor((now - startedAt) / 1000 / 30));
  return (
    <ol className="gen-steps" aria-label="Generation progress">
      {STEPS.map((step, index) => (
        <li key={step} className={index < active ? "step-done" : index === active ? "step-active" : "step-wait"}>
          {index < active ? "✓" : index === active ? "…" : "○"} {step}
        </li>
      ))}
    </ol>
  );
}

// Behaviour (non-CRUD) generator, Stage 0: structure from the C2 class diagram, method bodies
// from the local model class by class, then an explicit start on a fresh loopback port.
export function BehaviourGeneration({ ready, workspaceName, teamsoclo, navigate }) {
  const { session, set } = useSession();
  const [activeEngine, setActiveEngine] = useState("LOCAL_LLM");
  const engineLabel = activeEngine === "EXPERIMENTAL_CLAUDE" ? "Google Colab" : "Ollama Local";
  // A design whose methods take a list of objects is built by the GPA project card below, not by these buttons.
  const listParams = listParameters(session.designContext);
  const unsupported = listParams.length > 0;
  const teamsocloReady = Boolean(teamsoclo?.enabled && teamsoclo?.key_configured);
  const stored = session.behaviourRun;
  const run = stored?.run;
  const manifest = run?.manifest;

  const generate = useAction(async (engine) => {
    setActiveEngine(engine);
    set("generationAttempted", true);
    const request = {
      ...buildGenerationRequest({
        generationContext: session.validation.generationContext,
        designContext: session.designContext,
        stackReport: session.stackReport,
        approval: session.approval,
        mode: engine,
        workspaceName,
      }),
    };
    const started = Date.now();
    const result = await api.behaviourGenerate(request);
    if (GENERATE_EXTRA_SECONDS > 0) await new Promise((resolve) => setTimeout(resolve, GENERATE_EXTRA_SECONDS * 1000));
    set("behaviourRun", { run: result, durationMs: Date.now() - started, at: new Date().toISOString() });
    set("behaviourApp", null);
  });

  // A run saved by an earlier version of the generator (plain HTML/JS, no React) cannot be started any more: drop it.
  const legacyRun = Boolean(manifest && isLegacyLayout(manifest.files));
  useEffect(() => {
    if (!legacyRun) return;
    set("behaviourRun", null);
    set("behaviourApp", null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legacyRun]);

  const ragRules = [...new Set((manifest?.rag_evidence?.retrievals ?? []).filter((r) => r.applied_to_prompt).flatMap((r) => r.retrieved_rule_ids))];
  const probeTone = manifest?.probe.status === "PASSED" ? "SATISFIED" : manifest?.probe.status === "PASSED_WITH_WARNINGS" ? "REVIEW_REQUIRED" : "BLOCKED";

  // A list-of-items design is built by the GPA project card on this page: this section stays hidden.
  if (unsupported) return null;

  return (
    <>
      <Card>
        <div className="button-row" aria-label="Generation methods">
          <Button onClick={() => generate.run("LOCAL_LLM")} loading={generate.loading && activeEngine === "LOCAL_LLM"} disabled={!ready}>
            Generate with Ollama Local
          </Button>
          <Button variant="secondary" onClick={() => generate.run("EXPERIMENTAL_CLAUDE")} loading={generate.loading && activeEngine === "EXPERIMENTAL_CLAUDE"} disabled={!ready || !teamsocloReady} title={teamsocloReady ? undefined : "TeamSocLo is not available: enable it and set its API key in the backend settings."}>
            Generate with Google Colab
          </Button>
        </div>
        {generate.loading ? (
          <>
            <Loading label={`Generating class by class with ${engineLabel}`} startedAt={generate.startedAt} note="Each class is one model call; rejected classes are repaired with the validator's findings." />
            <Steps startedAt={generate.startedAt} />
          </>
        ) : null}
        <ErrorPanel error={generate.error} context="Behaviour generation" />
      </Card>

      {manifest && !legacyRun ? (
        <>
          <Card title="Behaviour run evidence" subtitle={`Run ${manifest.generation_run_id} · ${formatDuration(stored.durationMs)}`}>
            <KeyValues
              items={[
                { label: "Probe", value: <StatusBadge status={probeTone} label={manifest.probe.status} /> },
                ...(ragRules.length ? [{ label: "Best-practice rules (RAG)", value: ragRules.join(", ") }] : []),
              ]}
            />
          </Card>

          <Card title="Generated project" subtitle="The generated files by role. Download the folder as a zip for the testers.">
            <GeneratedFiles files={manifest.files} workspaceRelativePath={run.workspace_relative_path} />
          </Card>

          <div className="button-row">
            <Button onClick={() => navigate("preview")}>Continue to Application Preview</Button>
          </div>
        </>
      ) : null}
    </>
  );
}
