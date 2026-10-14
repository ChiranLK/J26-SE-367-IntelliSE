import { useEffect, useState } from "react";
import { getJson } from "../api.js";
import RoundsViewer from "../components/RoundsViewer.jsx";

// Every /generate run is saved in the database; open one to see its rounds again.
export default function History() {
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson("/runs").then(setRuns).catch((e) => setError(e.message));
  }, []);

  const open = (id) => getJson("/runs/" + id).then(setRun).catch((e) => setError(e.message));

  return (
    <div className="split">
      <section className="panel">
        <h1>History</h1>
        {error && <p className="error">{error}</p>}
        {runs.length === 0 && !error && <p className="hint">No runs yet. Generate a diagram first.</p>}
        {runs.map((r) => (
          <button key={r.id} className={run?.id === r.id ? "run active" : "run"} onClick={() => open(r.id)}>
            <span>#{r.id} {r.project}</span>
            <small>{r.diagram_type === "CLASS" ? "Class" : "Use case"} diagram, {r.created}</small>
            <em className={r.valid_final ? "ok" : "bad"}>{r.valid_final ? "Valid" : "Not fixed"}</em>
          </button>
        ))}
      </section>

      <section className="workspace">
        {run ? <RoundsViewer key={run.id} run={run} /> : <p className="empty">Choose a run to see its rounds.</p>}
      </section>
    </div>
  );
}