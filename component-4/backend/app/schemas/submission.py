from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.schemas.common import ProgrammingLanguage, SubmissionSource


class CodeSubmissionCreate(BaseModel):
    """Payload for manual code submission."""

    code: str = Field(
        min_length=1,
        max_length=500_000,
        description="Source code submitted for verification",
    )
    language: ProgrammingLanguage = Field(
        description="Programming language of the submitted code",
    )
    filename: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional filename associated with the code snippet",
    )
    requirement_ids: List[str] = Field(
        default_factory=list,
        description="Optional requirement identifiers that this code is intended to satisfy",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata (e.g. Component 3 caller info, component tag)",
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Submitted code cannot be empty or whitespace only.")
        return v

    @field_validator("requirement_ids")
    @classmethod
    def clean_requirement_ids(cls, v: List[str]) -> List[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        return cleaned


class CodeSubmissionResponse(BaseModel):
    """Response representing a stored code submission."""

    id: str = Field(description="Unique submission identifier (e.g. sub-...)")
    code: str = Field(description="Source code content")
    language: ProgrammingLanguage = Field(description="Programming language")
    filename: Optional[str] = Field(default=None, description="Filename if provided")
    requirement_ids: List[str] = Field(
        default_factory=list,
        description="Associated requirement identifiers",
    )
    source_type: SubmissionSource = Field(
        default=SubmissionSource.MANUAL_ENTRY,
        description="Submission mechanism (manual entry, file upload, etc.)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of submission creation",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata",
    )


class CodeSubmissionListResponse(BaseModel):
    """Paginated or listed view of code submissions."""

    total: int = Field(description="Total count of stored submissions")
    items: List[CodeSubmissionResponse] = Field(description="List of submissions")
