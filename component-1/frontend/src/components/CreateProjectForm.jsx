import { useEffect, useRef, useState } from 'react'
import { createProject } from '../services/api.js'
import { characterCount, PROJECT_LIMITS, validateProjectInput } from '../services/contracts.js'
import AudioTranscription from './AudioTranscription.jsx'

export default function CreateProjectForm({ onSaved }) {
  const [input, setInput] = useState({ name: '', description: '', discussion_text: '' })
  const [errors, setErrors] = useState({})
  const [failure, setFailure] = useState(null)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState('paste')
  const [provenance, setProvenance] = useState(null)
  const [replacement, setReplacement] = useState(null)
  const [clearing, setClearing] = useState(false)
  const pending = useRef(null)
  const form = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])

  async function submit(event) {
    event.preventDefault()
    if (pending.current || provenance) return
    const invalid = validateProjectInput(input)
    setErrors(invalid)
    if (Object.keys(invalid).length) {
      form.current.elements.namedItem(Object.keys(invalid)[0]).focus()
      return
    }
    const controller = new AbortController()
    pending.current = controller
    setSaving(true)
    setFailure(null)
    try {
      const project = await createProject({ ...input, description: input.description === '' ? null : input.description }, { signal: controller.signal })
      if (!controller.signal.aborted) onSaved(project)
    } catch (error) {
      if (!controller.signal.aborted) setFailure(error)
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setSaving(false) }
    }
  }

  function applyTranscript(job, text) {
    setInput((previous) => ({ ...previous, discussion_text: text }))
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
      onChange: (event) => setInput({ ...input, [name]: event.target.value }),
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
    <p className="eyebrow section-eyebrow">01 · CAPTURE THE DISCUSSION</p>
    <h2 id="create-heading">Create a project</h2>
    <p className="panel-description">Start with your client's original words. Save the discussion, then extract candidates for human review.</p>
    <form ref={form} onSubmit={submit} noValidate aria-busy={saving}>
      {field('name', 'Project name', false)}
      {field('description', 'Description (optional)', true, 3)}
      <div className="discussion-tabs" role="tablist" aria-label="Discussion source" onKeyDown={(event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        const next = event.key === 'Home' ? 'paste' : event.key === 'End' ? 'audio' : tab === 'paste' ? 'audio' : 'paste'
        setTab(next)
        document.getElementById(`source-${next}-tab`).focus()
      }}>
        {['paste', 'audio'].map((value) => <button key={value} id={`source-${value}-tab`} role="tab" type="button" disabled={saving}
          aria-selected={tab === value} aria-controls={`source-${value}-panel`} tabIndex={tab === value ? 0 : -1}
          onClick={() => setTab(value)}>{value === 'paste' ? 'Paste text' : 'Upload audio'}</button>)}
      </div>
      <div id="source-paste-panel" role="tabpanel" aria-labelledby="source-paste-tab" hidden={tab !== 'paste'}>
        <p className="field-help">Paste or edit the discussion below. Audio never replaces this text without your explicit action.</p>
      </div>
      <div id="source-audio-panel" role="tabpanel" aria-labelledby="source-audio-tab" hidden={tab !== 'audio'}>
        <AudioTranscription disabled={saving} onUse={useTranscript} />
      </div>
      {replacement && <div role="alertdialog" aria-modal="false" aria-labelledby="replace-discussion-heading" className="workspace-notice">
        <h3 id="replace-discussion-heading">Replace the existing discussion?</h3>
        <p>Your project name and description will stay unchanged. The reviewed transcript will replace all current discussion text.</p>
        <div className="action-row">
          <button type="button" className="workspace-button" onClick={() => applyTranscript(replacement.job, replacement.text)}>Replace discussion</button>
          <button type="button" className="workspace-button" onClick={() => setReplacement(null)}>Keep current discussion</button>
        </div>
      </div>}
      {field('discussion_text', 'Original client discussion', true, 9)}
      {provenance && <div className="workspace-notice" role="status">
        <p><strong>Audio-derived project saving is unavailable.</strong> The current project API cannot retain transcription provenance. Your reviewed discussion is kept here; saving is blocked so the source is not silently discarded.</p>
        <p className="record-id">Source transcription: <code>{provenance.transcription_id}</code> · {provenance.model} · {provenance.language}</p>
        <details className="audio-original"><summary>Applied original ASR transcript (unchanged)</summary><pre>{provenance.original_transcript}</pre></details>
        <p className="field-help">Required backend contract: persist a transcription reference and its review association with the project. Reviewed text is not written back to the transcription job by this API.</p>
        <button type="button" className="workspace-button" onClick={() => setClearing(true)}>Clear audio-derived discussion</button>
        {clearing && <div role="alertdialog" aria-modal="false" aria-label="Clear audio discussion confirmation">
          <p>Clear the discussion and its pending source association? The saved transcription job remains in the backend. Project name and description stay unchanged.</p>
          <button type="button" className="workspace-button" onClick={() => { setInput((previous) => ({ ...previous, discussion_text: '' })); setProvenance(null); setClearing(false) }}>Clear discussion and association</button>
          <button type="button" className="workspace-button" onClick={() => setClearing(false)}>Keep audio discussion</button>
        </div>}
      </div>}
      <p className="field-help">Project saving supports 100,000 characters. The backend's extraction limit defaults to 30,000 and may be configured differently.</p>
      {failure && <div className="error-message" role="alert"><p>{failure.message}</p>{failure.uncertain && <p>Saving may have completed. Refresh the project list before submitting again to avoid creating a duplicate.</p>}</div>}
      <button className="primary-button" type="submit" disabled={saving || Boolean(provenance)}>{saving ? 'Saving project…' : 'Save and open project'}</button>
      <p className="sr-only" role="status">{saving ? 'Saving project. Please wait.' : ''}</p>
    </form>
  </section>
}
