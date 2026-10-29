import { formatDate } from '../services/format.js'

export default function ProjectSource({ source }) {
  return <section className="saved-audio-source" aria-labelledby="saved-source-heading">
    <h3 id="saved-source-heading">Saved audio source</h3>
    <p className="review-note">User-reviewed discussion. The original ASR output is retained separately. Source hashes establish text traceability; they do not independently verify the review or recording.</p>
    <dl className="run-metadata">
      <div><dt>Transcription ID</dt><dd><code>{source.transcription_id}</code></dd></div>
      <div><dt>Provider / model / language</dt><dd>{source.provider} / {source.model} / {source.language}</dd></div>
      <div><dt>Transcription created</dt><dd>{formatDate(source.transcription_created_at)}</dd></div>
      <div><dt>Transcription completed</dt><dd>{formatDate(source.transcription_completed_at)}</dd></div>
      <div><dt>Review recorded</dt><dd>{formatDate(source.review_recorded_at)}</dd></div>
      <div><dt>Duration / processing time</dt><dd>{source.audio_duration_seconds} s / {source.processing_seconds.toFixed(2)} s</dd></div>
    </dl>
    <details className="audio-original"><summary>Original ASR transcript (unchanged)</summary><pre tabIndex={0}>{source.original_transcript}</pre>
      {source.segments.length > 0 && <ol>{source.segments.map((segment, index) => <li key={index}>{segment.start}–{segment.end} s: {segment.text}</li>)}</ol>}
    </details>
    <details className="source-hash"><summary>Saved source hashes and version</summary>
      <dl className="run-metadata">
        <div><dt>Original ASR SHA-256</dt><dd className="mono">{source.original_transcript_hash}</dd></div>
        <div><dt>Reviewed discussion SHA-256</dt><dd className="mono">{source.reviewed_discussion_hash}</dd></div>
        <div><dt>Provenance version</dt><dd>{source.schema_version}</dd></div>
      </dl>
    </details>
  </section>
}
