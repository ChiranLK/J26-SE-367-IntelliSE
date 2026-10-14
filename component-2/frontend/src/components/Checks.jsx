const CHECKS = [
  { id: "plantuml", name: "PlantUML parser", about: "Can PlantUML draw it?" },
  { id: "linter", name: "Linter", about: "@startuml / @enduml, brackets, quotes" },
  { id: "uml_rules", name: "UML rules", about: "Duplicates, inheritance, connections" },
  { id: "codebert", name: "CodeBERT", about: "Fine-tuned model, 13 error types" },
];

export default function Checks({ flaggedBy = [], codebert }) {
  return (
    <div className="checks">
      {CHECKS.map((c) => {
        const found = flaggedBy.includes(c.id);
        return (
          <div key={c.id} className={found ? "check bad" : "check ok"}>
            <strong>{c.name}</strong>
            <small>{c.about}</small>
            <span>{found ? "Found a problem" : "No problem"}</span>
            {c.id === "codebert" && codebert && (
              <small>
                Predicts {codebert.prediction} ({Math.round(codebert.confidence * 100)}%)
              </small>
            )}
          </div>
        );
      })}
      {flaggedBy.includes("repair_check") && (
        <p className="error wide">
          The pipeline sent this round back: the fix asked for in the previous round was not done.
        </p>
      )}
    </div>
  );
}