import { useEffect, useState } from 'react'
import { listProjects } from '../services/api.js'
import { MAX_OFFSET, PAGE_LIMIT } from '../services/contracts.js'
import { formatDate } from '../services/format.js'
import { openNewProject, openProject } from '../services/navigation.js'

export default function ProjectList({ activeId, refreshKey }) {
  const [query, setQuery] = useState({ offset: 0, revision: 0 })
  const [result, setResult] = useState({ phase: 'loading', page: null, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    listProjects({ limit: PAGE_LIMIT, offset: query.offset, signal: controller.signal })
      .then((page) => { if (!controller.signal.aborted) setResult({ phase: 'ready', page, error: '' }) })
      .catch((error) => { if (!controller.signal.aborted) setResult({ phase: 'error', page: null, error: error.message }) })
    return () => controller.abort()
  }, [query, refreshKey])

  function load(offset = query.offset) {
    setResult({ phase: 'loading', page: null, error: '' })
    setQuery({ offset, revision: query.revision + 1 })
  }
  const { phase, page, error } = result
  return <aside className="panel projects-panel" aria-labelledby="projects-heading">
    <div className="panel-heading"><h2 id="projects-heading">Projects</h2><button type="button" className="text-button" onClick={() => load()} disabled={phase === 'loading'}>Refresh list</button></div>
    <button type="button" className="primary-button new-project" onClick={openNewProject}>+ New project</button>
    <div aria-live="polite" aria-busy={phase === 'loading'}>
      {phase === 'loading' && <p className="state-message" role="status">Loading saved projects…</p>}
      {phase === 'error' && <div className="error-message" role="alert"><p>{error}</p><button type="button" className="secondary-button" onClick={() => load()}>Retry project list</button></div>}
      {phase === 'ready' && page.items.length === 0 && <p className="state-message">{query.offset === 0 ? 'No saved projects yet. Create your first project to get started.' : 'No projects on this page. Go back or refresh the list.'}</p>}
    </div>
    {phase === 'ready' && <>
      <ul className="project-list">{page.items.map((project) => <li key={project.id}>
        <button type="button" className="project-link" onClick={() => openProject(project.id)} aria-current={activeId?.toLowerCase() === project.id ? 'page' : undefined}>
          <span className="project-name">{project.name}</span>
          <span className="project-meta"><span className="draft-tag">{project.status}</span><time dateTime={project.created_at}>{formatDate(project.created_at)}</time></span>
        </button>
      </li>)}</ul>
      <nav className="pagination" aria-label="Project list pages">
        <button type="button" className="secondary-button" disabled={page.offset === 0} onClick={() => load(Math.max(0, page.offset - page.limit))}>Previous</button>
        <span>Page {Math.floor(page.offset / page.limit) + 1}</span>
        <button type="button" className="secondary-button" disabled={!page.has_more || page.offset + page.limit > MAX_OFFSET} onClick={() => load(page.offset + page.limit)}>Next</button>
      </nav>
      {page.has_more && page.offset + page.limit > MAX_OFFSET && <p className="field-help">The backend pagination limit has been reached.</p>}
    </>}
  </aside>
}
