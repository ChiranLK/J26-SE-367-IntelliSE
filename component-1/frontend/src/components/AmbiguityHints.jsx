import { analyseAmbiguity } from '../services/ambiguity.js'

export default function AmbiguityHints({ text, scope = 'requirement_text' }) {
  const analysis = analyseAmbiguity(text, { scope })
  const source = scope === 'discussion_text'
  const visibleIssues = analysis.issues.slice(0, 20)
  return <details open={source && analysis.issues.length > 0 ? true : undefined} className={`ambiguity-hints ${source ? 'source-ambiguity-review' : ''} ${analysis.issues.length ? 'has-flags' : ''}`}>
    <summary>{source ? 'Unclear wording in saved discussion' : 'Unclear points'} {analysis.issues.length ? `· ${analysis.issues.length} potential ${analysis.issues.length === 1 ? 'flag' : 'flags'}` : '· No rule matches'}</summary>
    {source && <p className="source-review-explanation">This checks the full saved discussion before extraction. Flags here are source wording hints, not extracted requirements or FR/NFR predictions. They stay visible even if extraction omits a sentence.</p>}
    <p className="ambiguity-scope">English wording rules suggest questions for human review. This is separate from FR/NFR prediction and is not a trained ambiguity model. Context may already explain a flagged phrase; no match does not prove clarity.</p>
    {analysis.issues.length > 0 ? <ul>{visibleIssues.map((issue) => <li key={`${issue.rule_id}-${issue.start}`}>
      <p><strong>“{issue.phrase}”</strong> — {issue.reason}</p>
      <p><strong>Ask the client:</strong> {issue.clarification_question}</p>
      {source && <small>Saved discussion characters {issue.start}–{issue.end} (end exclusive)</small>}
    </li>)}</ul> : <p>No configured rule matched. Review missing context, references and measurable acceptance criteria with the client.</p>}
    {visibleIssues.length < analysis.issues.length && <p className="ambiguity-scope">Showing the first {visibleIssues.length} of {analysis.issues.length} flags. The export includes the full analysis.</p>}
    {source && <p className="ambiguity-scope">Conversation can also trigger these wording rules. Review the full discussion for omitted requirements; this check does not establish extraction completeness.</p>}
    <p className="ambiguity-scope">These hints do not rewrite or approve the saved requirement. Clarify the source with your client before creating revised requirements.</p>
  </details>
}
