import { useEffect, useState } from 'react'

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001').replace(/\/+$/, '')
const healthUrl = `${apiBase}/api/v1/component-1/health`
const capabilities = [
  ['01', 'Understand client communication', 'Transform client communications into structured requirements.'],
  ['02', 'Classify & assess requirements', 'Separate functional and non-functional requirements and identify quality issues.'],
  ['03', 'Create Agile artifacts & an SRS', 'Generate development artifacts and a software requirements specification.'],
  ['04', 'Review & refine with clients', 'Support client review and targeted regeneration of affected artifacts.'],
]

export default function App() {
  const [status, setStatus] = useState('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    let active = true

    async function checkHealth() {
      try {
        const response = await fetch(healthUrl, { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error('Health request failed')
        const health = await response.json()
        if (health.status !== 'ok' || health.component !== 'component-1' || health.service !== 'requirement-engineering') {
          throw new Error('Unexpected service response')
        }
        if (active) setStatus('connected')
      } catch {
        if (active) setStatus('unavailable')
      } finally {
        clearTimeout(timeout)
      }
    }
    checkHealth()
    return () => { active = false; clearTimeout(timeout); controller.abort() }
  }, [attempt])

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#main" aria-label="InteliSE home"><span className="brand-icon">i</span>InteliSE<span className="brand-tag">RESEARCH PLATFORM</span></a>
        <span className="stage">Foundation prototype</span>
      </header>
      <main id="main">
        <section className="hero" aria-labelledby="title">
          <div className="hero-copy">
            <p className="eyebrow">COMPONENT 01 / REQUIREMENT ENGINEERING</p>
            <h1 id="title">AI-Powered Intelligent Requirement Engineering Agent for Agile Software Development</h1>
            <p className="intro">From client conversations to clear, structured requirements. A foundation for bringing shared understanding into Agile software development.</p>
            <p className="scope"><span className="scope-dot" /> Current scope: application foundation & service connectivity</p>
          </div>
          <aside className="connection" aria-labelledby="connection-title">
            <div className="card-top"><span className="eyebrow">SERVICE CONNECTION</span><span className={`status-dot ${status}`} /></div>
            <h2 id="connection-title">Requirement engineering API</h2>
            <div role="status" aria-live="polite" aria-atomic="true">
              <p className={`connection-status ${status}`}>{status === 'loading' ? 'Checking connection…' : status === 'connected' ? 'Backend connected' : 'Backend unavailable'}</p>
              <p className="connection-detail">{status === 'loading' ? 'Waiting for the local service to respond.' : status === 'connected' ? 'The API is responding. Database and AI readiness are not checked.' : 'Could not verify the service. Check the backend address, local server, and CORS configuration.'}</p>
            </div>
            <div className="endpoint"><span>HEALTH ENDPOINT</span><code>{healthUrl}</code></div>
            {status === 'unavailable' && <button onClick={() => { setStatus('loading'); setAttempt(value => value + 1) }}>Retry connection <span aria-hidden="true">↗</span></button>}
            <p className="local-note">No database or AI service is required for this check.</p>
          </aside>
        </section>
        <section className="roadmap" aria-labelledby="roadmap-title">
          <div className="section-heading"><div><p className="eyebrow">LOOKING AHEAD</p><h2 id="roadmap-title">The planned workflow</h2></div><p>Research capabilities to be implemented in future tasks.</p></div>
          <div className="capabilities">{capabilities.map(([number, title, description]) => (
            <article className="capability" key={number}><div className="capability-top"><span className="number">{number}</span><span className="planned">Planned</span></div><h3>{title}</h3><p>{description}</p></article>
          ))}</div>
        </section>
        <div className="foundation-note"><strong>A starting point for the research.</strong><p>This foundation provides the application shell and health connection only. It does not process requirements or represent 50% completion of the component.</p></div>
      </main>
      <footer><span>J26-SE-367 · InteliSE</span><span>Component 01 / Foundation</span></footer>
    </div>
  )
}
