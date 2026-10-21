import { ErrorPanel, Loading, PageHeader } from "../components/ui.jsx";
import { useBackend } from "../state/backend.jsx";

// Where Component 3 sits between the other InteliSE components (from the proposal's architecture).
const FLOW = [
  { id: "c1", tag: "C1", title: "Requirements", text: "What the app must do", here: false },
  { id: "c2", tag: "C2", title: "Design", text: "How the app is designed", here: false },
  { id: "c3", tag: "C3", title: "This component", text: "Builds the app and keeps every part linked to its requirement", here: true },
  { id: "c4", tag: "C4", title: "Testing", text: "Tests the app and reports defects back", here: false },
];

export default function Overview() {
  const { error, loading } = useBackend();

  return (
    <div className="page">
      <PageHeader
        title="Component 3 Research Dashboard"
        subtitle="Generate traceable software and maintain living requirement links."
      />

      <section className="research-hero">
        <div>
          <span className="eyebrow">INTELISE · COMPONENT 3</span>
          <h2>From approved design evidence to a traceable application</h2>
          <p>Component 3 takes the approved requirements (C1) and the released design (C2), builds the application, and keeps a living link from every requirement to its design, code, API, database and test hook.</p>
        </div>
        <ol className="hero-flow" aria-label="Where Component 3 fits" data-testid="hero-flow">
          {FLOW.map((item) => (
            <li key={item.id} className={`hero-flow-item${item.here ? " hero-flow-here" : ""}`}>
              <span className="hero-flow-tag">{item.tag}</span>
              <span className="hero-flow-body">
                <strong>{item.title}</strong>
                <small>{item.text}</small>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {loading ? <Loading label="Checking Component 3 services" /> : null}
      <ErrorPanel error={error} context="Service status" />
    </div>
  );
}
