import { useState } from 'react'
import { buildRequirementExport, downloadRequirementExport, exportAsText, simplifiedRequirementExport } from '../services/requirementExport.js'

export default function RequirementExport({ project, extraction, classification, reviews, loading, error, dirtyCount }) {
  const [format, setFormat] = useState('json')
  let data
  let failure = error?.message ?? ''
  try { data = buildRequirementExport(project, extraction, classification, [...reviews.values()]) } catch (problem) { failure = problem.message }
  const blocked = loading || !!failure || dirtyCount > 0
  const reviewed = data?.requirements.filter((item) => item.label_source === 'user_reviewed').length ?? 0
  return <section className="export-panel" aria-labelledby="export-heading">
    <p className="eyebrow">STEP 3 · EXPORT RESULTS</p><h2 id="export-heading">Your requirements, ready to share</h2>
    <p>Download your project title, description and requirements grouped as FR and NFR.</p>
    {loading && <p role="status">Loading saved reviews before export…</p>}
    {failure && <p role="alert">Export unavailable. {failure}</p>}
    {dirtyCount > 0 && <p className="workspace-notice" role="alert">You have {dirtyCount} unsaved label {dirtyCount === 1 ? 'review' : 'reviews'}. Go back and save those edits before exporting.</p>}
    {!blocked && data && <>
      <div className="export-counts"><div><strong>{data.requirements.length}</strong><span>Requirements</span></div><div><strong>{data.requirements.filter((item) => item.label === 'FR').length}</strong><span>Functional (FR)</span></div><div><strong>{data.requirements.filter((item) => item.label === 'NFR').length}</strong><span>Non-functional (NFR)</span></div><div><strong>{reviewed}/{data.requirements.length}</strong><span>Labels reviewed</span></div></div>
      {reviewed < data.requirements.length && <p className="workspace-notice">{data.requirements.length - reviewed} labels are still model predictions. Review them before sharing. Saved reviewed labels take priority.</p>}
      <fieldset className="export-format"><legend>Choose a format</legend>{['json', 'txt'].map((value) => <label key={value}><input type="radio" name="export-format" value={value} checked={format === value} onChange={() => setFormat(value)} />{value === 'json' ? 'JSON — structured data' : 'Text — easy to read'}</label>)}</fieldset>
      <button className="primary-button" onClick={() => downloadRequirementExport(data, format)}>Download {format === 'json' ? 'JSON' : 'text'}</button>
      <details className="export-preview" open><summary>Preview {format === 'json' ? 'JSON' : 'text'} export</summary><pre tabIndex={0} aria-label="Export preview">{format === 'json' ? JSON.stringify(simplifiedRequirementExport(data), null, 2) : exportAsText(data)}</pre></details>
    </>}
    <p className="workspace-note">Source evidence, model details and reviews remain available in the project.</p>
  </section>
}
