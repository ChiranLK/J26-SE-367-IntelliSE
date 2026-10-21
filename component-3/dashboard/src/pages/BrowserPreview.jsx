import { useEffect } from "react";
import { api } from "../api/endpoints.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  ErrorPanel,
  Hash,
  KeyValues,
  Loading,
  PageHeader,
  SimulatedBadge,
} from "../components/ui.jsx";
import { BehaviourAppCard } from "../components/BehaviourAppCard.jsx";
import { isDynamicCrudManifest } from "../lib/crudSummary.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";
import { HybridPreviewView } from "../components/HybridViews.jsx";
import { withHybridFallback } from "../components/withHybridFallback.jsx";

function previewTone(status) {
  if (status === "RUNNING") return "ok";
  if (status === "FAILED") return "bad";
  if (status === "BUILT" || status === "STOPPED") return "info";
  return "neutral";
}

function ClassicBrowserPreview({ navigate }) {
  const { session, set } = useSession();
  const run = session.generationRun?.run;
  const manifest = run?.manifest;
  const dynamic = manifest && isDynamicCrudManifest(manifest);
  const preview = session.preview;
  const behaviourRun = session.behaviourRun?.run;

  useEffect(() => {
    if (!dynamic || !manifest?.generation_run_id || preview?.preview_id === manifest.generation_run_id) {
      return;
    }
    api
      .previewStatus(manifest.generation_run_id)
      .then((status) => set("preview", status))
      .catch(() => {
        /* no session yet */
      });
  }, [dynamic, manifest, preview?.preview_id, set]);

  const build = useAction(async () => {
    const result = await api.previewBuild({
      manifest: run.manifest,
      workspace_relative_path: run.workspace_relative_path,
    });
    set("preview", result);
  });

  const start = useAction(async () => {
    const result = await api.previewStart(preview.preview_id);
    set("preview", result);
  });

  const stop = useAction(async () => {
    const result = await api.previewStop(preview.preview_id);
    set("preview", result);
  });

  return (
    <div className="page">
      <PageHeader
        title="Application Preview (Docker)"
        subtitle="Build and open the generated SPA inside a disposable Linux container. Generated JavaScript never runs on the Windows host."
        badges={
          <>
            <SimulatedBadge>SIMULATED C1/C2 INPUT</SimulatedBadge>
            <Badge tone="info">IN_MEMORY DB</Badge>
          </>
        }
      />

      {behaviourRun ? <BehaviourAppCard run={behaviourRun} /> : null}

      {!run && !behaviourRun ? (
        <Callout tone="warn" title="Generate an application first">
          Complete Code Generation for a dynamic CRUD domain, then return here.{" "}
          <button type="button" className="link-button" onClick={() => navigate("generation")}>
            Open Code Generation
          </button>
        </Callout>
      ) : null}

      {run && !dynamic ? (
        <Callout tone="info" title="Task MVP runs use the text preview only">
          Browser preview is enabled only for verified dynamic CRUD manifests. This run uses the older Task-specific
          manifest format and therefore remains display-only in the dashboard.
        </Callout>
      ) : null}

      {run && dynamic ? (
        <>
          <Card title="Research evidence chain" subtitle="What the dashboard can show without claiming real C4 or deployment.">
            <ol className="evidence-chain">
              <li>Requirement / UML provenance — SIMULATED fixtures on Inputs (labeled).</li>
              <li>Generated code / API / DB / test hooks — manifest + file table on Code Generation.</li>
              <li>Living traceability graph/version — Traceability step (REVIEW_REQUIRED links stay visible).</li>
              <li>Structural verification — static C3 rules (UI/IN_MEMORY flagged REVIEW_REQUIRED).</li>
              <li>Scoped regeneration — SIMULATED C4 defects; retest PENDING until independent C4.</li>
            </ol>
          </Card>

          <Card
            title="Preview controls"
            subtitle="POST /api/v1/demo/preview/* · non-root container · no Docker socket · loopback ports only"
            actions={
              <div className="button-row">
                <Button onClick={() => build.run()} loading={build.loading} disabled={!run}>
                  Build Preview
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => start.run()}
                  loading={start.loading}
                  disabled={!preview || !["BUILT", "STOPPED"].includes(preview.status)}
                >
                  Start Preview
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => stop.run()}
                  loading={stop.loading}
                  disabled={!preview || preview.status !== "RUNNING"}
                >
                  Stop Preview
                </Button>
                {preview?.ui_url && preview.status === "RUNNING" ? (
                  <a className="btn btn-primary" href={preview.ui_url} target="_blank" rel="noreferrer">
                    Open Preview
                  </a>
                ) : null}
              </div>
            }
          >
            {build.loading ? (
              <Loading
                label="Building Docker preview image"
                startedAt={build.startedAt}
                note="This compiles the generated frontend and backend inside Linux containers. It can take several minutes."
              />
            ) : null}
            {start.loading ? <Loading label="Starting preview container" startedAt={start.startedAt} /> : null}
            {stop.loading ? <Loading label="Stopping preview container" startedAt={stop.startedAt} /> : null}
            <ErrorPanel error={build.error} context="Preview build" />
            <ErrorPanel error={start.error} context="Preview start" />
            <ErrorPanel error={stop.error} context="Preview stop" />
            {preview ? (
              <>
                <div className="result-head">
                  <Badge tone={previewTone(preview.status)}>{preview.status}</Badge>
                  <span className="muted small">{preview.updated_at_utc}</span>
                </div>
                <KeyValues
                  items={[
                    { label: "Preview ID", value: <code>{preview.preview_id}</code> },
                    { label: "UI URL", value: preview.ui_url ? <a href={preview.ui_url}>{preview.ui_url}</a> : "—" },
                    { label: "API URL", value: preview.api_url ? <code>{preview.api_url}</code> : "—" },
                    { label: "UI port", value: preview.ui_port ?? "—" },
                    { label: "API port", value: preview.api_port ?? "—" },
                    { label: "Container", value: preview.container_name ?? "—" },
                    { label: "Artifact digest", value: <Hash value={preview.artifact_digest_sha256} length={24} /> },
                    { label: "Execution claim", value: preview.execution_claim },
                    { label: "Runtime DB", value: preview.runtime_db_claim },
                  ]}
                />
                {preview.last_error ? (
                  <Callout tone="bad" title="Preview error">
                    {preview.last_error}
                  </Callout>
                ) : null}
                <Callout tone="info">
                  Open the UI URL in your browser only after status is RUNNING. CORS is bound to the exact UI origin.
                  Stop the preview when finished to release ports and remove the container.
                </Callout>
              </>
            ) : (
              <p className="muted small">No preview session yet. Build uses the verified manifest and workspace paths.</p>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}

export default withHybridFallback(HybridPreviewView, ClassicBrowserPreview, { crudRunExists: (session) => Boolean(session.generationRun) });
