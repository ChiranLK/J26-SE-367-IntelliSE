import { api } from "../api/endpoints.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";
import { Button, Callout, Card, ErrorPanel, Loading } from "./ui.jsx";

// Explicit start/stop of a generated behaviour app on a fresh loopback port (Application Preview step).
export function BehaviourAppCard({ run }) {
  const { session, set } = useSession();
  const app = session.behaviourApp;
  const start = useAction(async () => set("behaviourApp", await api.behaviourStart(run.workspace_relative_path)));
  const stop = useAction(async () => set("behaviourApp", await api.behaviourStop(run.workspace_relative_path)));

  return (
    <Card title="Run the generated app on a new port" subtitle="POST /api/v1/behaviour/apps/start · node --permission, loopback only, files re-hashed first">
      <div className="button-row">
        {app?.status === "RUNNING" ? (
          <>
            <a className="btn btn-primary" href={app.url} target="_blank" rel="noreferrer">Open generated app</a>
            <Button variant="secondary" onClick={() => stop.run()} loading={stop.loading}>Stop app</Button>
          </>
        ) : (
          <Button onClick={() => start.run()} loading={start.loading}>Start app on a new port</Button>
        )}
      </div>
      {start.loading ? <Loading label="Starting the app" startedAt={start.startedAt} note="The first start builds the React frontend (npm install + vite build), which can take a minute or two; later starts reuse the build." /> : null}
      {app?.status === "RUNNING" ? (
        <Callout tone="info" title={`Running on port ${app.port}`}>
          <a href={app.url} target="_blank" rel="noreferrer">{app.url}</a> · {app.sandbox}
        </Callout>
      ) : null}
      {app?.status === "STOPPED" ? <p className="muted small">Stopped.</p> : null}
      <ErrorPanel error={start.error} context="Start behaviour app" />
      <ErrorPanel error={stop.error} context="Stop behaviour app" />
    </Card>
  );
}
