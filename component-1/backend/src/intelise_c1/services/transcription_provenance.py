"""Validate a stored ASR result and snapshot its source, never client model claims."""
from hashlib import sha256

from pydantic import ValidationError

from intelise_c1.api.project_schemas import TranscriptionProvenance
from intelise_c1.api.transcription_schemas import TranscriptResult


class TranscriptionReferenceError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


INVALID_RESULT = 'The completed transcription has no valid speech result. Review or transcribe the recording again.'


def source_hash(text):
    return sha256(text.encode('utf-8')).hexdigest()


def build_provenance(job, identifier, reviewed_text, recorded_at):
    if job is None:
        raise TranscriptionReferenceError(404, 'Referenced transcription not found. No project was saved.')
    if job.status != 'completed':
        raise TranscriptionReferenceError(409, 'Referenced transcription must be completed before saving a reviewed discussion. No project was saved.')
    try:
        result = TranscriptResult.model_validate(job.model_dump(include=set(TranscriptResult.model_fields)))
        if (job.transcription_id != identifier or result.outcome != 'review_required'
                or not result.asr_performed or not result.original_transcript
                or not result.original_transcript.strip() or not job.model.strip()
                or job.upload_bytes <= 0 or job.error_code is not None or job.error_message is not None
                or job.updated_at < job.created_at):
            raise ValueError('Unusable source result')
        return TranscriptionProvenance(
            transcription_id=identifier, model=job.model, language=job.language,
            provider=job.provider, api_version=job.api_version, locale=job.locale,
            original_transcript=result.original_transcript,
            original_transcript_hash=source_hash(result.original_transcript),
            reviewed_discussion_hash=source_hash(reviewed_text), segments=result.segments,
            audio_duration_seconds=result.audio_duration_seconds, processing_seconds=result.processing_seconds,
            transcription_created_at=job.created_at, transcription_completed_at=job.updated_at,
            review_recorded_at=recorded_at,
        )
    except (ValidationError, ValueError):
        # Never expose a Pydantic error containing the original transcript.
        raise TranscriptionReferenceError(409, INVALID_RESULT) from None
