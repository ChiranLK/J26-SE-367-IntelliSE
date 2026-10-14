import { useState } from "react";
import { postJson } from "../api.js";
import Checks from "../components/Checks.jsx";
import Diagram from "../components/Diagram.jsx";

// Check one diagram with CodeBERT + PlantUML + UML rules. No LLM, so it answers in about a second.
export default function ValidateUml() {
  const [puml, setPuml] = useState("");
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  async function validate() {
    setError("");
    try {
      setReport(await postJson("/validate", { puml }));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="split">
      <section className="panel">
        <h1>Validate a diagram</h1>
        <p className="hint">Paste PlantUML code to see what the validator finds.</p>
        <textarea className="mono" rows={20} value={puml} onChange={(e) => setPuml(e.target.value)} placeholder="@startuml ... @enduml" />
        <button className="primary" onClick={validate} disabled={!puml.trim()}>Validate</button>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="workspace">
        {report ? (
          <>
            <div className={report.is_valid ? "verdict ok" : "verdict bad"}>
              <strong>{report.is_valid ? "Valid diagram" : report.syntax_error_type}</strong>
            </div>
            <Checks flaggedBy={report.flagged_by} codebert={report.codebert} />
            <Diagram svg={report.svg} puml={report.plantuml_source} feedback={report.feedback} />
          </>
        ) : (
          <p className="empty">The result and the drawn diagram will appear here.</p>
        )}
      </section>
    </div>
  );
}