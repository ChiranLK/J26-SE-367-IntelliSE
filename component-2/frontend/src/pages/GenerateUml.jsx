import { useState } from "react";
import { postJson } from "../api.js";
import RoundsViewer from "../components/RoundsViewer.jsx";

export default function GenerateUml() {
  const [srs, setSrs] = useState("");
  const [type, setType] = useState("CLASS");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setBusy(true);
    setError("");
    try {
      setRun(await postJson("/generate", { srs, diagram_type: type }));
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <div className="split">
      <section className="panel">
        <h1>Generate a UML diagram</h1>
        <p className="hint">Qwen drafts the diagram from your SRS, then the validator checks it and asks for repairs.</p>

        <label className="file">
          Load SRS from a .txt file
          <input type="file" accept=".txt" onChange={(e) => e.target.files[0]?.text().then(setSrs)} />
        </label>
        <textarea rows={16} value={srs} onChange={(e) => setSrs(e.target.value)} placeholder="Or paste the SRS here" />

        <div className="toggle">
          <button className={type === "CLASS" ? "on" : ""} onClick={() => setType("CLASS")}>Class diagram</button>
          <button className={type === "USE_CASE" ? "on" : ""} onClick={() => setType("USE_CASE")}>Use case diagram</button>
        </div>

        <button className="primary" onClick={generate} disabled={busy || !srs.trim()}>
          {busy ? "Generating…" : "Generate diagram"}
        </button>
        {busy && <p className="hint">Qwen runs on the CPU, so this takes 3–6 minutes.</p>}
        {error && <p className="error">{error}</p>}
      </section>

      <section className="workspace">
        {run ? (
          <RoundsViewer key={run.id} run={run} />
        ) : (
          <p className="empty">Paste an SRS and generate a diagram. Every repair round will appear here.</p>
        )}
      </section>
    </div>
  );
}