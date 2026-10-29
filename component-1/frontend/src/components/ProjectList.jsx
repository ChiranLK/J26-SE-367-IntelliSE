import { useEffect, useRef, useState } from 'react'
import { deleteProject, listProjects } from '../services/api.js'
import { MAX_OFFSET, PAGE_LIMIT } from '../services/contracts.js'
import { formatDate } from '../services/format.js'
import { openNewProject, openProject } from '../services/navigation.js'

export default function ProjectList({ activeId, refreshKey, onDeleted }) {
  const [target, setTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const pendingDelete = useRef(null)
  const cancelButton = useRef(null)
  const originButton = useRef(null)
  useEffect(() => () => pendingDelete.current?.abort(), [])
  useEffect(() => { if (target) cancelButton.current?.focus() }, [target])
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
  function cancelDeletion() {
    if (pendingDelete.current) return
    setTarget(null)
    setDeleteError(null)
    originButton.current?.focus()
  }

  async function removeProject() {
    if (!target || pendingDelete.current) return
    const selected = target
    const controller = new AbortController()
    pendingDelete.current = controller
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteProject(selected.id, { signal: controller.signal })
      if (!controller.signal.aborted) {
        setTarget(null)
        onDeleted?.(selected.id)
        load(0)
      }
    } catch (problem) {
      if (!controller.signal.aborted) setDeleteError(problem)
    } finally {
      if (!controller.signal.aborted) { pendingDelete.current = null; setDeleting(false) }
    }
  }

  const { phase, page, error } = result
  return <aside className="panel projects-panel" aria-labelledby="projects-heading">
    <div className="panel-heading"><h2 id="projects-heading">Projects</h2><button type="button" className="text-button" onClick={() => load()} disabled={phase === 'loading' || deleting}>Refresh list</button></div>
    <button type="button" className="primary-button new-project" disabled={deleting} onClick={openNewProject}>+ New project</button>
    <div aria-live="polite" aria-busy={phase === 'loading'}>
      {phase === 'loading' && <p className="state-message" role="status">Loading saved projects…</p>}
      {phase === 'error' && <div className="error-message" role="alert"><p>{error}</p><button type="button" className="secondary-button" onClick={() => load()}>Retry project list</button></div>}
      {phase === 'ready' && page.items.length === 0 && <p className="state-message">{query.offset === 0 ? 'No saved projects yet. Create your first project to get started.' : 'No projects on this page. Go back or refresh the list.'}</p>}
    </div>
    {target && <section className="project-delete-confirm" role="alertdialog" aria-modal="false" aria-labelledby="delete-project-heading" aria-describedby="delete-project-description" onKeyDown={(event) => { if (event.key === 'Escape') cancelDeletion() }}>
      <h3 id="delete-project-heading">Delete project from dashboard?</h3>
      <p id="delete-project-description"><strong>{target.name}</strong> will disappear from the project list and normal retrieval. Its source, saved results and audio provenance remain in the database for recovery. This is not permanent data erasure.</p>
      {deleteError && <p role="alert">{[404, 405].includes(deleteError.status) ? 'Project deletion is unavailable or the project was not found. Restart the updated backend and refresh the list.' : deleteError.message}{deleteError.uncertain && ' Deletion may have completed. An explicit retry of this same deletion is safe; it will not delete another project.'}</p>}
      <div className="delete-confirm-actions"><button type="button" className="secondary-button" ref={cancelButton} disabled={deleting} onClick={cancelDeletion}>Cancel</button><button type="button" className="danger-button" disabled={deleting} onClick={() => { void removeProject() }}>{deleting ? 'Deleting…' : 'Delete project'}</button></div>
    </section>}
    {phase === 'ready' && <>
      <ul className="project-list">{page.items.map((project) => <li key={project.id}>
        <button type="button" className="project-link" disabled={deleting} onClick={() => openProject(project.id)} aria-current={activeId?.toLowerCase() === project.id ? 'page' : undefined}>
          <span className="project-name">{project.name}</span>
          <span className="project-meta"><span className="draft-tag">{project.status}</span><time dateTime={project.created_at}>{formatDate(project.created_at)}</time></span>
        </button>
        <button type="button" className="project-delete-button" aria-label={`Delete project ${project.name}`} disabled={deleting}
          onClick={(event) => { originButton.current = event.currentTarget; setDeleteError(null); setTarget(project) }}>Delete</button>
      </li>)}</ul>
      <nav className="pagination" aria-label="Project list pages">
        <button type="button" className="secondary-button" disabled={deleting || page.offset === 0} onClick={() => load(Math.max(0, page.offset - page.limit))}>Previous</button>
        <span>Page {Math.floor(page.offset / page.limit) + 1}</span>
        <button type="button" className="secondary-button" disabled={deleting || !page.has_more || page.offset + page.limit > MAX_OFFSET} onClick={() => load(page.offset + page.limit)}>Next</button>
      </nav>
      {page.has_more && page.offset + page.limit > MAX_OFFSET && <p className="field-help">The backend pagination limit has been reached.</p>}
    </>}
  </aside>
}
