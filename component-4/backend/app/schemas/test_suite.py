import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TestSuiteProvenance(str, Enum):
    """Source provenance of the trusted test suite."""

    __test__ = False
    RUN_EXPLICIT = "RUN_EXPLICIT"                  # Explicitly supplied during verification run creation/execution
    SUBMISSION_ATTACHED = "SUBMISSION_ATTACHED"    # Attached to the code submission
    RECOVERED_AUTHORIZED = "RECOVERED_AUTHORIZED"  # Independently supplied and authorized for historical run
    LEGACY_MIGRATED = "LEGACY_MIGRATED"            # Migrated from legacy telemetry metadata


class TrustedTestSuite(BaseModel):
    """
    Immutable trusted test suite specification used for isolated Docker verification
    and subsequent repair re-verification.
    """

    __test__ = False
    model_config = ConfigDict(populate_by_name=True)

    suite_id: str = Field(
        default_factory=lambda: f"suite-{uuid.uuid4().hex[:12]}",
        description="Unique trusted test suite identifier",
    )
    verification_run_id: str = Field(description="Associated verification run ID")
    submission_id: Optional[str] = Field(default=None, description="Associated submission ID")
    test_code: str = Field(description="Authorized executable pytest source code")
    content_hash: str = Field(description="SHA-256 hash of the authorized test_code")
    provenance: TestSuiteProvenance = Field(
        default=TestSuiteProvenance.RUN_EXPLICIT,
        description="Provenance of the test specification",
    )
    test_types: List[str] = Field(
        default_factory=lambda: ["unit"],
        description="Target test categories (e.g. unit, integration)",
    )
    execution_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime container execution configuration",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Provenance or authorization notes",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )

    @classmethod
    def compute_hash(cls, code: str) -> str:
        """Computes deterministic SHA-256 hash of the normalized test code."""
        return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


class TrustedTestSuiteResponse(BaseModel):
    """
    Public metadata response for a trusted test suite.
    Avoids unnecessarily exposing full raw executable test source in public telemetry.
    """

    __test__ = False
    model_config = ConfigDict(populate_by_name=True)

    suite_id: str = Field(description="Unique trusted test suite identifier")
    verification_run_id: str = Field(description="Associated verification run ID")
    submission_id: Optional[str] = Field(default=None, description="Associated submission ID")
    content_hash: str = Field(description="SHA-256 content hash")
    provenance: TestSuiteProvenance = Field(description="Provenance of test specification")
    test_types: List[str] = Field(description="Target test categories")
    notes: Optional[str] = Field(default=None, description="Authorization notes")
    created_at: datetime = Field(description="Creation timestamp")


class TrustedTestSuiteAttachRequest(BaseModel):
    """
    Payload to explicitly supply an authorized test specification for historical runs
    or runs lacking durable test specifications.
    """

    __test__ = False

    test_code: str = Field(
        min_length=1,
        max_length=500_000,
        description="Authorized executable pytest test code",
    )
    provenance: TestSuiteProvenance = Field(
        default=TestSuiteProvenance.RECOVERED_AUTHORIZED,
        description="Provenance of the authorized test specification",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Independent authorization or provenance rationale",
    )

    @field_validator("test_code")
    @classmethod
    def validate_code_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Authorized test code cannot be empty or whitespace only.")
        if "\0" in v:
            raise ValueError("Authorized test code cannot contain null bytes.")
        return v
