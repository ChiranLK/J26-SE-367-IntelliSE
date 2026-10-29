import { useState, useSyncExternalStore } from 'react'
import ProjectFlow from './components/ProjectFlow.jsx'
import ProjectList from './components/ProjectList.jsx'
import RequirementTester from './components/RequirementTester.jsx'
import { getHash, openProject, projectFromHash, subscribeToHash } from './services/navigation.js'

export default function App() {
  const hash = useSyncExternalStore(subscribeToHash, getHash, () => '')
  const projectId = projectFromHash(hash) ?? (hash === '' ? new URLSearchParams(window.location.search).get('project') : null)
  const [listRevision, setListRevision] = useState(0)

  function projectSaved(project) {
    setListRevision((revision) => revision + 1)
    openProject(project.id)
  }

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
        <section className="intro dashboard-intro" aria-labelledby="page-title">
          <div className="hero-copy">
            <p className="eyebrow"><span aria-hidden="true" /> INTELLISE · COMPONENT 01</p>
            <h1 id="page-title">Requirement Engineering</h1>
          </div>


        </section>

        {hash === '#model-test' ? <section className="standalone-model-test" aria-label="Standalone model diagnostic">
          <a href="#new-project" className="diagnostic-back">← Back to projects</a>
          <RequirementTester />
        </section> : <>
        <section className="workspace" aria-label="Project and requirement extraction workspace">
          <ProjectList key={listRevision} activeId={projectId} refreshKey={listRevision} onDeleted={(id) => { setListRevision((revision) => revision + 1); if (projectId?.toLowerCase() === id) window.location.hash = 'new-project' }} />
          <div className="workspace-content">
            <ProjectFlow key={projectId ?? "new"} projectId={projectId} onSaved={projectSaved} />
          </div>
        </section>
        </>}

        <div className="research-note"><span className="note-symbol" aria-hidden="true">i</span><p>Generated requirements and baseline classifications support human review. They do not establish completeness, correctness or client approval.</p></div>
      </main>
      <footer><span>IntelliSE <span aria-hidden="true">/</span> Intelligent Agile Software Engineering</span><span>Fourth-year research project · Component 01</span></footer>
    </>
  )
}
