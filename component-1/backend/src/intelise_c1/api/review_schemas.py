"""Label reviews are human feedback, never edits to predictions/client approval."""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    submission_id: UUID = Field(description='Client-generated UUID for idempotent explicit save/retry.')
    reviewed_label: Literal['FR', 'NFR']
    reviewer_id: str = Field(min_length=1, max_length=120)
    note: str = Field(default='', max_length=2000)

    @field_validator('reviewer_id')
    @classmethod
    def reviewer_nonblank(cls, value):
        if not value.strip():
            raise ValueError('Enter a reviewer name or identifier')
        return value.strip()


class LabelReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    review_id: str
    submission_id: str
    project_id: str
    extraction_run_id: str
    classification_id: str
    requirement_id: str
    original_prediction: Literal['FR', 'NFR']
    reviewed_label: Literal['FR', 'NFR']
    reviewer_id: str
    note: str
    model_identifier: str
    model_version: str
    source_discussion_hash: str
    requirement_text_hash: str
    reviewed_at: AwareDatetime
    review_status: Literal['user_reviewed'] = 'user_reviewed'
    reviewer_identity_status: Literal['self_reported'] = 'self_reported'


class ReviewPage(BaseModel):
    project_id: str
    extraction_run_id: str
    classification_id: str
    reviews: list[LabelReview] = Field(max_length=100)
