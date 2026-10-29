// Verified against the backend audio worktree's generated OpenAPI and runtime schemas.
export const AUDIO_MAX_BYTES = 10000000
export const AUDIO_MAX_SECONDS = 120
export const validTranscriptionId = (id) => typeof id === 'string' && /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(id)
export const terminalTranscription = (job) => ['completed', 'failed'].includes(job.status)
const text = (value) => typeof value === 'string'
const finite = (value, minimum = 0) => Number.isFinite(value) && value >= minimum
const date = (value) => text(value) && /(Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))

export function validateAudioFile(file) {
  if (!file || typeof file.name !== 'string') return 'Choose a WAV, MP3 or M4A file.'
  if (!/\.(wav|mp3|m4a)$/i.test(file.name)) return 'Only WAV, MP3 and M4A files are supported.'
  if (!Number.isFinite(file.size) || file.size <= 0) return 'Choose a nonempty audio file.'
  if (file.size > AUDIO_MAX_BYTES) return 'Choose a file no larger than 10 MB (10,000,000 bytes).'
  return null
}

export const validJobAccepted = (job) => Boolean(job && validTranscriptionId(job.transcription_id) && job.status === 'queued')

export function validTranscription(job, id) {
  if (!job || job.transcription_id !== id || !validTranscriptionId(id)
    || !['queued', 'processing', 'completed', 'failed'].includes(job.status)
    || !text(job.model) || !job.model.trim() || job.language !== 'en'
    || !date(job.created_at) || !date(job.updated_at)
    || !Number.isInteger(job.upload_bytes) || job.upload_bytes <= 0
    || job.review_status !== 'needs_review' || job.reviewed_text !== null
    || !(job.original_transcript === null || text(job.original_transcript))
    || !(job.audio_duration_seconds === null || finite(job.audio_duration_seconds, Number.MIN_VALUE))
    || !(job.processing_seconds === null || finite(job.processing_seconds))
    || !Array.isArray(job.segments) || job.segments.length > 500
    || !job.segments.every((s) => s && finite(s.start) && finite(s.end, s.start) && text(s.text)
      && (job.audio_duration_seconds === null || s.end <= job.audio_duration_seconds + .5))) return false
  if (job.status === 'completed') {
    return finite(job.audio_duration_seconds, Number.MIN_VALUE) && finite(job.processing_seconds)
      && ((job.outcome === 'silence_detected' && job.asr_performed === false && job.original_transcript === null && job.segments.length === 0)
        || (['review_required', 'no_intelligible_speech'].includes(job.outcome) && job.asr_performed === true && text(job.original_transcript)))
  }
  if (job.status === 'failed') return text(job.error_code) && text(job.error_message)
    && job.original_transcript === null && job.segments.length === 0
  return job.original_transcript === null && job.segments.length === 0
}
