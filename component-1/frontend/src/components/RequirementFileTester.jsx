import { useEffect, useRef, useState } from 'react'
import { classifyRequirement } from '../services/api.js'
import { readRequirementFile } from '../services/requirementCsv.js'

export default function RequirementFileTester({ available, disabled, requestLockRef, onBusyChange }) {
  const [rows, setRows] = useState([])
  const [filename, setFilename] = useState('')
  const [reading, setReading] = useState(false)
  const [state, setState] = useState({ phase: 'idle', predictions: [], error: '' })
  const selection = useRef(0)
  const ownRequest = useRef(null)
  const running = state.phase === 'running'
  const compared = state.predictions.filter((_, index) => rows[index]?.expected)
  const matched = state.predictions.filter((prediction, index) => prediction.label === rows[index]?.expected).length

  useEffect(() => () => { selection.current++; ownRequest.current?.abort() }, [])

  async function select(event) {
    const file = event.target.files?.[0]
    const token = ++selection.current
    setRows([])
    setFilename(file?.name ?? '')
    setState({ phase: 'idle', predictions: [], error: '' })
    if (!file) return
    setReading(true)
    try {
      const parsed = await readRequirementFile(file)
      if (token === selection.current) setRows(parsed)
    } catch (error) {
      if (token === selection.current) setState({ phase: 'failed', predictions: [], error: error.message })
    } finally { if (token === selection.current) setReading(false) }
  }

  async function checkFile() {
    if (requestLockRef.current || !available || !rows.length || reading) return
    const controller = new AbortController()
    requestLockRef.current = controller
    ownRequest.current = controller
    onBusyChange(true)
    const predictions = []
    setState({ phase: 'running', predictions: [], error: '' })
    try {
      for (const row of rows) {
        const result = await classifyRequirement(row.requirement, { signal: controller.signal })
        if (controller.signal.aborted) return
        predictions.push(result)
        setState({ phase: 'running', predictions: [...predictions], error: '' })
      }
      setState({ phase: 'complete', predictions: [...predictions], error: '' })
    } catch (error) {
      if (!controller.signal.aborted) setState({ phase: 'failed', predictions: [...predictions], error: `File check stopped after ${predictions.length} of ${rows.length} requirements. ${error.message} Remaining rows were not checked.` })
    } finally {
      if (requestLockRef.current === controller) requestLockRef.current = null
      ownRequest.current = null
      if (!controller.signal.aborted) onBusyChange(false)
    }
  }

  return <div className="requirement-file-tester" aria-labelledby="file-tester-title">
    <h3 id="file-tester-title">Or upload a test file</h3>
    <p><a href={`${import.meta.env.BASE_URL}samples/fr-nfr-test.csv`} download>Download sample CSV (12 requirements)</a></p>
    <p className="workspace-note">Illustrative examples with suggested expected labels, not a research benchmark. Mismatches are shown honestly.</p>
    <label htmlFor="requirement-csv">Requirements CSV</label>
    <input id="requirement-csv" type="file" accept=".csv,text/csv" onChange={(event) => { void select(event) }} disabled={!available || disabled || running || reading} aria-describedby="csv-help" />
    <p id="csv-help" className="workspace-note">UTF-8 CSV · Up to 100 KB / 50 requirements · Columns: requirement, optional id and expected_label (FR/NFR).</p>
    {filename && <p className="workspace-note">Selected: {filename}{rows.length > 0 && ` · ${rows.length} requirements`}</p>}
    <button className="workspace-button primary" type="button" onClick={() => { void checkFile() }} disabled={!available || disabled || running || reading || !rows.length}>{running ? 'Checking file…' : 'Check uploaded file'}</button>
    <div role="status" aria-live="polite">
      {reading && <p>Reading CSV…</p>}
      {running && <p>Checked {state.predictions.length} of {rows.length}. Requirements are processed one at a time.</p>}
      {state.phase === 'complete' && <p>File check complete: {state.predictions.length} requirements checked.</p>}
    </div>
    {state.error && <p className="workspace-error" role="alert">{state.error}</p>}
    {rows.length > 0 && <div className="tester-table-scroll"><table className="tester-table">
      <caption>Uploaded requirements: expected labels and actual model predictions</caption>
      <thead><tr><th scope="col">ID</th><th scope="col">Requirement</th><th scope="col">Expected</th><th scope="col">Predicted</th><th scope="col">Comparison</th></tr></thead>
      <tbody>{rows.map((row, index) => {
        const prediction = state.predictions[index]
        return <tr key={row.id}>
          <th scope="row">{row.id}</th><td>{row.requirement}</td><td>{row.expected ?? '—'}</td>
          <td>{prediction ? <span className={`requirement-badge ${prediction.label.toLowerCase()}`}>{prediction.label === 'FR' ? 'FR · Functional' : 'NFR · Non-functional'}</span> : 'Not checked'}</td>
          <td>{!prediction || !row.expected ? '—' : prediction.label === row.expected ? 'Match' : 'Mismatch'}</td>
        </tr>
      })}</tbody>
    </table></div>}
    {compared.length > 0 && <p className="workspace-note">{matched} of {compared.length} expected labels matched. This sample comparison is not a general accuracy estimate.</p>}
    {state.predictions.length > 0 && <p className="workspace-note">Model: TF-IDF + logistic regression · Version <code className="tester-version">{state.predictions[0].model_version}</code></p>}
    <p className="workspace-note">The file is read in your browser. Clicking Check sends its requirement texts to the local model; expected labels are used only for comparison. No project or results are saved.</p>
  </div>
}
