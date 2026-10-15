import { useEffect, useRef, useState } from 'react'
import { getTranscription, transcribeAudio } from '../services/api.js'
import { terminalTranscription, validateAudioFile } from '../services/transcriptionContracts.js'
import { pollTranscription } from '../services/transcriptionPolling.js'
import { characterCount, PROJECT_LIMITS } from '../services/contracts.js'

export default function AudioTranscription({ disabled, onUse, provenanceAvailable = false }) {
  const [file, setFile] = useState(null)
  const [job, setJob] = useState(null)
  const [activity, setActivity] = useState(null)
  const [failure, setFailure] = useState(null)
  const [uncertain, setUncertain] = useState(false)
  const [reviewed, setReviewed] = useState('')
  const pending = useRef(null)
  const reviewJob = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])

  const activeJob = job && !terminalTranscription(job)
  const locked = disabled || Boolean(activity) || Boolean(activeJob) || uncertain
  const usable = job?.status === 'completed' && job.outcome === 'review_required'
    && job.asr_performed && Boolean(job.original_transcript?.trim())

  function receive(next) {
    setJob(next)
    // Manual refresh must never overwrite the user's edited copy.
    if (next.status === 'completed' && reviewJob.current !== next.transcription_id) {
      reviewJob.current = next.transcription_id
      setReviewed(next.original_transcript ?? '')
    }
  }

  async function upload() {
    if (pending.current || locked) return
    const invalid = validateAudioFile(file)
    if (invalid) { setFailure({ message: invalid }); return }
    const controller = new AbortController()
    pending.current = controller
    setActivity('uploading')
    setFailure(null)
    let accepted = false
    try {
      const result = await transcribeAudio(file, { signal: controller.signal })
      if (controller.signal.aborted) return
      accepted = true
      setJob(result)
      setActivity('polling')
      await pollTranscription(result.transcription_id, { signal: controller.signal, onUpdate: receive })
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailure(error)
        if (!accepted && error.uncertain) setUncertain(true)
      }
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setActivity(null) }
    }
  }

  async function refresh() {
    if (pending.current || !job) return
    const controller = new AbortController()
    pending.current = controller
    setActivity('refreshing')
    setFailure(null)
    try {
      const next = await getTranscription(job.transcription_id, { signal: controller.signal })
      if (!controller.signal.aborted) receive(next)
    } catch (error) {
      if (!controller.signal.aborted) setFailure(error)
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setActivity(null) }
    }
  }

  return <div className="audio-transcription">
    <div className="form-field">
      <label htmlFor="audio-file">Audio recording</label>
      <input id="audio-file" type="file" accept=".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4" disabled={locked}
        aria-describedby="audio-limits" onChange={(event) => {
          const selected = event.target.files?.[0] ?? null
          setFile(selected)
          setFailure(selected ? { message: validateAudioFile(selected) } : null)
        }} />
      <p id="audio-limits" className="field-help">WAV, MP3 or M4A · Default limit: 10 MB (10,000,000 bytes) and 2 minutes. The server checks decoding and duration; configured limits may differ. English transcription requires review.</p>
      {file && <p className="audio-filename">Selected: {file.name}</p>}
    </div>
    <button type="button" className="workspace-button" onClick={upload} disabled={locked || !file || Boolean(validateAudioFile(file))}>
      {activity === 'uploading' ? 'Uploading audio…' : 'Transcribe audio'}
    </button>
    <p role="status" aria-live="polite" className="audio-status">{activity === 'uploading' ? 'Uploading audio. Please wait.'
      : job ? `Transcription ${job.status}.${activity === 'polling' ? ' Checking status automatically.' : ''}` : 'No audio submitted.'}</p>
    {job && <div className="audio-job">
      <p className="record-id">Transcription ID: <code>{job.transcription_id}</code></p>
      <button type="button" className="workspace-button" onClick={refresh} disabled={disabled || Boolean(activity)}>
        {activity === 'refreshing' ? 'Refreshing status…' : 'Refresh transcription status'}
      </button>
      {activeJob && !activity && <p className="field-help">Automatic polling has stopped. Refresh manually to check this saved job. No new upload has been submitted.</p>}
      {job.model && <dl className="run-metadata">
        <div><dt>Model / language</dt><dd>{job.model} / {job.language}</dd></div>
        <div><dt>Created</dt><dd>{new Date(job.created_at).toLocaleString()}</dd></div>
        {job.audio_duration_seconds !== null && <div><dt>Audio duration</dt><dd>{job.audio_duration_seconds} seconds</dd></div>}
        {job.processing_seconds !== null && <div><dt>Processing time</dt><dd>{job.processing_seconds.toFixed(2)} seconds</dd></div>}
      </dl>}
      {job.status === 'failed' && <div role="alert" className="error-message"><p>Transcription failed: {job.error_message}</p><p className="field-help">{job.error_code}. No transcript was substituted. Review the recording or backend configuration before a new submission.</p></div>}
      {job.status === 'completed' && <>
        <p className="review-note">Human review required. ASR can invent or omit speech. Check names, numbers, permissions and negation against the recording.</p>
        {!usable && <p role="status" className="workspace-notice">{job.outcome === 'silence_detected'
          ? 'Silence was detected; transcription was skipped. There is no generated transcript to use.'
          : 'No intelligible speech was reported. Review the recording; this output cannot be used as a discussion.'}</p>}
        <details className="audio-original"><summary>Original ASR transcript (unchanged)</summary>
          {job.original_transcript === null ? <p>No generated transcript is available.</p> : <pre>{job.original_transcript}</pre>}
          {job.segments.length > 0 && <ol>{job.segments.map((segment, index) => <li key={index}><span>{segment.start}–{segment.end} s: </span>{segment.text}</li>)}</ol>}
        </details>
        <div className="form-field">
          <label htmlFor="reviewed-transcript">Editable transcript — requires review</label>
          <textarea id="reviewed-transcript" rows={7} value={reviewed} disabled={disabled || Boolean(activity) || !usable}
            onChange={(event) => setReviewed(event.target.value)} aria-describedby="transcript-review-help" />
          <p id="transcript-review-help" className="field-help">{characterCount(reviewed).toLocaleString()} / {PROJECT_LIMITS.discussion_text.toLocaleString()} characters. Editing keeps the generated original unchanged. This draft is local to this form.</p>
        </div>
        <button type="button" className="workspace-button primary" disabled={disabled || Boolean(activity) || !usable || !reviewed.trim() || characterCount(reviewed) > PROJECT_LIMITS.discussion_text}
          onClick={() => onUse(job, reviewed)}>Use this transcript</button>
        <p className="field-help">Copies your reviewed draft to the discussion field. Does not save a project or run extraction. {provenanceAvailable ? 'Explicit project saving will include its source transcription reference.' : 'Audio saving remains blocked until the configured backend confirms provenance support.'}</p>
      </>}
    </div>}
    {failure?.message && <div className="error-message" role="alert"><p>{failure.status === 404 ? 'The backend transcription endpoint or job is unavailable. Check that the audio-enabled backend is running.' : failure.message}</p>
      {job && <p>Last known job status is retained. Refresh manually; status-check failures do not prove transcription failed.</p>}
    </div>}
    {uncertain && <p role="alert" className="workspace-notice">Upload completion is unknown and no job ID was returned. A job may exist. Further uploads are blocked in this form to avoid duplicates; check the backend before starting a new form.</p>}
    <p className="field-help">Automatic checks stop after at most 5 minutes or 150 requests, or on a request error. Leaving this form stops browser checks; it does not cancel a backend job.</p>
  </div>
}
