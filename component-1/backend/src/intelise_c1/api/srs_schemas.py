"""Versioned SRS snapshots; client feedback is separate from FR/NFR review."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ActorInput(InputModel):
    submission_id: UUID
    expected_revision: int = Field(ge=0)
    reviewer_id: str = Field(min_length=1, max_length=120)

    @field_validator('reviewer_id')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Reviewer name or ID is required')
        return value.strip()


class DraftInput(ActorInput):
    extraction_run_id: UUID
    classification_id: UUID


class FeedbackInput(ActorInput):
    version_id: UUID
    requirement_id: str = Field(min_length=1, max_length=200)
    decision: Literal['accepted', 'request_changes', 'needs_clarification']
    comment: str = Field(default='', max_length=2000)


class BulkAcceptInput(ActorInput):
    version_id: UUID
    confirm: Literal[True]


class RequirementChange(InputModel):
    requirement_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    label: Literal['FR', 'NFR']
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('text', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Text and change reason must not be blank')
        return value


class RevisionInput(ActorInput):
    base_version_id: UUID
    changes: list[RequirementChange] = Field(min_length=1, max_length=100)


class ApprovalInput(ActorInput):
    version_id: UUID
    confirm: Literal[True]


class SrsRequirement(BaseModel):
    requirement_id: str
    text: str
    label: Literal['FR', 'NFR']
    original_text: str
    label_review_id: str | None
    source_text_hash: str
    change_reason: str | None = None
    authored_revision: bool = False


class ClientFeedback(BaseModel):
    feedback_id: str
    requirement_id: str
    decision: Literal['accepted', 'request_changes', 'needs_clarification']
    comment: str
    reviewer_id: str
    recorded_at: AwareDatetime
    identity_status: Literal['self_reported'] = 'self_reported'


class SrsApproval(BaseModel):
    reviewer_id: str
    approved_at: AwareDatetime
    content_hash: str
    identity_status: Literal['self_reported'] = 'self_reported'


class SrsVersion(BaseModel):
    version_id: str
    version_number: int
    parent_version_id: str | None = None
    project_title: str
    project_description: str | None
    extraction_run_id: str
    classification_id: str
    source_discussion_hash: str
    created_at: AwareDatetime
    created_by: str
    generation_method: Literal['reviewed-requirements-template-v1', 'classified-requirements-template-v2'] = 'reviewed-requirements-template-v1'
    status: Literal['draft', 'approved'] = 'draft'
    requirements: list[SrsRequirement]
    content_hash: str
    feedback: list[ClientFeedback] = Field(default_factory=list)
    approval: SrsApproval | None = None


class Receipt(BaseModel):
    submission_id: str
    request_hash: str
    version_id: str


class SrsState(BaseModel):
    schema_version: Literal['c1-srs-v1'] = 'c1-srs-v1'
    project_id: str
    revision: int = 0
    versions: list[SrsVersion] = Field(default_factory=list)
    receipts: list[Receipt] = Field(default_factory=list, exclude=True)
