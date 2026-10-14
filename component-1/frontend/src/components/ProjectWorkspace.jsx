import { useEffect, useRef, useState } from 'react'
import { classificationLabels, classifyExtraction, getLatestClassification, getLatestExtraction, getProject, listProjects } from '../services/projectApi.js'

function ClassificationMetadata({ result }) {
  return <dl className="classification-metadata">
    <div><dt>Model</dt><dd>{result.model_identifier === 'tfidf-logistic-regression' ? 'TF-IDF + logistic regression' : result.model_identifier}</dd></div>
    <div><dt>Model version</dt><dd><code>{result.model_version}</code></dd></div>
    <div><dt>Classified</dt><dd><time dateTime={result.classified_at}>{new Date(result.classified_at).toLocaleString()}</time></dd></div>
    <div><dt>Classification ID</dt><dd><code>{result.classification_id}</code></dd></div>
  </dl>
}

function SavedProject({ projectId, onBusyChange }) {
  const [view, setView] = useState({ phase: 'loading', project: null, extraction: null, classification: null, classificationState: 'loading', error: null, notice: '' })
  const [revision, setRevision] = useState(0)
  const [classifying, setClassifying] = useState(false)
  const busy = useRef(false)
  const mounted = useRef(false)
  const previousRun = useRef(null)
  const readRequest = useRef(null)

  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    readRequest.current = controller
    async function load() {
      try {
        const [project, extraction] = await Promise.all([
          getProject(projectId, { signal: controller.signal }),
          getLatestExtraction(projectId, { signal: controller.signal }),
        ])
        if (controller.signal.aborted) return
        const notice = previousRun.current && previousRun.current !== extraction?.run_id
          ? 'A newer extraction is displayed. Classification results from the previous run are not applied.' : ''
        previousRun.current = extraction?.run_id ?? null
        setView({ phase: 'ready', project, extraction, classification: null, classificationState: extraction ? 'loading' : 'none', error: null, notice })
        if (extraction) {
          try {
            const classification = await getLatestClassification(projectId, extraction, { signal: controller.signal })
            if (!controller.signal.aborted) setView((current) => ({ ...current, classification, classificationState: classification ? 'saved' : 'none' }))
          } catch (error) {
            if (!controller.signal.aborted) setView((current) => ({ ...current, classificationState: 'error', error }))
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) setView((current) => ({ ...current, phase: 'error', error }))
      }
    }
    void load()
    return () => { mounted.current = false; controller.abort() }
  }, [projectId, revision])

  function refresh() {
    if (busy.current) return
    readRequest.current?.abort()
    setView((current) => ({ ...current, phase: 'loading', classification: null, error: null }))
    setRevision((current) => current + 1)
  }

  async function classify() {
    if (busy.current || !view.extraction || view.classificationState === 'loading') return
    busy.current = true // Synchronous guard before React renders the disabled button.
    setClassifying(true)
    onBusyChange(true)
    setView((current) => ({ ...current, error: null }))
    let saved = false
    try {
      const extraction = view.extraction
      const classification = await classifyExtraction(projectId, extraction)
      saved = true
      if (!mounted.current) return
      setView((current) => ({ ...current, classification, classificationState: 'saved' }))
      // Another client may have created a new extraction while this POST was pending.
      const latest = await getLatestExtraction(projectId)
      if (!mounted.current) return
      if (latest && latest.run_id !== extraction.run_id) {
        previousRun.current = latest.run_id
        setView((current) => ({ ...current, extraction: latest, classification: null, classificationState: 'loading',
          notice: `Classification was saved for older extraction ${extraction.run_id}. The newer extraction is displayed without those badges.` }))
        const currentClassification = await getLatestClassification(projectId, latest)
        if (mounted.current) setView((current) => ({ ...current, classification: currentClassification, classificationState: currentClassification ? 'saved' : 'none' }))
      }
    } catch (error) {
      if (mounted.current) setView((current) => ({ ...current, error,
        classificationState: current.classificationState === 'loading' ? 'error' : current.classificationState,
        notice: saved ? 'Classification was saved, but checking the latest extraction/results failed. Refresh saved results.' : current.notice }))
    } finally {
      busy.current = false
      if (mounted.current) setClassifying(false)
      onBusyChange(false)
    }
  }

  if (view.phase === 'loading') return <div className="project-detail" role="status">Loading project and saved extraction…</div>
  if (view.phase === 'error') return <div className="project-detail"><p role="alert">{view.error.message}</p><button className="workspace-button" onClick={refresh}>Retry loading project</button></div>
  const { project, extraction, classification, classificationState, error, notice } = view
  // Defensive mapping also guards against a stale response after an extraction change.
  let labels = new Map()
  let mappingError = null
  if (classification && extraction) {
    try { labels = classificationLabels(classification, extraction, projectId) } catch (problem) { mappingError = problem.message }
  }
  const waiting = classifying || classificationState === 'loading'

  return <article className="project-detail" aria-labelledby="saved-project-title">
    <div className="workspace-heading"><h3 id="saved-project-title">{project.name}</h3>
      <button className="workspace-button" disabled={waiting} onClick={refresh}>Refresh saved results</button></div>
    <p className="record-id">Project <code>{project.id}</code></p>
    <details><summary>Original discussion</summary><p className="source-discussion">{project.discussion_text}</p></details>
    {!extraction ? <p role="status">No saved extraction exists for this project. Save an extraction through the backend before classifying requirements.</p> : <>
      <div className="workspace-heading extraction-heading"><div><h4>Saved requirement candidates</h4><p className="record-id">Extraction <code>{extraction.run_id}</code></p></div>
        <button className="workspace-button primary" disabled={waiting || !extraction.candidates.length} onClick={() => { void classify() }}>
          {classifying ? 'Classifying…' : 'Classify requirements'}
        </button></div>
      <div aria-live="polite" aria-atomic="true">
        {classificationState === 'loading' && <p role="status">Loading saved classification…</p>}
        {classifying && <p role="status">Classifying this saved extraction. Please wait.</p>}
        {classificationState === 'none' && <p>No saved classification for this extraction. Results for older runs are not applied.</p>}
        {notice && <p className="workspace-notice">{notice}</p>}
      </div>
      {error && <p className="workspace-error" role="alert">{error.message}{error.kind === 'model_unavailable' && ' Existing saved predictions remain readable.'}</p>}
      {mappingError && <p className="workspace-error" role="alert">{mappingError}</p>}
      {classification && !mappingError && <ClassificationMetadata result={classification} />}
      {!extraction.candidates.length ? <p role="status">This saved extraction contains no requirements.{classification ? ' Its saved classification has no predictions.' : ''}</p>
        : <ul className="requirement-list">{extraction.candidates.map((candidate) => <li key={candidate.requirement_id}>
          <div className="requirement-identity"><code>{candidate.requirement_id}</code>
            {labels.has(candidate.requirement_id) ? <span className={`requirement-badge ${labels.get(candidate.requirement_id).toLowerCase()}`} title={labels.get(candidate.requirement_id) === 'FR' ? 'Functional requirement prediction' : 'Non-functional requirement prediction'}>{labels.get(candidate.requirement_id)}</span>
              : <span className="requirement-badge pending">Unclassified</span>}
          </div><p>{candidate.requirement_text}</p><small>Candidate for review · Classification does not approve this requirement.</small>
        </li>)}</ul>}
      <p className="workspace-note">FR = functional requirement; NFR = non-functional requirement. Labels are baseline predictions for review, without individual confidence scores.</p>
    </>}
  </article>
}

export default function ProjectWorkspace() {
  const initialId = new URLSearchParams(window.location.search).get('project') ?? ''
  const [selectedId, setSelectedId] = useState(/^[a-f0-9]{24}$/i.test(initialId) ? initialId.toLowerCase() : '')
  const [enteredId, setEnteredId] = useState(initialId)
  const [inputError, setInputError] = useState('')
  const [busy, setBusy] = useState(false)
  const [page, setPage] = useState({ offset: 0, revision: 0 })
  const [listing, setListing] = useState({ phase: 'loading', items: [], hasMore: false, error: null })
  const listingBusy = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    listingBusy.current = true
    listProjects({ offset: page.offset, signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setListing((current) => ({ phase: 'ready', items: page.offset ? [...current.items, ...data.items.filter((p) => !current.items.some((existing) => existing.id === p.id))] : data.items, hasMore: data.has_more, error: null }))
    }).catch((error) => {
      if (!controller.signal.aborted) setListing((current) => ({ ...current, phase: 'error', error }))
    }).finally(() => { if (!controller.signal.aborted) listingBusy.current = false })
    return () => controller.abort()
  }, [page])

  function select(id) {
    if (busy) return
    setInputError('')
    setSelectedId(id)
    setEnteredId(id)
    const url = new URL(window.location.href)
    url.searchParams.set('project', id)
    window.history.replaceState(null, '', url)
  }

  function loadPage(offset) {
    if (busy || listingBusy.current) return
    listingBusy.current = true
    setListing((current) => ({ ...current, phase: 'loading', error: null }))
    setPage((current) => ({ offset, revision: current.revision + 1 }))
  }

  return <section className="project-workspace" aria-labelledby="projects-title">
    <div className="section-heading"><div><p className="eyebrow section-eyebrow">SAVED PROJECTS</p><h2 id="projects-title">Requirement classification</h2></div><p>Review the trained FR/NFR baseline’s predictions.</p></div>
    <form className="open-project" onSubmit={(event) => {
      event.preventDefault()
      if (busy) return
      if (!/^[a-f0-9]{24}$/i.test(enteredId.trim())) { setInputError('Enter a valid 24-character project ID.'); return }
      select(enteredId.trim().toLowerCase())
    }}><label htmlFor="project-id">Open saved project by ID</label><div><input id="project-id" value={enteredId} onChange={(event) => setEnteredId(event.target.value)} disabled={busy} aria-describedby={inputError ? 'project-input-error' : undefined} /><button className="workspace-button" disabled={busy}>Open project</button></div>
      {inputError && <p id="project-input-error" role="alert">{inputError}</p>}</form>
    <div className="workspace-layout"><aside aria-label="Saved projects">
      <button className="workspace-button" disabled={busy || listing.phase === 'loading'} onClick={() => loadPage(0)}>Refresh projects</button>
      {listing.phase === 'loading' && <p role="status">Loading projects…</p>}
      {listing.error && <p role="alert">{listing.error.message}</p>}
      {listing.phase === 'ready' && !listing.items.length && <p>No saved projects yet.</p>}
      <ul className="project-list">{listing.items.map((project) => <li key={project.id}><button type="button" disabled={busy} aria-current={selectedId === project.id ? 'true' : undefined} onClick={() => select(project.id)}>{project.name}<small>{project.id}</small></button></li>)}</ul>
      {listing.hasMore && <button className="workspace-button" disabled={busy || listing.phase === 'loading'} onClick={() => loadPage(page.offset + 20)}>Load more projects</button>}
    </aside>{selectedId ? <SavedProject key={selectedId} projectId={selectedId} onBusyChange={setBusy} /> : <p className="project-detail">Select a saved project to load its latest extraction and classification.</p>}</div>
  </section>
}
