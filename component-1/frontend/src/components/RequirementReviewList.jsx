import { Fragment, useEffect, useId, useRef, useState } from 'react'
import { getLabelReviews, saveLabelReview } from '../services/reviewApi.js'
import RequirementExport from './RequirementExport.jsx'
import AmbiguityHints from './AmbiguityHints.jsx'
import ReviewLabelSelect from './ReviewLabelSelect.jsx'

function ReviewEditor({ candidate, saved, reviewer, projectId, extraction, classification, onSaved, disabled, onDirty, displayId, reviewerInput, prediction }) {
  const [reviewedLabel, setReviewedLabel] = useState(saved?.reviewed_label ?? '')
  const [note, setNote] = useState(saved?.note ?? '')
  const [state, setState] = useState({ busy: false, error: '', uncertain: false })
  const pending = useRef(null)
  const controller = useRef(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function save(event) {
    event.preventDefault()
    if (controller.current || disabled) return
    if (!pending.current && !reviewer.trim()) {
      setState({ busy: false, error: 'Enter your reviewer name or ID above, then save your review.', uncertain: false })
      reviewerInput.current?.focus()
      return
    }
    const submission = pending.current ?? { submission_id: crypto.randomUUID(), reviewed_label: reviewedLabel, reviewer_id: reviewer.trim(), note }
    pending.current = submission
    const active = new AbortController()
    controller.current = active
    setState({ busy: true, error: '', uncertain: false })
    try {
      const review = await saveLabelReview(projectId, extraction, classification, candidate.requirement_id, submission, { signal: active.signal })
      if (!active.signal.aborted) onSaved(review)
    } catch (error) {
      if (!active.signal.aborted) {
        if (!error.uncertain) pending.current = null
        setState({ busy: false, error: error.message, uncertain: !!error.uncertain })
      }
    } finally { if (controller.current === active) controller.current = null }
  }

  function change(nextLabel, nextNote) {
    setReviewedLabel(nextLabel)
    setNote(nextNote)
    onDirty(nextLabel !== (saved?.reviewed_label ?? '') || nextNote !== (saved?.note ?? ''))
  }
  const dirty = reviewedLabel !== (saved?.reviewed_label ?? '') || note !== (saved?.note ?? '')
  const locked = disabled || state.busy || state.uncertain
  return <div className="label-review">
    {saved && <details className="saved-review-details"><summary>Reviewed label: <strong>{saved.reviewed_label}</strong></summary><p className="saved-label-review" role="status">{saved.reviewer_id} · <time dateTime={saved.reviewed_at}>{new Date(saved.reviewed_at).toLocaleString()}</time></p>{saved.note && <p className="review-note">Saved note: {saved.note}</p>}</details>}
    <form onSubmit={(event) => { void save(event) }}>
      <ReviewLabelSelect key={locked ? 'locked' : 'active'} value={reviewedLabel} onChange={(value) => change(value, note)} disabled={locked} displayId={displayId} placeholder={`Use model label (${prediction})`} />
      <details className="review-note-editor"><summary>Review note (optional)</summary><label><span className="sr-only">Review note</span><textarea aria-label={`Review note for ${displayId}`} value={note} maxLength={2000} onChange={(event) => change(reviewedLabel, event.target.value)} disabled={locked} rows={2} /></label></details>
      <button className="workspace-button review-save-button" disabled={disabled || state.busy || (!state.uncertain && (!reviewedLabel || (saved && !dirty)))}>{state.busy ? 'Saving review…' : state.uncertain ? 'Retry same review' : saved && !dirty ? '✓ Saved' : 'Save review'}</button>
    </form>
    {!saved && !dirty && <p className="model-label-default">Using model label · change only if needed</p>}
    {state.error && <p role="alert">{state.error}{state.uncertain && ' Saving may have succeeded. Retry the same review safely, or refresh saved results before editing.'}</p>}
  </div>
}

export default function RequirementReviewList({ projectId, extraction, classification, labels, disabled, project, activeStep = 2, reviewerName, onReviewerChange, reviewerError = '', reviewerInputRef }) {
  const [reviews, setReviews] = useState(new Map())
  const [expanded, setExpanded] = useState(new Set())
  const detailsPrefix = useId()
  const [dirty, setDirty] = useState(new Set())
  const [localReviewer, setLocalReviewer] = useState('')
  const localReviewerInput = useRef(null)
  const reviewer = reviewerName ?? localReviewer
  const reviewerInput = reviewerInputRef ?? localReviewerInput
  const setReviewer = (value) => { setLocalReviewer(value); onReviewerChange?.(value) }
  const reviewerErrorId = `${detailsPrefix}-reviewer-error`
  const [loading, setLoading] = useState(!!classification)
  const [error, setError] = useState(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    if (!classification) return
    const controller = new AbortController()
    getLabelReviews(projectId, extraction, classification, { signal: controller.signal }).then((page) => {
      if (!controller.signal.aborted) { setReviews(new Map(page.reviews.map((item) => [item.requirement_id, item]))); setLoading(false) }
    }).catch((problem) => { if (!controller.signal.aborted) { setError(problem); setLoading(false) } })
    return () => controller.abort()
  }, [projectId, extraction, classification, revision])

  function retry() { setError(null); setLoading(true); setRevision((value) => value + 1) }
  function markDirty(id, changed) {
    setDirty((current) => { const next = new Set(current); if (changed) next.add(id); else next.delete(id); return next })
  }
  return <>
    <div hidden={activeStep !== 2}>
    {classification && <div className="label-review-intro">
      <p>Model labels are used automatically. Change FR/NFR only when needed and save your correction. Original predictions are preserved.</p>
      <label>Reviewer name or ID (required before export, self-reported)<input ref={reviewerInput} aria-required="true" placeholder="Enter your reviewer name or ID" aria-invalid={!!reviewerError && !reviewer.trim()} aria-describedby={reviewerError ? reviewerErrorId : undefined} value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={120} aria-label="Reviewer name or ID" disabled={disabled} /></label>
      {reviewerError && !reviewer.trim() && <p id={reviewerErrorId} className="field-error" role="alert">{reviewerError}</p>}
      {loading && <p role="status">Loading saved label reviews…</p>}
      {error && <div role="alert"><p>Label reviews unavailable. {error.status === 404 ? 'Restart the backend with label-review routes enabled.' : error.message}</p><button className="workspace-button" onClick={retry}>Retry loading reviews</button></div>}
      {!loading && !error && !reviews.size && <p>No saved label reviews for this classification.</p>}
    </div>}
    <div className="requirement-table-scroll" role="region" aria-label="Requirement review table" tabIndex={0}>
      <table className="requirement-review-table">
        <caption className="sr-only">Requirement text, original model prediction, and saved human label reviews. Expand Details for source evidence and unclear points.</caption>
        <colgroup><col className="review-col-id" /><col className="review-col-text" /><col className="review-col-model" /><col className="review-col-human" /><col className="review-col-details" /></colgroup>
        <thead><tr><th scope="col">ID</th><th scope="col">Requirement</th><th scope="col">Model prediction</th><th scope="col">Human review</th><th scope="col">Details</th></tr></thead>
        <tbody>{extraction.candidates.map((candidate, index) => {
          const displayId = `R${String(index + 1).padStart(2, '0')}`
          const detailId = `${detailsPrefix}-${index}`
          const isOpen = expanded.has(candidate.requirement_id)
          return <Fragment key={candidate.requirement_id}>
            <tr className="requirement-table-row">
              <th scope="row"><span className="requirement-number">{displayId}</span></th>
              <td><p className="compact-requirement-text">{candidate.requirement_text}</p></td>
              <td>{labels.has(candidate.requirement_id) ? <span className={`requirement-badge ${labels.get(candidate.requirement_id).toLowerCase()}`} title={labels.get(candidate.requirement_id) === 'FR' ? 'Functional requirement prediction' : 'Non-functional requirement prediction'}>{labels.get(candidate.requirement_id)}</span> : <span className="requirement-badge pending">Unclassified</span>}</td>
              <td>{classification ? <ReviewEditor key={reviews.get(candidate.requirement_id)?.review_id ?? 'new'} {...{ candidate, reviewer, projectId, extraction, classification, displayId, reviewerInput }} prediction={labels.get(candidate.requirement_id)} saved={reviews.get(candidate.requirement_id)} disabled={disabled || loading || !!error}
                onDirty={(changed) => markDirty(candidate.requirement_id, changed)}
                onSaved={(review) => { markDirty(candidate.requirement_id, false); setReviews((previous) => new Map(previous).set(review.requirement_id, review)) }} /> : <span className="workspace-note">Classify to review</span>}</td>
              <td><button type="button" className="row-details-toggle" aria-label={`${isOpen ? 'Hide' : 'View'} details for ${displayId}`} aria-expanded={isOpen} aria-controls={detailId}
                onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(candidate.requirement_id)) next.delete(candidate.requirement_id); else next.add(candidate.requirement_id); return next })}>{isOpen ? 'Hide details' : 'View details'}</button></td>
            </tr>
            <tr className="requirement-table-details" id={detailId} hidden={!isOpen}><td colSpan={5}>
              <div className="requirement-identity"><details className="requirement-record"><summary>Evidence & record details for {displayId}</summary><p>Requirement ID: <code>{candidate.requirement_id}</code></p>
                {candidate.evidence?.map((span, spanIndex) => <blockquote key={spanIndex}>{span.quote}<small>Source characters {span.start}–{span.end}</small></blockquote>)}
              </details></div>
              <AmbiguityHints text={candidate.requirement_text} />
            </td></tr>
          </Fragment>
        })}</tbody>
      </table>
    </div>
    <p className="workspace-note">FR = functional requirement; NFR = non-functional requirement. Saving a label review does not approve the requirement.</p>
    </div>
    {activeStep === 3 && classification && project && <RequirementExport {...{ project, extraction, classification, reviews, loading, error }} dirtyCount={dirty.size} />}
  </>
}
