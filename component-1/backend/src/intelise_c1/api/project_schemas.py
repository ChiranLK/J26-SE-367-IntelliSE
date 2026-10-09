"""Project input limits and public records, separate from BSON storage."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    discussion_text: str = Field(min_length=1, max_length=100_000)

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


class ProjectRecord(ProjectSummary):
    discussion_text: str


class ProjectPage(BaseModel):
    items: list[ProjectSummary]
    limit: int
    offset: int
    has_more: bool
