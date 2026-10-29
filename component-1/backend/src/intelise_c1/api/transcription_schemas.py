"""Server-owned jobs and immutable generated transcripts awaiting human review."""
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Segment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    text: str = Field(max_length=10000)

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start:
            raise ValueError('Segment timestamps must be ordered')
        return self


class TranscriptResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    audio_duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    processing_seconds: float = Field(ge=0, allow_inf_nan=False)
    original_transcript: str | None = Field(max_length=40000)
    segments: list[Segment] = Field(max_length=500)
    outcome: Literal['review_required', 'silence_detected', 'no_intelligible_speech']
    asr_performed: bool

    @model_validator(mode='after')
    def consistent(self):
        if any(s.end > self.audio_duration_seconds + .5 for s in self.segments):
            raise ValueError('Segment extends beyond decoded audio')
        if self.asr_performed and self.original_transcript is None:
            raise ValueError('ASR result must retain its original transcript')
        if not self.asr_performed and (self.original_transcript is not None or self.segments or self.outcome != 'silence_detected'):
            raise ValueError('Skipped ASR must not fabricate a transcript')
        return self


class JobAccepted(BaseModel):
    transcription_id: str
    status: Literal['queued'] = 'queued'


class TranscriptionJob(BaseModel):
    transcription_id: str
    status: Literal['queued', 'processing', 'completed', 'failed']
    model: str
    provider: Literal['whisper', 'azure'] = 'whisper'
    api_version: str | None = None
    locale: str | None = None
    language: Literal['en'] = 'en'
    created_at: AwareDatetime
    updated_at: AwareDatetime
    upload_bytes: int
    audio_duration_seconds: float | None = None
    original_transcript: str | None = None
    reviewed_text: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    processing_seconds: float | None = None
    outcome: Literal['review_required', 'silence_detected', 'no_intelligible_speech'] | None = None
    asr_performed: bool | None = None
    review_status: Literal['needs_review'] = 'needs_review'
    error_code: str | None = None
    error_message: str | None = None
