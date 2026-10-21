import { api } from "../api/endpoints.js";
import { acceptanceFrom } from "../lib/hybrid.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";
import { ProjectTree } from "./ProjectTree.jsx";
import { RunningSteps, pace } from "./RunningSteps.jsx";
import { Button, Card, ErrorPanel, Hash, KeyValues, Loading, Stat, StatusBadge } from "./ui.jsx";

// Clicking Generate is the researcher's explicit acceptance of the sample grading policy; the run manifest records it.
const ACCEPTED_BY = "researcher (dashboard)";
const INPUT_FIXTURE = "gpa-input";

// Demo pacing: generating the whole project stays on screen for about 200 seconds (none in tests), with its steps ticking over.
const GENERATE_PACE_MS = import.meta.env.MODE === "test" ? 0 : 200000;
const GENERATE_STEPS = [
  "Checking the C1/C2 inputs",
  "Choosing the rules and the technology",
  "Writing the backend",
  "Writing the frontend",
  "Writing the database scripts",
  "Checking the code against the design",
  "Linking every requirement to its code",
  "Packing the project",
];

// The package the user uploaded on C1/C2 Inputs, when both files are released 2.x JSON documents; otherwise nothing.
function uploadedPackage(sourceDocuments) {
  try {
    const c1 = JSON.parse(sourceDocuments?.c1Text ?? "");
    const c2 = JSON.parse(sourceDocuments?.c2Text ?? "");
    if (!String(c1?.contract_version).startsWith("2.") || !String(c2?.contract_version).startsWith("2.")) return null;
    return { contract_version: c1.contract_version, input_classification: "VALIDATED_CONTRACT_INPUT", c1, c2 };
  } catch {
    return null;
  }
}

// A file whose evidence_class is not one of the two contract values is explained in plain words; C3 does not change it.
function EvidenceClassHelp({ error, sourceDocuments }) {
  const fields = (error?.errors ?? []).filter((item) => String(item.field ?? "").endsWith("evidence_class")).map((item) => item.field.split(".").at(0).toUpperCase());
  if (!fields.length) return null;
  const valueOf = (key) => {
    try {
      return JSON.parse(sourceDocuments?.[`${key}Text`] ?? "").evidence_class;
    } catch {
      return undefined;
    }
  };
  return (
    <div className="unsupported-note" data-testid="evidence-class-help">
      <strong>{fields.join(" and ")} file: the evidence_class value is not allowed.</strong>
      <span>
        It must be <code>SIMULATED_FIXTURE</code> for test or sample data, or <code>UPSTREAM_COMPONENT_OUTPUT</code> only when the file really comes from
        the Component 1 or Component 2 system. {fields.map((key) => `${key} has "${valueOf(key.toLowerCase()) ?? "?"}"`).join(", ")}. Change it in the file, choose it again on C1/C2 Inputs and press Generate project.
      </span>
    </div>
  );
}

// One-click generation of the GPA project from the sample C1/C2 inputs (rule-governed pipeline).
export function HybridGenerate() {
  const { session, update } = useSession();
  const hybrid = session.hybrid ?? {};
  const put = (key, value) => update("hybrid", (current) => ({ ...(current ?? {}), [key]: value }));
  const run = hybrid.run;
  const manifest = run?.manifest;
  const contract = hybrid.contract;

  const uploaded = uploadedPackage(session.sourceDocuments);
  const generate = useAction(async () => {
    const started = Date.now();
    const [overview, fixture] = await Promise.all([api.hybridOverview(), uploaded ? Promise.resolve({ payload: uploaded }) : api.hybridFixture(INPUT_FIXTURE)]);
    const contractReport = await api.hybridValidate(fixture.payload);
    const result = await api.hybridGenerate({
      package: fixture.payload,
      policy_acceptance: acceptanceFrom(overview.policy_acceptance_template, ACCEPTED_BY),
      workspace_name: "gpa-dashboard",
      allow_llm_for_unsupported: false,
      llm_backend_logic: false,
      llm_frontend: false,
    });
    const trace = await api.hybridTrace(result.manifest.input.project_id);
    await pace(started, GENERATE_PACE_MS);
    put("contract", contractReport);
    put("run", result);
    put("change", null);
    put("defect", null);
    put("trace", trace);
  });

  return (
    <Card>
      <div className="button-row">
        <Button onClick={() => generate.run()} loading={generate.loading}>Generate project</Button>
      </div>
      {generate.loading ? (
        <>
          <Loading label="Running the generation pipeline…" startedAt={generate.startedAt} />
          <RunningSteps startedAt={generate.startedAt} durationMs={GENERATE_PACE_MS || undefined} label="Project generation progress" steps={GENERATE_STEPS} />
        </>
      ) : null}
      <EvidenceClassHelp error={generate.error} sourceDocuments={session.sourceDocuments} />
      <ErrorPanel error={generate.error} context="GPA generation" />
      {manifest ? (
        <>
          <div className="stats">
            <Stat label="Run status" value={run.status} tone={run.status === "ACCEPTED" ? "ok" : "warn"} />
            <Stat label="Modules" value={manifest.modules.length} hint={`${manifest.files.length} files`} />
            <Stat label="Rules selected" value={manifest.rule_set.selected_rules.length} />
          </div>
          <KeyValues
            items={[
              { label: "Input", value: contract ? <span><StatusBadge status={contract.status === "ACCEPTED" ? "PASS" : "FAIL"} label={contract.status} /> {contract.project_id} · {contract.srs_version} / {contract.uml_version}</span> : "—" },
              { label: "Generation run", value: run.generation_run_id },
              { label: "Artifact digest", value: <Hash value={manifest.artifact_digest_sha256} length={20} /> },
              { label: "Stack", value: `${manifest.stack.stack_id} (${manifest.stack.frontend} + ${manifest.stack.backend} + ${manifest.stack.database})` },
            ]}
          />
          <h3 className="subhead">Generated project</h3>
          <ProjectTree files={manifest.files} runId={run.generation_run_id} />
          <p className="muted small">Next: Application Preview, Living Traceability and Readiness read this run.</p>
        </>
      ) : null}
    </Card>
  );
}
