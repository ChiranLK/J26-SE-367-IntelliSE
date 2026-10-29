import { useEffect, useRef, useState } from 'react'
import { checkProjectProvenanceContract, createProject } from '../services/api.js'
import { characterCount, PROJECT_LIMITS, validateProjectInput } from '../services/contracts.js'
import AudioTranscription from './AudioTranscription.jsx'

export default function CreateProjectForm({ onSaved }) {
  const [input, setInput] = useState({ name: '', description: '', discussion_text: '' })
  const [errors, setErrors] = useState({})
  const [reviewed, setReviewed] = useState(false)
  const [failure, setFailure] = useState(null)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState('paste')
  const [provenance, setProvenance] = useState(null)
  const [replacement, setReplacement] = useState(null)
  const [clearing, setClearing] = useState(false)
  const [contract, setContract] = useState({ phase: 'loading', error: '' })
  const [contractRevision, setContractRevision] = useState(0)
  const pending = useRef(null)
  const form = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    checkProjectProvenanceContract({ signal: controller.signal })
      .then((supported) => { if (!controller.signal.aborted) setContract({ phase: supported ? 'supported' : 'unavailable', error: '' }) })
      .catch((error) => { if (!controller.signal.aborted) setContract({ phase: 'unavailable', error: error.message }) })
    return () => controller.abort()
  }, [contractRevision])
  const audioSaveBlocked = Boolean(provenance) && contract.phase !== 'supported'

  async function submit(event) {
    event.preventDefault()
    if (pending.current || audioSaveBlocked) return
    const invalid = validateProjectInput(input)
    if (!Object.keys(invalid).length && !reviewed) invalid.source_review = 'Review the discussion and confirm it before saving.'
    setErrors(invalid)
    if (Object.keys(invalid).length) {
      form.current.elements.namedItem(Object.keys(invalid)[0])?.focus()
      return
    }
    const controller = new AbortController()
    pending.current = controller
    setSaving(true)
    setFailure(null)
    try {
      const project = await createProject({ ...input, description: input.description === '' ? null : input.description,
        ...(provenance ? { transcription_id: provenance.transcription_id } : {}),
      }, { signal: controller.signal })
      if (!controller.signal.aborted) onSaved(project)
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailure(error)
        if (error.code === 'provenance-unavailable') setContract({ phase: 'unavailable', error: error.message })
      }
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setSaving(false) }
    }
  }

  function applyTranscript(job, text) {
    setInput((previous) => ({ ...previous, discussion_text: text }))
    setReviewed(false)
    setProvenance(job)
    setReplacement(null)
    setTab('paste')
  }

  function useTranscript(job, text) {
    if (input.discussion_text.length) setReplacement({ job, text })
    else applyTranscript(job, text)
  }

  function field(name, label, multiline, rows) {
    const props = {
      id: name, name, value: input[name], required: name !== 'description', disabled: saving,
      onChange: (event) => { setInput({ ...input, [name]: event.target.value }); if (name === 'discussion_text') setReviewed(false) },
      'aria-invalid': Boolean(errors[name]), 'aria-describedby': `${name}-help ${errors[name] ? `${name}-error` : ''}`.trim(),
    }
    return <div className="form-field">
      <label htmlFor={name}>{label}</label>
      {multiline ? <textarea {...props} rows={rows} /> : <input {...props} type="text" autoComplete="off" />}
      <p id={`${name}-help`} className="field-help">{characterCount(input[name]).toLocaleString()} / {PROJECT_LIMITS[name].toLocaleString()} characters{name === 'discussion_text' ? ' · Saved as submitted; never rewritten.' : ''}</p>
      {errors[name] && <p className="field-error" id={`${name}-error`}>{errors[name]}</p>}
    </div>
  }

  return <section className="panel" aria-labelledby="create-heading">
    <p className="eyebrow section-eyebrow">STEP 1 · CREATE & REVIEW SOURCE</p>
    <h2 id="create-heading">Create a project</h2>
    <p className="panel-description">Add a title and description, then paste a discussion or upload an audio recording. Read and edit the text before continuing.</p>
    <form ref={form} onSubmit={submit} noValidate aria-busy={saving}>
      {field('name', 'Project name', false)}
      {field('description', 'Description (optional)', true, 3)}
      <div className="discussion-tabs" data-active={tab} role="tablist" aria-label="Discussion source" onKeyDown={(event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        const next = event.key === 'Home' ? 'paste' : event.key === 'End' ? 'audio' : tab === 'paste' ? 'audio' : 'paste'
        setTab(next)
        document.getElementById(`source-${next}-tab`).focus()
      }}>
        {['paste', 'audio'].map((value) => <button key={value} id={`source-${value}-tab`} role="tab" type="button" disabled={saving}
          aria-selected={tab === value} aria-controls={`source-${value}-panel`} tabIndex={tab === value ? 0 : -1}
          onClick={() => setTab(value)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{value === 'paste' ? <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8M8 17h5" /></> : <><path d="M9 18V5l11-2v13M9 8l11-2" /><ellipse cx="6" cy="18" rx="3" ry="3" /><ellipse cx="17" cy="16" rx="3" ry="3" /></>}</svg>{value === 'paste' ? 'Paste text' : 'Upload audio'}</button>)}
      </div>
      <div id="source-paste-panel" className="source-tab-panel source-text-panel" role="tabpanel" aria-labelledby="source-paste-tab" hidden={tab !== 'paste'}>
        <p className="field-help">Paste or edit the discussion below. Audio never replaces this text without your explicit action.</p>
      </div>
      <div id="source-audio-panel" className="source-tab-panel" role="tabpanel" aria-labelledby="source-audio-tab" hidden={tab !== 'audio'}>
        <AudioTranscription disabled={saving} onUse={useTranscript} provenanceAvailable={contract.phase === 'supported'} />
      </div>
      {replacement && <div role="alertdialog" aria-modal="false" aria-labelledby="replace-discussion-heading" className="workspace-notice">
        <h3 id="replace-discussion-heading">Replace the existing discussion?</h3>
        <p>Your project name and description will stay unchanged. The reviewed transcript will replace all current discussion text.</p>
        <div className="action-row">
          <button type="button" className="workspace-button" onClick={() => applyTranscript(replacement.job, replacement.text)}>Replace discussion</button>
          <button type="button" className="workspace-button" onClick={() => setReplacement(null)}>Keep current discussion</button>
        </div>
      </div>}
      <div className="source-review-heading"><span className="step-mini">REVIEW YOUR SOURCE</span><p>Check names, numbers, permissions and missing words. This text becomes your saved discussion.</p></div>
      {field('discussion_text', 'Original client discussion', true, 9)}
      <label className="source-review-check"><input type="checkbox" name="source_review" checked={reviewed} disabled={saving} onChange={(event) => setReviewed(event.target.checked)} />I have reviewed this discussion and am ready to continue.</label>
      {errors.source_review && <p className="field-error" role="alert">{errors.source_review}</p>}
      {provenance && <div className={`workspace-notice audio-source-link ${audioSaveBlocked ? '' : 'ready'}`} role="status">
        {audioSaveBlocked ? <>
          <p><strong>Audio-derived project saving is unavailable.</strong> {contract.phase === 'loading' ? 'Checking the backend provenance contract.' : 'The configured backend does not currently provide the required provenance contract.'} Your discussion and source reference are retained; saving is blocked.</p>
          {contract.error && <p className="field-help">{contract.error}</p>}
          <button type="button" className="workspace-button" disabled={contract.phase === 'loading'} onClick={() => { setContract({ phase: 'loading', error: '' }); setContractRevision((value) => value + 1) }}>Check audio saving support</button>
        </> : <p><strong>Audio transcript linked.</strong> When you save this project, your edited discussion and the original transcript will be kept together.</p>}
        <details className="audio-source-details"><summary>Recording details</summary><p className="record-id">Transcription: <code>{provenance.transcription_id}</code> · {provenance.model} · {provenance.language}</p></details>
        <details className="audio-original"><summary>View original transcript (before your edits)</summary><pre>{provenance.original_transcript}</pre></details>
        <p className="field-help">You can keep editing your discussion. The original transcript stays unchanged.</p>
        <button type="button" className="workspace-button" disabled={saving} onClick={() => setClearing(true)}>Clear audio-derived discussion</button>
        {clearing && <div role="alertdialog" aria-modal="false" aria-label="Clear audio discussion confirmation">
          <p>Clear the discussion and its pending source association? The saved transcription job remains in the backend. Project name and description stay unchanged.</p>
          <button type="button" className="workspace-button" onClick={() => { setInput((previous) => ({ ...previous, discussion_text: '' })); setReviewed(false); setProvenance(null); setClearing(false) }}>Clear discussion and association</button>
          <button type="button" className="workspace-button" onClick={() => setClearing(false)}>Keep audio discussion</button>
        </div>}
      </div>}
      <p className="field-help">Project saving supports 100,000 characters. The backend's extraction limit defaults to 30,000 and may be configured differently.</p>
      {failure && <div className="error-message" role="alert"><p>{failure.message}</p>{failure.uncertain && <p>Saving may have completed. Refresh the project list before submitting again to avoid creating a duplicate.</p>}</div>}
      <button className="primary-button" type="submit" disabled={saving || audioSaveBlocked}>{saving ? 'Saving project…' : 'Save and open project'}</button>
      <p className="sr-only" role="status">{saving ? 'Saving project. Please wait.' : ''}</p>
    </form>
  </section>
}
