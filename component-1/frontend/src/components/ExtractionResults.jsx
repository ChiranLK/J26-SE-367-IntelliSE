import { formatDate } from '../services/format.js'

export default function ExtractionResults({ run }) {
  return <div className="extraction-results">
    <div className="run-heading"><h3>{run.candidates.length} requirement {run.candidates.length === 1 ? 'candidate' : 'candidates'}</h3><span className="unreviewed-tag">Unreviewed</span></div>
    <dl className="run-metadata">
      <div><dt>Run date</dt><dd><time dateTime={run.created_at}>{formatDate(run.created_at)}</time></dd></div>
      <div><dt>Model</dt><dd>{run.model_identifier}</dd></div>
      <div><dt>Prompt version</dt><dd>{run.prompt_version}</dd></div>
      <div><dt>Run ID</dt><dd className="mono">{run.run_id}</dd></div>
    </dl>
    <p className="review-note">These are generated candidates for human review. Supporting quotes establish traceability, not semantic correctness or client approval.</p>
    {run.candidates.length === 0 ? <p className="state-message">Extraction completed successfully with no requirement candidates. This empty result is saved.</p> :
      <ol className="requirement-list">{run.candidates.map((candidate, index) => <li className="requirement-card" key={candidate.requirement_id}>
        <div className="candidate-heading"><h4>Candidate {index + 1}</h4><span className="unreviewed-tag">{candidate.review_status}</span></div>
        <p className="requirement-text">{candidate.requirement_text}</p>
        <p className="requirement-id">Requirement ID <span className="mono">{candidate.requirement_id}</span></p>
        {(candidate.actor !== null || candidate.action !== null) && <dl className="actor-action">
          {candidate.actor !== null && <div><dt>Actor</dt><dd>{candidate.actor}</dd></div>}
          {candidate.action !== null && <div><dt>Action</dt><dd>{candidate.action}</dd></div>}
        </dl>}
        <h5>Supporting source evidence</h5>
        {candidate.evidence.map((span, spanIndex) => <figure className="evidence" key={spanIndex}>
          <blockquote>{span.quote}</blockquote>
          <figcaption>Source characters {span.start}–{span.end} (end exclusive)</figcaption>
        </figure>)}
      </li>)}</ol>}
    <details className="source-hash"><summary>Source discussion hash</summary><p className="mono">{run.source_discussion_hash}</p></details>
  </div>
}
