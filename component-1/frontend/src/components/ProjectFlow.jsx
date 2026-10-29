import { useCallback, useRef, useState } from 'react'
import CreateProjectForm from './CreateProjectForm.jsx'
import ProjectDetail from './ProjectDetail.jsx'
import ProjectWorkspace from './ProjectWorkspace.jsx'
import SrsWorkspace from './SrsWorkspace.jsx'

const stages = [
  ['Create & review source', 'Project details · text or audio'],
  ['Classify & review labels', 'Extract · FR / NFR · human review'],
  ['Export results', 'Download JSON or text'],
  ['SRS & client review', 'Draft · feedback · approval'],
]

export default function ProjectFlow({ projectId, onSaved }) {
  const [step, setStep] = useState(projectId ? 2 : 1)
  const [revision, setRevision] = useState(0)
  const [classified, setClassified] = useState(false)
  const [reviewerName, setReviewerName] = useState('')
  const [reviewerError, setReviewerError] = useState('')
  const reviewerInputRef = useRef(null)
  const onReviewerChange = (value) => { setReviewerName(value); if (value.trim()) setReviewerError('') }
  function goToStep(next) {
    if (next === 3 && !reviewerName.trim()) {
      setReviewerError('Please provide your reviewer name or ID.')
      setStep(2)
      requestAnimationFrame(() => reviewerInputRef.current?.focus())
      return
    }
    setStep(next)
  }
  const onProgress = useCallback((ready) => setClassified(ready), [])
  return <div className="project-flow">
    <nav className="flow-tracker" aria-label="Project workflow">
      <ol>{stages.map(([title, detail], index) => {
        const number = index + 1
        const complete = number === 1 ? !!projectId : number === 2 ? classified : false
        return <li key={title} className={`${step === number ? 'active' : ''} ${complete ? 'complete' : ''} ${number < step ? 'reached' : ''}`}>
          <button type="button" aria-current={step === number ? 'step' : undefined} disabled={number > 1 && !projectId || number === 3 && !classified} onClick={() => goToStep(number)}>
            <span className="step-number" aria-hidden="true">{complete && step !== number ? '✓' : number}</span>
            <span><strong>{title}</strong><small>{detail}</small></span>
          </button>
        </li>
      })}</ol>
    </nav>
    {!projectId ? <CreateProjectForm onSaved={onSaved} /> : <>
      <div className={`project-stage stage-${step}`}>
      <ProjectDetail projectId={projectId} activeStep={step} onExtractionSaved={() => setRevision((value) => value + 1)} />
      <div hidden={step === 1 || step === 4}><ProjectWorkspace projectId={projectId} refreshKey={revision} activeStep={step} onProgress={onProgress} reviewerProps={{ reviewerName, onReviewerChange, reviewerError, reviewerInputRef }} /></div>
      </div>
      {step === 4 && <SrsWorkspace projectId={projectId} />}
      <div className="flow-actions">
        {step === 1 && <button className="primary-button" onClick={() => setStep(2)}>Continue to classification →</button>}
        {step === 2 && <><button className="secondary-button" onClick={() => setStep(1)}>← Review saved source</button><button className="primary-button" disabled={!classified} onClick={() => goToStep(3)}>Continue to export →</button></>}
        {step === 3 && <><button className="secondary-button" onClick={() => setStep(2)}>← Back to label review</button><button className="primary-button" onClick={() => setStep(4)}>Continue to SRS →</button></>}
        {step === 4 && <button className="secondary-button" onClick={() => setStep(2)}>← Back to label review</button>}
      </div>
    </>}
  </div>
}
