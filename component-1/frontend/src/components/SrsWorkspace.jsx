import { useEffect, useRef, useState } from 'react'
import { getLatestClassification, getLatestExtraction } from '../services/projectApi.js'
import ReviewLabelSelect from './ReviewLabelSelect.jsx'
import { downloadSrs, getSrs, saveSrsAction } from '../services/srsApi.js'

const decisionChoices = [
  { value: 'accepted', title: 'Accept requirement', badge: '✓', description: 'Keep this requirement as written' },
  { value: 'request_changes', title: 'Request changes', badge: '↺', description: 'Explain what needs to change' },
  { value: 'needs_clarification', title: 'Needs clarification', badge: '?', description: 'Ask a question before accepting' },
]

function FeedbackEditor({ item, saved, disabled, saving, onSave, displayId }) {
  const [decision, setDecision] = useState(saved?.decision ?? 'accepted')
  const [comment, setComment] = useState(saved?.comment ?? '')
  const unchanged = !!saved && decision === saved.decision && comment === saved.comment
  const commentField = <label>{decision === 'accepted' ? 'Comment (optional)' : 'Explain the change or question'}<textarea value={comment} maxLength={2000} required={decision !== 'accepted'} rows={2} disabled={disabled} onChange={(event) => setComment(event.target.value)} /></label>
  return <form className="srs-feedback" onSubmit={(event) => { event.preventDefault(); if (!unchanged) onSave({ requirement_id: item.requirement_id, decision, comment }) }}>
    <span className="srs-field-label">Client decision</span>
    <div className="srs-decision-actions">
      <ReviewLabelSelect value={decision} onChange={setDecision} disabled={disabled} options={decisionChoices}
        ariaLabel={`Client decision for ${displayId}`} menuLabel={`Client decision choices for ${displayId}`} className="client-decision-picker" />
      <button className={`workspace-button srs-save-decision ${unchanged ? 'is-saved' : ''}`} disabled={disabled || unchanged}>
        {saving ? 'Saving…' : unchanged ? '✓ Saved' : 'Save client decision'}
      </button>
    </div>
    {decision === 'accepted' ? <details className="srs-comment"><summary>Comment (optional)</summary>{commentField}</details> : commentField}
  </form>
}

function RevisionEditor({ version, disabled, onSave }) {
  const [requirementId, setRequirementId] = useState(version.requirements[0].requirement_id)
  const selected = version.requirements.find((item) => item.requirement_id === requirementId)
  const [text, setText] = useState(selected.text)
  const [label, setLabel] = useState(selected.label)
  const [reason, setReason] = useState('')
  return <details className="srs-revision"><summary>Create a revised draft</summary>
    <p>Edit one requirement to create the next version. All client decisions must be reviewed again. Original source records stay unchanged.</p>
    <form onSubmit={(event) => { event.preventDefault(); onSave({ base_version_id: version.version_id, changes: [{ requirement_id: requirementId, text, label, reason }] }) }}>
      <label>Requirement to revise<select value={requirementId} disabled={disabled} onChange={(event) => { const item = version.requirements.find((item) => item.requirement_id === event.target.value); setRequirementId(item.requirement_id); setText(item.text); setLabel(item.label) }}>
        {version.requirements.map((item, index) => <option key={item.requirement_id} value={item.requirement_id}>R{String(index + 1).padStart(2, '0')} · {item.text.slice(0, 70)}</option>)}
      </select></label>
      <label>Revised requirement<textarea value={text} onChange={(event) => setText(event.target.value)} required maxLength={2000} rows={3} disabled={disabled} /></label>
      <label>Requirement type<select value={label} onChange={(event) => setLabel(event.target.value)} disabled={disabled}><option value="FR">FR — Functional</option><option value="NFR">NFR — Non-functional</option></select></label>
      <label>Reason for change<textarea value={reason} onChange={(event) => setReason(event.target.value)} required maxLength={2000} rows={2} disabled={disabled} /></label>
      <button className="primary-button" disabled={disabled}>Save new SRS version</button>
    </form>
  </details>
}

export default function SrsWorkspace({ projectId }) {
  const [record, setRecord] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [bulkConfirmed, setBulkConfirmed] = useState(false)
  const [activeAction, setActiveAction] = useState(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(null)
  const [retryAction, setRetryAction] = useState(null)
  const controller = useRef(null)
  const actorInput = useRef(null)

  useEffect(() => {
    const active = new AbortController()
    controller.current = active
    getSrs(projectId, { signal: active.signal }).then((data) => {
      if (!active.signal.aborted) { setRecord(data); setSelectedId(data.versions.at(-1)?.version_id ?? '') }
    }).catch((problem) => { if (!active.signal.aborted) setError(problem) })
      .finally(() => { if (!active.signal.aborted) { setBusy(false); controller.current = null } })
    return () => { active.abort(); controller.current?.abort() }
  }, [projectId])

  async function refresh() {
    if (controller.current) return
    const active = new AbortController(); controller.current = active; setBusy(true); setError(null)
    try {
      const data = await getSrs(projectId, { signal: active.signal })
      if (!active.signal.aborted) { setRecord(data); setSelectedId(data.versions.at(-1)?.version_id ?? ''); setConfirmed(false); setBulkConfirmed(false) }
    } catch (problem) { if (!active.signal.aborted) setError(problem) }
    finally { if (!active.signal.aborted) { controller.current = null; setBusy(false) } }
  }

  async function perform(operation, fields = {}, replay = null) {
    if (controller.current || !record || (retryAction && !replay)) return
    if (!replay && !reviewer.trim()) { setError(new Error('Enter the reviewer name or ID before saving.')); actorInput.current?.focus(); return }
    const active = new AbortController(); controller.current = active; setBusy(true); setError(null)
    let body = replay?.body
    setActiveAction({ operation, requirement_id: replay?.body?.requirement_id ?? fields.requirement_id })
    try {
      if (!body) {
        body = { submission_id: crypto.randomUUID(), expected_revision: record.revision, reviewer_id: reviewer.trim(), ...fields }
        if (operation === 'draft') {
          const extraction = await getLatestExtraction(projectId, { signal: active.signal })
          if (!extraction) throw new Error('Save an extraction and classify its requirements first.')
          const classification = await getLatestClassification(projectId, extraction, { signal: active.signal })
          if (!classification) throw new Error('Classify the saved extraction first. Label corrections are optional.')
          Object.assign(body, { extraction_run_id: extraction.run_id, classification_id: classification.classification_id })
        }
      }
      const data = await saveSrsAction(projectId, operation, body, { signal: active.signal })
      if (!active.signal.aborted) { setRecord(data); setSelectedId(data.versions.at(-1)?.version_id ?? ''); setConfirmed(false); setBulkConfirmed(false); setRetryAction(null) }
    } catch (problem) {
      if (!active.signal.aborted) {
        setError(problem)
        if (problem.uncertain && body) setRetryAction({ operation, body })
        else if (replay) setRetryAction(null)
      }
    } finally { if (!active.signal.aborted) { controller.current = null; setBusy(false); setActiveAction(null) } }
  }

  const version = record?.versions.find((item) => item.version_id === selectedId)
  const isLatest = version && version.version_id === record.versions.at(-1)?.version_id
  const latestFeedback = new Map(version?.feedback.map((item) => [item.requirement_id, item]) ?? [])
  const accepted = version?.requirements.filter((item) => latestFeedback.get(item.requirement_id)?.decision === 'accepted').length ?? 0
  const pendingCount = version?.requirements.filter((item) => !latestFeedback.has(item.requirement_id)).length ?? 0
  const locked = busy || !!retryAction
  return <section className="panel srs-workspace" aria-labelledby="srs-heading" aria-busy={busy}>
    <p className="eyebrow">STEP 4 · SRS & CLIENT REVIEW</p><h2 id="srs-heading">Draft SRS and client decisions</h2>
    <p>Build a requirement specification using model labels and any saved corrections. Client acceptance is separate from FR/NFR classification.</p>
    <div className="srs-toolbar"><label>Reviewer name or ID (required, self-reported)<input aria-label="SRS reviewer name or ID" ref={actorInput} value={reviewer} maxLength={120} disabled={locked} onChange={(event) => setReviewer(event.target.value)} /></label>
      <button className="workspace-button" disabled={busy} onClick={() => { void refresh() }}>Refresh saved SRS</button></div>
    {busy && <p role="status">Loading or saving SRS…</p>}
    {error && <p className="error-message" role="alert">{error.status === 404 ? 'SRS routes are unavailable. Restart the updated backend.' : error.message}</p>}
    {retryAction && <div className="workspace-notice" role="alert"><p>The action may have been saved. Other changes are blocked. Refresh to inspect saved data, then retry the same submission safely.</p><button className="workspace-button" disabled={busy} onClick={() => { void perform(retryAction.operation, {}, retryAction) }}>Retry same SRS action</button></div>}
    {record && !version && <><p>No saved SRS yet. Generate a draft using model labels; saved corrections take priority. You do not need to review every label.</p><button className="primary-button" disabled={locked} onClick={() => { void perform('draft') }}>Generate draft SRS</button></>}
    {version && <>
      <label className="srs-version-select">Saved version<select value={selectedId} disabled={locked} onChange={(event) => { setSelectedId(event.target.value); setConfirmed(false) }}>
        {record.versions.map((item) => <option key={item.version_id} value={item.version_id}>Version {item.version_number} · {item.status}</option>)}
      </select></label>
      {!isLatest && <p className="workspace-notice">Historical version — read only. Its decisions apply only to this version.</p>}
      <h3>{version.project_title} · SRS v{version.version_number}</h3><p>{version.project_description}</p>
      <p className="srs-status">{version.status === 'approved' ? 'Approved version' : 'Draft — awaiting client approval'} · {accepted}/{version.requirements.length} requirements accepted</p>
      <p className="workspace-note">Template draft from extraction {version.extraction_run_id}. Later extraction or label changes do not update this snapshot automatically.</p>
      {isLatest && version.status === 'draft' && <div className="srs-bulk-review">
        <div><strong>Review by exception</strong><p>Change individual decisions where needed, then accept the remaining pending requirements together. Existing change and clarification requests stay unresolved.</p></div>
        {pendingCount > 0 ? <><label className="srs-bulk-confirm"><input type="checkbox" checked={bulkConfirmed} disabled={locked} onChange={(event) => setBulkConfirmed(event.target.checked)} />I accept the {pendingCount} remaining pending requirements in this version.</label>
          <button className="primary-button" disabled={locked || !bulkConfirmed} onClick={() => { void perform('accept-remaining', { version_id: version.version_id, confirm: true }) }}>{activeAction?.operation === 'accept-remaining' ? 'Saving decisions…' : `Accept ${pendingCount} remaining requirements`}</button></>
          : <p className="srs-bulk-done">✓ All requirements have a saved decision.</p>}
      </div>}
      {version.requirements.map((item, index) => {
        const saved = latestFeedback.get(item.requirement_id)
        return <article className="srs-requirement" key={item.requirement_id}>
          <h4>R{String(index + 1).padStart(2, '0')} <span className={`requirement-badge ${item.label.toLowerCase()}`}>{item.label}</span></h4><p>{item.text}</p>
          {saved ? <p className="srs-decision">Client decision: {saved.decision.replaceAll('_', ' ')} · {saved.reviewer_id}</p> : <p className="workspace-note">Client decision pending</p>}
          {saved?.comment && <blockquote>{saved.comment}</blockquote>}
          {isLatest && version.status === 'draft' && <FeedbackEditor key={saved?.feedback_id ?? 'new'} item={item} saved={saved} disabled={locked} displayId={`R${String(index + 1).padStart(2, '0')}`} saving={busy && activeAction?.operation === 'feedback' && activeAction.requirement_id === item.requirement_id} onSave={(fields) => { void perform('feedback', { version_id: version.version_id, ...fields }) }} />}
          <details><summary>Source and review history</summary><p>Source requirement: {item.requirement_id}</p><p>Original wording: {item.original_text}</p><p>Label source: {item.authored_revision ? 'Authored revision' : item.label_review_id ? 'Saved human label review' : 'Model prediction — no human label review'}</p>
            {item.authored_revision && <p>Authored revision: {item.change_reason}. Revised wording requires client confirmation and is not asserted as an exact source quote.</p>}
            {version.feedback.filter((entry) => entry.requirement_id === item.requirement_id).map((entry) => <p key={entry.feedback_id}>{entry.decision.replaceAll('_', ' ')} · {entry.reviewer_id} · {new Date(entry.recorded_at).toLocaleString()} · {entry.comment}</p>)}
          </details>
        </article>
      })}
      {isLatest && <RevisionEditor key={version.version_id} version={version} disabled={locked} onSave={(fields) => { void perform('revisions', fields) }} />}
      {isLatest && version.status === 'draft' && <div className="srs-approval"><label><input type="checkbox" checked={confirmed} disabled={locked} onChange={(event) => setConfirmed(event.target.checked)} />I approve this exact SRS version after reviewing every requirement.</label>
        <button className="primary-button" disabled={locked || !confirmed || accepted !== version.requirements.length} onClick={() => { void perform('approval', { version_id: version.version_id, confirm: true }) }}>Approve SRS version {version.version_number}</button>
        {accepted !== version.requirements.length && <p className="field-help">Accept every requirement and resolve change/clarification requests before approval.</p>}
      </div>}
      {version.approval && <p className="workspace-notice">Approved by {version.approval.reviewer_id} (self-reported) on {new Date(version.approval.approved_at).toLocaleString()}. This approval applies only to the displayed version.</p>}
      <div className="action-row"><button className="workspace-button" onClick={() => downloadSrs(version, 'json')}>Download SRS JSON</button><button className="workspace-button" onClick={() => downloadSrs(version, 'txt')}>Download SRS text</button></div>
      <details><summary>Version identity</summary><p className="record-id">Content SHA-256: {version.content_hash}</p><p>Method: classified requirements template with optional corrections. No LLM generation or RAG validation was performed.</p></details>
    </>}
    <p className="workspace-note">Client identities are self-reported. This is a requirement-focused SRS draft, not a complete standards-compliant specification. Agile story generation and automatic UML/code/test handoff remain future work.</p>
  </section>
}
