import { useEffect, useRef, useState } from 'react'
import { extractRequirements, getLatestExtraction, getProject, isNoExtraction } from '../services/api.js'
import { formatDate } from '../services/format.js'
import { openNewProject, pendingExtraction } from '../services/navigation.js'
import ExtractionResults from './ExtractionResults.jsx'
import ProjectSource from './ProjectSource.jsx'
import { classifyExtraction } from '../services/projectApi.js'

export default function ProjectDetail({ projectId, onExtractionSaved, activeStep = 2 }) {
  const [project, setProject] = useState(null)
  const [projectError, setProjectError] = useState('')
  const [revision, setRevision] = useState(0)
  const [run, setRun] = useState(null)
  const [latest, setLatest] = useState({ phase: 'loading', error: '' })
  const [processing, setProcessing] = useState(false)
  const [extractionError, setExtractionError] = useState('')
  const [needsCheck, setNeedsCheck] = useState(() => pendingExtraction(projectId))
  const extractionRequest = useRef(null)
  const latestRequest = useRef(null)
  const heading = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      let saved
      try {
        saved = await getProject(projectId, { signal: controller.signal })
        if (controller.signal.aborted) return
        setProject(saved)
      } catch (error) {
        if (!controller.signal.aborted) setProjectError(error.status === 404 ? 'Project not found. Check the link or open another saved project.' : error.message)
        return
      }
      try {
        const result = await getLatestExtraction(saved.id, saved.discussion_text, { signal: controller.signal })
        if (!controller.signal.aborted) { setRun(result); setLatest({ phase: 'ready', error: '' }) }
      } catch (error) {
        if (!controller.signal.aborted) {
          setLatest(isNoExtraction(error) ? { phase: 'none', error: '' } : { phase: 'error', error: error.message })
        }
      }
    }
    void load()
    return () => controller.abort()
  }, [projectId, revision])

  useEffect(() => { if (project) heading.current?.focus() }, [project])
  useEffect(() => () => { extractionRequest.current?.abort(); latestRequest.current?.abort() }, [])

  async function retrieveLatest() {
    if (!project || latestRequest.current || extractionRequest.current) return
    const controller = new AbortController()
    latestRequest.current = controller
    setLatest({ phase: 'loading', error: '' })
    try {
      const saved = await getLatestExtraction(project.id, project.discussion_text, { signal: controller.signal })
      if (!controller.signal.aborted) {
        setRun(saved)
        onExtractionSaved?.()
        setLatest({ phase: 'ready', error: '' })
        setNeedsCheck(false)
        pendingExtraction(projectId, false)
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        if (isNoExtraction(error)) {
          setRun(null)
          onExtractionSaved?.()
          setLatest({ phase: 'none', error: '' })
          setNeedsCheck(false)
          pendingExtraction(projectId, false)
        } else setLatest({ phase: 'error', error: error.message })
      }
    } finally { if (!controller.signal.aborted) latestRequest.current = null }
  }

  async function extract(withClassification = false) {
    if (!project || extractionRequest.current || latestRequest.current || needsCheck || latest.phase === 'loading' || latest.phase === 'error') return
    const controller = new AbortController()
    extractionRequest.current = controller
    pendingExtraction(projectId, true)
    setProcessing(true)
    setExtractionError('')
    try {
      const saved = await extractRequirements(project.id, project.discussion_text, { signal: controller.signal })
      if (!controller.signal.aborted) {
        setRun(saved)
        onExtractionSaved?.()
        setLatest({ phase: 'ready', error: '' })
        pendingExtraction(projectId, false)
        if (withClassification) {
          try {
            await classifyExtraction(projectId, saved, { signal: controller.signal })
            if (!controller.signal.aborted) onExtractionSaved?.()
          } catch (error) {
            if (!controller.signal.aborted) setExtractionError(`Requirements were saved, but classification failed. ${error.message} Use the classification panel to retrieve results or retry explicitly.`)
          }
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setExtractionError(error.message)
        setNeedsCheck(error.uncertain)
        pendingExtraction(projectId, error.uncertain)
      }
    } finally {
      if (!controller.signal.aborted) { extractionRequest.current = null; setProcessing(false) }
    }
  }

  if (projectError) return <section className="panel" aria-labelledby="project-error-heading">
    <h2 id="project-error-heading">Could not open project</h2><p className="error-message" role="alert">{projectError}</p>
    <div className="action-row"><button type="button" className="secondary-button" onClick={() => { setProjectError(''); setRevision(revision + 1) }}>Retry project</button><button type="button" className="text-button" onClick={openNewProject}>Create a project</button></div>
  </section>
  if (!project) return <section className="panel"><p className="state-message" role="status">Loading project discussion…</p></section>
  return <article className="project-detail">
    <section className="panel" aria-labelledby="project-heading" hidden={activeStep !== 1}>
      <p className="eyebrow section-eyebrow">STEP 1 · SAVED SOURCE</p>
      <h2 id="project-heading" ref={heading} tabIndex={-1}>{project.name}</h2>
      <div className="project-meta"><span className="draft-tag">{project.status}</span><span>Created <time dateTime={project.created_at}>{formatDate(project.created_at)}</time></span></div>
      {project.description !== null && <p className="project-description">{project.description}</p>}
      <details className="discussion" open><summary>{project.transcription_provenance ? 'Reviewed client discussion' : 'Original client discussion'}</summary><pre tabIndex={0} aria-label={project.transcription_provenance ? 'Saved reviewed discussion' : 'Saved original discussion'}>{project.discussion_text}</pre></details>
      {project.transcription_provenance && <ProjectSource source={project.transcription_provenance} />}
    </section>
    <section hidden={activeStep !== 2} className="panel extraction-panel" aria-labelledby="extraction-heading" aria-busy={processing}>
      <p className="eyebrow section-eyebrow">STEP 2 · EXTRACT & CLASSIFY</p>
      <h2 id="extraction-heading">Classify & review requirements</h2>
      <p className="panel-description">Find individual requirements in your saved discussion and classify them as Functional (FR) or Non-functional (NFR). Then review the labels below. Each run is saved separately.</p>
      <div className="action-row">
        <button type="button" className="primary-button" disabled={processing || needsCheck || latest.phase === 'loading' || latest.phase === 'error'} onClick={() => { void extract(true) }}>{processing ? 'Processing requirements…' : 'Run extraction & classification'}</button>
      </div>
      <details className="advanced-actions" open={needsCheck || undefined}><summary>Extraction controls & recovery</summary><div className="action-row">
        <button type="button" className="secondary-button" onClick={() => { void extract() }} disabled={processing || needsCheck || latest.phase === 'loading' || latest.phase === 'error'}>{processing ? 'Extracting requirements…' : 'Extract requirements'}</button>
        <button type="button" className="secondary-button" onClick={retrieveLatest} disabled={processing || latest.phase === 'loading'}>{latest.phase === 'loading' ? 'Retrieving latest…' : 'Retrieve latest saved result'}</button>
      </div>
      </details>
      <div role="status" aria-live="polite">{processing && <p className="processing-message">Extraction is running. This can take a few minutes. Previous saved results remain below.</p>}{latest.phase === 'loading' && <p className="state-message">Loading the latest saved extraction…</p>}</div>
      {extractionError && <p className="error-message" role="alert">{extractionError} {run ? 'The previous saved result is still displayed.' : ''}</p>}
      {needsCheck && <p className="recovery-message" role="alert">A previous extraction may still be running or may have been saved. Retrieve the latest saved result before requesting another extraction. Retrieval does not cancel an earlier run; if it has not finished, check again later.</p>}
      {latest.phase === 'error' && <p className="error-message" role="alert">Could not retrieve the latest extraction. {latest.error} Use “Retrieve latest saved result” to retry.</p>}
      {latest.phase === 'none' && <p className="state-message">No extraction yet. Use “Run extraction & classification” above to get started.</p>}
      {run && <details className="extraction-evidence"><summary>{run.candidates.length} requirement {run.candidates.length === 1 ? "candidate" : "candidates"} · View extraction evidence</summary><ExtractionResults run={run} /></details>}
    </section>
  </article>
}
