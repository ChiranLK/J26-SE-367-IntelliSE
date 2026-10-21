"""Project input limits and public records, separate from BSON storage."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from intelise_c1.api.transcription_schemas import Segment


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    discussion_text: str = Field(min_length=1, max_length=100_000)
    transcription_id: UUID | None = Field(default=None, description=(
        "Optional completed transcription UUID. discussion_text is the user's reviewed draft; "
        "original transcript and model metadata are retrieved from backend storage."
    ))

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()

    @field_validator("discussion_text")
    @classmethod
    def validate_discussion(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Discussion text must not be blank")
        # Validate without normalizing whitespace, line breaks, or Unicode.
        return value


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: str | None
    status: Literal["draft"]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TranscriptionProvenance(BaseModel):
    """Backend-owned source snapshot; user review is asserted, not independently verified."""
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["c1-transcription-provenance-v1"] = "c1-transcription-provenance-v1"
    transcription_id: str
    provider: Literal["whisper", "azure"] = "whisper"
    api_version: str | None = None
    locale: str | None = None
    model: str = Field(min_length=1, max_length=200)
    language: Literal["en"]
    original_transcript: str = Field(min_length=1, max_length=40000)
    original_transcript_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_discussion_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    segments: list[Segment] = Field(max_length=500)
    audio_duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    processing_seconds: float = Field(ge=0, allow_inf_nan=False)
    transcription_created_at: AwareDatetime
    transcription_completed_at: AwareDatetime
    review_recorded_at: AwareDatetime
    review_status: Literal["user_reviewed"] = "user_reviewed"


class ProjectRecord(ProjectSummary):
    discussion_text: str
    transcription_provenance: TranscriptionProvenance | None = None


class ProjectPage(BaseModel):
    items: list[ProjectSummary]
    limit: int
    offset: int
    has_more: bool
