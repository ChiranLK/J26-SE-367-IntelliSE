from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.schemas.common import TestResultStatus, TestType


class TestResult(BaseModel):
    """Schema representing an individual test execution result."""

    __test__ = False

    test_id: str = Field(description="Unique identifier for the test case")
    name: str = Field(description="Descriptive name of the test")
    test_type: TestType = Field(description="Category of test (unit, integration, performance)")
    status: TestResultStatus = Field(description="Execution outcome")
    duration_ms: Optional[float] = Field(default=None, description="Execution duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Failure or error message if applicable")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace or diagnostics if available")
    metrics: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Performance or coverage metrics associated with this test",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when test completed",
    )
