import { useBackendStatus } from './hooks/useBackendStatus.js'

const capabilities = [
  ['Text input', 'Capture stakeholder needs in plain language.'],
  ['Requirement extraction', 'Identify requirements from supplied text.'],
  ['FR/NFR classification', 'Organize functional and non-functional needs.'],
  ['Quality validation', 'Review clarity, completeness, and consistency.'],
  ['Agile artifacts', 'Shape requirements into user stories and acceptance criteria.'],
  ['Draft SRS generation', 'Assemble a draft software requirements specification.'],
]

const statusLabels = {
  loading: 'Checking connection',
  connected: 'Connected',
  unavailable: 'Unavailable',
}

export default function App() {
  const { state, detail, retry } = useBackendStatus()

  return (
    <>
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="site-header">
        <div className="brand" aria-label="IntelliSE">
          <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
          <span>Intelli<span className="brand-accent">SE</span></span>
        </div>
        <span className="header-note">Research project <span className="header-divider">/</span> Component 01</span>
      </header>

      <main id="main" tabIndex={-1}>
        <section className="intro" aria-labelledby="page-title">
          <div className="hero-copy">
            <p className="eyebrow"><span aria-hidden="true" /> INTELLISE · COMPONENT 01</p>
            <h1 id="page-title">Requirement<br className="desktop-break" /> Engineering Agent</h1>
            <p className="hero-description">From stakeholder needs to a clearer foundation for Agile software development.</p>
            <p className="hero-detail">An AI-powered research component designed to help teams capture, structure, and review software requirements.</p>
            <div className="foundation-label"><span aria-hidden="true">◈</span> Frontend foundation <span className="label-divider" aria-hidden="true" /> Development in progress</div>
          </div>

          <aside className="connection-card" aria-labelledby="connection-heading">
            <div className="card-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="4" y="4" width="16" height="6" rx="2" /><rect x="4" y="14" width="16" height="6" rx="2" /><path d="M8 7h.01M8 17h.01M13 7h4M13 17h4" strokeLinecap="round" /></svg>
            </div>
            <p className="card-overline">SERVICE STATUS</p>
            <h2 id="connection-heading">Backend connectivity</h2>
            <div className="connection-message" role="status" aria-live="polite" aria-atomic="true">
              <p className={`status-badge ${state}`}><span className="status-dot" aria-hidden="true" />{statusLabels[state]}</p>
              <p className="status-description">{state === 'loading'
                ? 'Checking the Component 01 backend. This usually takes a moment.'
                : state === 'connected'
                  ? 'The Component 01 backend is responding to health requests.'
                  : detail}</p>
            </div>
            <button className="retry-button" type="button" onClick={() => { if (state !== 'loading') void retry() }} aria-disabled={state === 'loading'}>
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.7-1L20 9M4 15l2.2 3A7 7 0 0 0 17.9 17" /></svg>
              {state === 'loading' ? 'Checking…' : 'Retry connection'}
            </button>
            <p className="connection-note">Connectivity only. This does not indicate database or AI readiness.</p>
          </aside>
        </section>

        <section className="capabilities" aria-labelledby="capabilities-title">
          <div className="section-heading">
            <div><p className="eyebrow section-eyebrow">THE ROAD AHEAD</p><h2 id="capabilities-title">Planned capabilities</h2></div>
            <p>Future work. These features are not available yet.</p>
          </div>
          <ul className="capability-grid">
            {capabilities.map(([title, description], index) => (
              <li className="capability" key={title}>
                <div className="capability-top"><span className="capability-number" aria-hidden="true">0{index + 1}</span><span className="planned-tag">Planned</span></div>
                <h3>{title}</h3><p>{description}</p>
              </li>
            ))}
          </ul>
        </section>
        <div className="research-note"><span className="note-symbol" aria-hidden="true">i</span><p>This foundation introduces the component and its service connection. Requirement processing will be added in future development.</p></div>
      </main>
      <footer><span>IntelliSE <span aria-hidden="true">/</span> Intelligent Agile Software Engineering</span><span>Fourth-year research project · Component 01</span></footer>
    </>
  )
}
