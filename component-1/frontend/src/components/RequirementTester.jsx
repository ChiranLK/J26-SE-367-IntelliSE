import { useEffect, useRef, useState } from 'react'
import { classifyRequirement } from '../services/api.js'
import RequirementFileTester from './RequirementFileTester.jsx'

export default function RequirementTester() {
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [fileBusy, setFileBusy] = useState(false)
  const active = useRef(null)
  const available = import.meta.env.DEV

  useEffect(() => () => active.current?.abort(), [])

  async function check(event) {
    event.preventDefault()
    if (active.current || !available) return
    setResult(null)
    setError('')
    if (!text.trim()) { setError('Enter a requirement to check.'); return }
    if (Array.from(text).length > 5000) { setError('Use no more than 5,000 characters.'); return }
    const controller = new AbortController()
    active.current = controller
    setLoading(true)
    try {
      const prediction = await classifyRequirement(text, { signal: controller.signal })
      if (!controller.signal.aborted) setResult(prediction)
    } catch (problem) {
      if (!controller.signal.aborted) setError(problem.message)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
      if (active.current === controller) active.current = null
    }
  }

  return <section className="requirement-tester" aria-labelledby="requirement-tester-title">
    <div className="section-heading">
      <div><p className="eyebrow section-eyebrow">TRY THE TRAINED BASELINE</p><h2 id="requirement-tester-title">Functional or non-functional?</h2></div>
      <p>TF-IDF + logistic regression · Local model</p>
    </div>
    <p className="tester-description">Type one software requirement to see its predicted category. This check does not save a project or run extraction.</p>
    <form onSubmit={check} aria-busy={loading}>
      <label htmlFor="test-requirement">Requirement</label>
      <textarea id="test-requirement" rows={3} value={text} disabled={loading || fileBusy || !available}
        placeholder="For example: Search results shall appear within two seconds."
        aria-describedby="tester-help" aria-invalid={Boolean(error)}
        onChange={(event) => { setText(event.target.value); setResult(null); setError('') }} />
      <div className="tester-actions"><p id="tester-help">One requirement at a time · Up to 5,000 characters</p>
        <button className="workspace-button primary" type="submit" disabled={loading || fileBusy || !available}>{loading ? 'Checking model…' : 'Check requirement'}</button></div>
    </form>
    {!available && <p className="workspace-notice" role="status">This local tester is available with npm run dev. A static production build cannot run the Python model.</p>}
    <div aria-live="polite" aria-atomic="true">
      {loading && <p role="status">Checking the saved model. The first request may take longer while it loads.</p>}
      {error && <p className="workspace-error" role="alert">{error}</p>}
      {result && <div className={`tester-result ${result.label.toLowerCase()}`}>
        <p className="tester-result-heading">Model prediction</p>
        <h3><span className={`requirement-badge ${result.label.toLowerCase()}`}>{result.label}</span> {result.label === 'FR' ? 'Functional requirement' : 'Non-functional requirement'}</h3>
        <p className="tester-input">{result.requirement_text}</p>
        <dl className="classification-metadata">
          <div><dt>Model</dt><dd>TF-IDF + logistic regression</dd></div>
          <div><dt>Model version</dt><dd><code>{result.model_version}</code></dd></div>
          <div><dt>Processing time</dt><dd>{result.processing_seconds.toFixed(2)} seconds</dd></div>
        </dl>
      </div>}
    </div>
    <RequirementFileTester available={available} disabled={loading} requestLockRef={active} onBusyChange={setFileBusy} />
    <p className="workspace-note">A baseline prediction for human review. The model can make mistakes and assigns FR or NFR even to input that is not a requirement.</p>
  </section>
}
