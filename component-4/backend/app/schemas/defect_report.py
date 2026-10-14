from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import DefectSeverity


class DefectReport(BaseModel):
    """Structured defect report generated when verification checks detect failures."""

    defect_id: str = Field(description="Unique defect identifier (e.g. def-...)")
    requirement_id: Optional[str] = Field(
        default=None,
        description="Associated requirement ID that the defect violates",
    )
    title: str = Field(description="Concise description of the defect")
    severity: DefectSeverity = Field(
        default=DefectSeverity.MEDIUM,
        description="Severity classification of the defect",
    )
    description: str = Field(description="Detailed explanation of the failure mode")
    file_path: Optional[str] = Field(
        default=None,
        description="Relative file path where defect was identified",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number if localized to a specific source line",
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        description="High-level suggestion for Component 3 correction (Component 4 does not modify code)",
    )
    xai_explanation: Optional[str] = Field(
        default=None,
        description="Conditional explainable AI feedback generated in later phases",
    )
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when defect report was generated",
    )
