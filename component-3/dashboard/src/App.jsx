import { useState } from "react";
import { Badge } from "./components/ui.jsx";
import { BackendProvider, useBackend } from "./state/backend.jsx";
import { SessionProvider, useSession } from "./state/session.jsx";
import DesignStack from "./pages/DesignStack.jsx";
import Generation from "./pages/Generation.jsx";
import Inputs from "./pages/Inputs.jsx";
import Overview from "./pages/Overview.jsx";
import Readiness from "./pages/Readiness.jsx";
import ScopedRegeneration from "./pages/ScopedRegeneration.jsx";
import Traceability from "./pages/Traceability.jsx";

export const PAGES = [
  { id: "overview", label: "Overview", step: "0", Component: Overview },
  { id: "inputs", label: "C1/C2 Inputs", step: "1", Component: Inputs },
  { id: "design", label: "Design & Stack", step: "2", Component: DesignStack },
  { id: "generation", label: "Code Generation", step: "3", Component: Generation },
  { id: "traceability", label: "Living Traceability", step: "4", Component: Traceability },
  { id: "scoped", label: "Scoped Regeneration", step: "5", Component: ScopedRegeneration },
  { id: "readiness", label: "Readiness", step: "6", Component: Readiness },
];

function isDone(pageId, session) {
  switch (pageId) {
    case "inputs":
      return Boolean(session.validation?.ok);
    case "design":
      return session.approval?.status === "APPROVED_FOR_MVP_GENERATION";
    case "generation":
      return Boolean(session.generationRun);
    case "traceability":
      return Boolean(session.graph);
    case "scoped":
      return session.scoped.runs.length > 0;
    default:
      return false;
  }
}

function Sidebar({ current, onNavigate }) {
  const { session, reset } = useSession();
  const { health, error, loading, overview } = useBackend();
  const apiTone = loading ? "neutral" : health ? "ok" : "bad";
  const apiLabel = loading ? "checking API…" : health ? "API healthy" : "API unreachable";
  const ollama = overview?.ollama;
  return (
    <nav className="sidebar" aria-label="Demo workflow">
      <div className="brand">
        <div className="brand-mark">IS</div>
        <div>
          <div className="brand-name">InteliSE</div>
          <div className="brand-sub">Component 3 · Research Demo</div>
        </div>
      </div>
      <ul className="nav-list">
        {PAGES.map((page) => (
          <li key={page.id}>
            <button
              type="button"
              className={`nav-item${current === page.id ? " nav-active" : ""}`}
              aria-current={current === page.id ? "page" : undefined}
              onClick={() => onNavigate(page.id)}
            >
              <span className="nav-step">{isDone(page.id, session) ? "✓" : page.step}</span>
              <span>{page.label}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="sidebar-foot">
        <div className="status-line">
          <span className={`dot dot-${apiTone}`} />
          <span>{apiLabel}</span>
        </div>
        <div className="status-line">
          <span className={`dot dot-${ollama ? (ollama.reachable && ollama.model_installed ? "ok" : "warn") : "neutral"}`} />
          <span>
            {ollama
              ? ollama.reachable
                ? ollama.model_installed
                  ? `Ollama · ${ollama.configured_model}`
                  : "Ollama model missing"
                : "Ollama unreachable"
              : "Ollama unknown"}
          </span>
        </div>
        {error && !loading ? <div className="foot-note">{error.message}</div> : null}
        <div className="foot-badges">
          <Badge tone="sim">C1/C2 SIMULATED</Badge>
          <Badge tone="bad-soft">C4 NOT INTEGRATED</Badge>
        </div>
        <button type="button" className="btn btn-ghost btn-small" onClick={reset}>
          Reset session
        </button>
      </div>
    </nav>
  );
}

function Shell() {
  const [current, setCurrent] = useState("overview");
  const page = PAGES.find((item) => item.id === current) ?? PAGES[0];
  const Page = page.Component;
  return (
    <div className="shell">
      <Sidebar current={current} onNavigate={setCurrent} />
      <main className="content" id="main">
        <Page navigate={setCurrent} />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BackendProvider>
      <SessionProvider>
        <Shell />
      </SessionProvider>
    </BackendProvider>
  );
}
