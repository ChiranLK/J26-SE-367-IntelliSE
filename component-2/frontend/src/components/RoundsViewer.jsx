import { useState } from "react";
import Checks from "./Checks.jsx";
import Diagram from "./Diagram.jsx";

// The repair loop as a row of drafts: Round 0 is Qwen's first draft, then each repair.
export default function RoundsViewer({ run }) {
  const last = run.rounds.length - 1;
  const [selected, setSelected] = useState(last);
  const round = run.rounds[selected];

  return (
    <div>
      <ol className="drafts">
        {run.rounds.map((r, i) => (
          <li key={i}>
            <button
              className={`draft ${r.status === "VALID" ? "ok" : "bad"} ${i === selected ? "active" : ""}`}
              onClick={() => setSelected(i)}
            >
              <b>{i}</b>
              <span>{i === 0 ? "First draft" : `Repair ${i}`}</span>
              <small>{r.status === "VALID" ? "Valid" : r.status}</small>
            </button>
          </li>
        ))}
      </ol>
      <Checks flaggedBy={round.flagged_by} codebert={round.codebert} />
      <Diagram svg={round.svg} puml={round.puml} feedback={round.feedback} />
    </div>
  );
}