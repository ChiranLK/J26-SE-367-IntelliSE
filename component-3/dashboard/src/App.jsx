import { useState } from "react";
import { MemoryRouter, useInRouterContext, useLocation, useNavigate } from "react-router-dom";
import { Badge, StatusBadge } from "./components/ui.jsx";
import { BackendProvider, useBackend } from "./state/backend.jsx";
import { SessionProvider, useSession } from "./state/session.jsx";
import DesignStack from "./pages/DesignStack.jsx";
import Generation from "./pages/Generation.jsx";
import Inputs from "./pages/Inputs.jsx";
import Overview from "./pages/Overview.jsx";
import Readiness from "./pages/Readiness.jsx";
import ScopedRegeneration from "./pages/ScopedRegeneration.jsx";
import Traceability from "./pages/Traceability.jsx";
import BrowserPreview from "./pages/BrowserPreview.jsx";

export const PAGES = [
  { id: "overview", label: "Dashboard", step: "0", Component: Overview },
  { id: "inputs", label: "C1/C2 Inputs", step: "1", Component: Inputs },
  { id: "design", label: "Design & Stack", step: "2", Component: DesignStack },
  { id: "generation", label: "Code Generation", step: "3", Component: Generation },
  { id: "preview", label: "Application Preview", step: "4", Component: BrowserPreview },
  { id: "traceability", label: "Living Traceability", step: "5", Component: Traceability },
  { id: "scoped", label: "Scoped Regeneration", step: "6", Component: ScopedRegeneration },
  { id: "readiness", label: "Readiness", step: "7", Component: Readiness },
];

export const PAGE_ROUTES = {
  overview: "/dashboard",
  inputs: "/inputs",
  design: "/dashboard/designstack",
  generation: "/dashboard/generation",
  preview: "/dashboard/preview",
  traceability: "/dashboard/traceability",
  scoped: "/dashboard/scoped",
  readiness: "/dashboard/readiness",
};

export const PATH_TO_PAGE = {
  "": "overview",
  "/": "overview",
  "dashboard": "overview",
  "overview": "overview",
  "inputs": "inputs",
  "c1-c2": "inputs",
  "c1c2": "inputs",
  "design": "design",
  "designstack": "design",
  "design-stack": "design",
  "stack": "design",
  "generation": "generation",
  "code-generation": "generation",
  "preview": "preview",
  "browser-preview": "preview",
  "traceability": "traceability",
  "scoped": "scoped",
  "scoped-regeneration": "scoped",
  "readiness": "readiness",
};

export function getPageIdFromPath(pathname) {
  const clean = (pathname || "").replace(/^\/+|\/+$/g, "");
  if (!clean || clean === "dashboard" || clean === "overview") return "overview";
  const segments = clean.split("/");
  const target = segments[segments.length - 1].toLowerCase();
  return PATH_TO_PAGE[target] ?? "overview";
}


const PIPELINE = [
  { id: "inputs", label: "C1/C2 input" },
  { id: "design", label: "Design" },
  { id: "generation", label: "Generation" },
  { id: "traceability", label: "Traceability" },
  { id: "scoped", label: "C4 feedback" },
  { id: "readiness", label: "Readiness" },
];

function isDone(pageId, session) {
  // If files are being uploaded, no pages are done except the current inputs page
  if (session.uploading) {
    return pageId === "inputs";
  }
  switch (pageId) {
    case "inputs": return Boolean(session.validation?.ok);
    case "design": return session.approval?.status === "APPROVED_FOR_MVP_GENERATION";
    case "generation": return Boolean(session.generationRun);
    case "preview": return session.preview?.status === "RUNNING";
    case "traceability": return Boolean(session.graph);
    case "scoped": return session.scoped.runs.length > 0;
    default: return false;
  }
}

function projectLabel(session) {
  const fixtureId = session.fixtures?.inputPackage?.fixture_id;
  if (fixtureId) {
    return fixtureId.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
  return session.validation?.generationContext?.project_id ?? "No project loaded";
}

function Sidebar({ current, onNavigate }) {
  const { session, reset } = useSession();
  const { health, error, loading, overview } = useBackend();
  const apiTone = loading ? "neutral" : health ? "ok" : "bad";
  const apiLabel = loading ? "Checking API..." : health ? "API healthy" : "API unreachable";
  const ollama = overview?.ollama;
  
  const isNavigationDisabled = session.uploading;
  
  return (
    <nav className="sidebar" aria-label="Demo workflow">
      <div className="brand">
        <div className="brand-mark">IS</div>
        <div><div className="brand-name">InteliSE</div><div className="brand-sub">Traceable generation lab</div></div>
      </div>
      <div className="nav-caption">WORKFLOW</div>
      <ul className="nav-list">
        {PAGES.map((page) => {
          // Disable navigation to pages beyond inputs while uploading
          const canNavigate = !isNavigationDisabled || page.id === "inputs" || page.id === current;
          return (
            <li key={page.id}>
              <button 
                type="button" 
                className={`nav-item${current === page.id ? " nav-active" : ""}`} 
                aria-current={current === page.id ? "page" : undefined} 
                onClick={() => canNavigate && onNavigate(page.id)}
                disabled={!canNavigate}
                title={!canNavigate ? "Complete input upload and validation first" : ""}
              >
                <span className="nav-step">{isDone(page.id, session) ? "✓" : page.step}</span><span>{page.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="sidebar-foot">
        {session.uploading && <div className="status-line"><span className="dot dot-neutral" /><span>Uploading files...</span></div>}
        <div className="status-line"><span className={`dot dot-${apiTone}`} /><span>{apiLabel}</span></div>
        <div className="status-line">
          <span className={`dot dot-${ollama ? (ollama.reachable && ollama.model_installed ? "ok" : "warn") : "neutral"}`} />
          <span>{ollama ? (ollama.reachable ? (ollama.model_installed ? `Ollama: ${ollama.configured_model}` : "Ollama model missing") : "Ollama unreachable") : "Ollama unknown"}</span>
        </div>
        {error && !loading ? <div className="foot-note">{error.message}</div> : null}
        <div className="foot-badges"><Badge tone="bad-soft">C4 NOT INTEGRATED</Badge></div>
        <button type="button" className="btn btn-ghost btn-small" onClick={reset} disabled={session.uploading}>Reset session</button>
      </div>
    </nav>
  );
}

function Topbar({ current, onNavigate }) {
  const { session } = useSession();
  const projectId = session.validation?.generationContext?.project_id ?? "Awaiting validated input";
  const isNavigationDisabled = session.uploading;
  return (
    <>
      <header className="topbar">
        <div><span className="topbar-label">PROJECT</span><strong>{projectLabel(session)}</strong><div className="topbar-project-id">Project ID: {projectId}</div></div>
        <div className="topbar-status"><Badge tone="sim">RESEARCH PROTOTYPE</Badge><StatusBadge status="BLOCKED" label="DEPLOYMENT BLOCKED" />{session.uploading && <Badge tone="neutral">UPLOADING...</Badge>}</div>
      </header>
      <div className="pipeline" aria-label="Pipeline status">
        {PIPELINE.map((item, index) => {
          const active = item.id === current || (item.id === "generation" && current === "preview");
          const canNavigate = !isNavigationDisabled || item.id === current;
          return (
            <button 
              key={item.id} 
              type="button" 
              className={`pipeline-step${active ? " pipeline-active" : ""}`} 
              onClick={() => canNavigate && onNavigate(item.id)}
              disabled={!canNavigate}
              title={!canNavigate ? "Complete input upload and validation first" : ""}
            >
              <span className={`pipeline-dot${isDone(item.id, session) ? " pipeline-done" : ""}`} />{item.label}
              {index < PIPELINE.length - 1 ? <span className="pipeline-arrow">›</span> : null}
            </button>
          );
        })}
      </div>
    </>
  );
}

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const current = getPageIdFromPath(location.pathname);
  const page = PAGES.find((item) => item.id === current) ?? PAGES[0];
  const Page = page.Component;

  const handleNavigate = (target) => {
    const pageId = PATH_TO_PAGE[target] ?? target;
    const path = PAGE_ROUTES[pageId] ?? `/${pageId}`;
    navigate(path);
  };

  return (
    <div className="shell">
      <Sidebar current={current} onNavigate={handleNavigate} />
      <div className="main-column">
        <Topbar current={current} onNavigate={handleNavigate} />
        <main className="content" id="main">
          <Page navigate={handleNavigate} />
        </main>
      </div>
    </div>
  );
}

function RouterBoundary({ children }) {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return children;
  }
  const initial = typeof window !== "undefined" && window.location?.pathname && window.location.pathname !== "/"
    ? [window.location.pathname]
    : ["/dashboard"];
  return <MemoryRouter initialEntries={initial}>{children}</MemoryRouter>;
}

export default function App() {
  return (
    <BackendProvider>
      <SessionProvider>
        <RouterBoundary>
          <Shell />
        </RouterBoundary>
      </SessionProvider>
    </BackendProvider>
  );
}
