export const transcriptionId = (n = 1) => `880a97af-dda2-48ef-969a-${n.toString(16).padStart(12, '0')}`
export const originalTranscript = ' Customers can book appointments. <b>Review every word.</b> '
export function transcriptionJob(status = 'completed', id = transcriptionId()) {
  return {
    transcription_id: id, status, model: 'tiny.en', language: 'en',
    created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T00:00:00Z', upload_bytes: 100,
    audio_duration_seconds: status === 'completed' ? 3 : null,
    processing_seconds: status === 'completed' ? .2 : null,
    original_transcript: status === 'completed' ? originalTranscript : null,
    reviewed_text: null, review_status: 'needs_review',
    segments: status === 'completed' ? [{ start: 0, end: 3, text: originalTranscript }] : [],
    outcome: status === 'completed' ? 'review_required' : null,
    asr_performed: status === 'completed' ? true : null,
    error_code: status === 'failed' ? 'invalid_audio' : null,
    error_message: status === 'failed' ? 'Audio decode fixture failure.' : null,
  }
}
