import { svgSrc } from "../api.js";

// One diagram on the drafting board, with what is wrong and the PlantUML code
export default function Diagram({ svg, puml, feedback = [] }) {
  return (
    <div>
      <div className="board">
        <img src={svgSrc(svg)} alt="UML diagram" />
      </div>
      {feedback.length > 0 && (
        <div className="feedback">
          <h3>What the validator found</h3>
          <ul>{feedback.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </div>
      )}
      <details className="code">
        <summary>PlantUML code</summary>
        <pre>{puml}</pre>
      </details>
    </div>
  );
}