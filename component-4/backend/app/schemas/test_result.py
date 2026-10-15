from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.schemas.common import TestResultStatus, TestType


class TestResult(BaseModel):
    """Schema representing an individual test execution result."""

    __test__ = False

    test_id: str = Field(description="Unique identifier for the test case")
    name: str = Field(description="Descriptive name of the test")
    test_name: Optional[str] = Field(default=None, description="Alias for descriptive name (for frontend compatibility)")
    test_type: TestType = Field(description="Category of test (unit, integration, performance)")
    status: TestResultStatus = Field(description="Execution outcome")
    duration_ms: Optional[float] = Field(default=None, description="Execution duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Failure or error message if applicable")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace or diagnostics if available")
    stdout: Optional[str] = Field(default=None, description="Captured standard output for this test execution")
    stderr: Optional[str] = Field(default=None, description="Captured standard error for this test execution")
    metrics: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Performance or coverage metrics associated with this test",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when test completed",
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.test_name and self.name:
            self.test_name = self.name
        elif not self.name and self.test_name:
            self.name = self.test_name
