import { useEffect, useRef, useState } from 'react'
import { createProject } from '../services/api.js'
import { characterCount, PROJECT_LIMITS, validateProjectInput } from '../services/contracts.js'

export default function CreateProjectForm({ onSaved }) {
  const [input, setInput] = useState({ name: '', description: '', discussion_text: '' })
  const [errors, setErrors] = useState({})
  const [failure, setFailure] = useState(null)
  const [saving, setSaving] = useState(false)
  const pending = useRef(null)
  const form = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
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
      {field('discussion_text', 'Original client discussion', true, 9)}
      <p className="field-help">Project saving supports 100,000 characters. The backend's extraction limit defaults to 30,000 and may be configured differently.</p>
      {failure && <div className="error-message" role="alert"><p>{failure.message}</p>{failure.uncertain && <p>Saving may have completed. Refresh the project list before submitting again to avoid creating a duplicate.</p>}</div>}
      <button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving project…' : 'Save and open project'}</button>
      <p className="sr-only" role="status">{saving ? 'Saving project. Please wait.' : ''}</p>
    </form>
  </section>
}
