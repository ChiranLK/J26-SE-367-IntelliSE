import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RepairSource(str, Enum):
    """Origin of the corrected source code."""

    LOCAL_MANUAL = "LOCAL_MANUAL"
    LOCAL_UPLOAD = "LOCAL_UPLOAD"
    LOCAL_AUTOMATED = "LOCAL_AUTOMATED"
    EXTERNAL_COMPONENT_3 = "EXTERNAL_COMPONENT_3"


class RepairResponseStatus(str, Enum):
    """Lifecycle state of a repair response."""

    INGESTED = "INGESTED"
    REVERIFYING = "REVERIFYING"
    REVERIFIED = "REVERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    # Aliases
    VERIFYING = "REVERIFYING"
    VERIFIED = "REVERIFIED"


class ResolutionStatus(str, Enum):
    """Status of an individual test or defect after re-verification."""

    RESOLVED = "RESOLVED"
    STILL_FAILING = "STILL_FAILING"
    NEW_FAILURE = "NEW_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


class OverallResolutionVerdict(str, Enum):
    """Comprehensive verdict summarizing the repair outcome."""

    FULLY_RESOLVED = "FULLY_RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    REGRESSION_INTRODUCED = "REGRESSION_INTRODUCED"
    INCONCLUSIVE = "INCONCLUSIVE"


class TestResolutionDetail(BaseModel):
    """Comparison detail for an individual test case."""

    test_name: str = Field(description="Name or identifier of the test case")
    original_status: str = Field(description="Status in the original verification run (e.g. FAILED)")
    corrected_status: str = Field(description="Status in the corrected verification run (e.g. PASSED)")
    resolution_status: ResolutionStatus = Field(description="Resolution classification")
    error_message: Optional[str] = Field(default=None, description="Diagnostic error message if failing")
    notes: Optional[str] = Field(default=None, description="Additional context or comparison rationale")


class DefectResolutionDetail(BaseModel):
    """Comparison detail for a structured defect report."""

    defect_id: Optional[str] = Field(default=None, description="Original defect identifier")
    title: Optional[str] = Field(default=None, description="Defect title")
    failed_test: str = Field(description="Associated failed test case name")
    resolution_status: ResolutionStatus = Field(description="Resolution outcome")
    original_assertion: Optional[str] = Field(default=None, description="Original assertion or exception excerpt")
    notes: Optional[str] = Field(default=None, description="Explanatory notes regarding resolution")


class DefectResolutionComparison(BaseModel):
    """Deterministic before-and-after comparison between original and corrected verification runs."""

    original_run_id: str = Field(description="Original verification run ID")
    corrected_run_id: Optional[str] = Field(
        default=None, description="Re-verification run ID executing corrected code"
    )
    original_status: str = Field(description="Original verification run status")
    corrected_status: str = Field(description="Corrected verification run status")
    verdict: OverallResolutionVerdict = Field(description="Summary resolution verdict")
    original_defects_count: int = Field(default=0, ge=0, description="Total defect count in original run")
    resolved_defects_count: int = Field(default=0, ge=0, description="Count of demonstrably resolved defects")
    remaining_defects_count: int = Field(default=0, ge=0, description="Count of defects still failing")
    new_defects_count: int = Field(default=0, ge=0, description="Count of newly introduced defects/regressions")
    resolution_rate: float = Field(default=0.0, ge=0.0, le=100.0, description="Resolution percentage (0-100%)")
    test_comparisons: List[TestResolutionDetail] = Field(
        default_factory=list, description="Granular test-level comparison records"
    )
    defect_comparisons: List[DefectResolutionDetail] = Field(
        default_factory=list, description="Defect-level comparison records"
    )
    compared_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when comparison was computed",
    )
    notes: Optional[str] = Field(default=None, description="Explanatory notes or inconclusive rationale")


class RepairResponseIngestRequest(BaseModel):
    """Payload to ingest corrected source code for a failed verification run."""

    corrected_code: str = Field(
        min_length=1,
        max_length=500_000,
        description="Corrected Python source code",
    )
    filename: Optional[str] = Field(
        default="solution.py",
        max_length=255,
        description="Filename for the corrected source code (must end in .py)",
    )
    feedback_iteration_id: Optional[str] = Field(
        default=None,
        description="Associated feedback iteration ID (if omitted, uses latest approved iteration)",
    )
    repair_source: RepairSource = Field(
        default=RepairSource.LOCAL_MANUAL,
        description="Provenance of the corrected code (e.g. LOCAL_MANUAL, LOCAL_UPLOAD)",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional engineer notes or description of the fix",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Optional correlation tracing identifier",
    )
    external_repair_job_id: Optional[str] = Field(
        default=None,
        description="Optional external repair job ID (only when genuinely provided by external service)",
    )

    @field_validator("corrected_code")
    @classmethod
    def validate_code_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Corrected source code cannot be empty or whitespace only.")
        if "\0" in v:
            raise ValueError("Corrected source code cannot contain null bytes.")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename_security(cls, v: Optional[str]) -> str:
        if not v or not v.strip():
            return "solution.py"
        cleaned = v.strip()
        # Security: reject path traversal and non-python extensions
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("Filename cannot contain directory separators or path traversal sequences.")
        if not cleaned.endswith(".py"):
            raise ValueError("Only Python source files (.py) are supported for repair ingestion.")
        return cleaned


def is_inconsistent_repair_attempt(data: Any) -> bool:
    """
    Detects if a repair attempt record has an inconsistent lifecycle status:
    Marked REVERIFIED/VERIFIED without a genuine corrected_run_id, and with INCONCLUSIVE comparison.
    """
    if isinstance(data, dict):
        status_raw = data.get("status")
        corr_run_id = data.get("corrected_run_id")
        comp = data.get("comparison")
        if isinstance(comp, dict):
            verdict_raw = comp.get("verdict")
        else:
            verdict_raw = getattr(comp, "verdict", None)
    else:
        status_raw = getattr(data, "status", None)
        corr_run_id = getattr(data, "corrected_run_id", None)
        comp = getattr(data, "comparison", None)
        verdict_raw = getattr(comp, "verdict", None) if comp else None

    status_str = status_raw.value if hasattr(status_raw, "value") else str(status_raw or "").upper()
    verdict_str = verdict_raw.value if hasattr(verdict_raw, "value") else str(verdict_raw or "").upper()

    if status_str in ("REVERIFIED", "VERIFIED"):
        no_run = not corr_run_id or str(corr_run_id).strip().lower() in ("none", "null", "")
        is_inconclusive = verdict_str == "INCONCLUSIVE"
        return no_run and is_inconclusive
    return False


class RepairAttempt(BaseModel):
    """Persisted record representing a repair ingestion and re-verification cycle."""

    model_config = ConfigDict(populate_by_name=True)

    repair_id: str = Field(
        default="",
        description="Canonical repair attempt identifier (rep-...)",
    )
    id: Optional[str] = Field(default=None, description="Alias matching repair_id")
    original_run_id: str = Field(description="Associated original failed verification run ID")
    original_submission_id: str = Field(description="Original submission ID whose code had defects")
    feedback_iteration_id: str = Field(description="Associated feedback iteration ID")
    corrected_submission_id: str = Field(description="ID of the newly created submission holding corrected code")
    corrected_run_id: Optional[str] = Field(
        default=None,
        description="ID of the re-verification run executed against corrected code",
    )
    corrected_code: Optional[str] = Field(default=None, description="Corrected source code artifact")
    corrected_filename: str = Field(default="solution.py", description="Filename of corrected code")
    filename: Optional[str] = Field(default=None, description="Alias for corrected_filename")
    repair_source: RepairSource = Field(default=RepairSource.LOCAL_MANUAL, description="Repair provenance")
    status: RepairResponseStatus = Field(default=RepairResponseStatus.INGESTED, description="Current lifecycle state")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")
    external_repair_job_id: Optional[str] = Field(
        default=None, description="External repair job ID if genuinely provided"
    )
    notes: Optional[str] = Field(default=None, description="Engineer notes regarding this repair attempt")
    comparison: Optional[DefectResolutionComparison] = Field(
        default=None, description="Defect resolution comparison if re-verified"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last update timestamp",
    )

    @model_validator(mode="before")
    @classmethod
    def unify_repair_identifier(cls, data: Any) -> Any:
        if isinstance(data, dict):
            canonical = (
                data.get("repair_id")
                or data.get("id")
                or data.get("_id")
            )
            if not canonical:
                canonical = f"rep-{uuid.uuid4().hex[:12]}"
            data["repair_id"] = str(canonical)
            data["id"] = str(canonical)

            canonical_file = (
                data.get("corrected_filename")
                or data.get("filename")
                or "solution.py"
            )
            data["corrected_filename"] = canonical_file
            data["filename"] = canonical_file
        elif hasattr(data, "repair_id") or hasattr(data, "id"):
            canonical = getattr(data, "repair_id", None) or getattr(data, "id", None)
            if not canonical:
                canonical = f"rep-{uuid.uuid4().hex[:12]}"
            if hasattr(data, "model_dump"):
                d = data.model_dump()
            elif hasattr(data, "__dict__"):
                d = dict(data.__dict__)
            else:
                d = {}
            d["repair_id"] = str(canonical)
            d["id"] = str(canonical)
            canonical_file = (
                d.get("corrected_filename")
                or d.get("filename")
                or "solution.py"
            )
            d["corrected_filename"] = canonical_file
            d["filename"] = canonical_file
            return d
        return data

    @model_validator(mode="after")
    def validate_reverified_lifecycle(self) -> "RepairAttempt":
        """
        Enforce invariant: A repair attempt may enter REVERIFIED only when
        a genuine corrected verification run has completed and its execution evidence is persisted.
        Legacy inconsistent records are permitted for detection and reconciliation.
        """
        if self.status in (RepairResponseStatus.REVERIFIED, RepairResponseStatus.VERIFIED):
            no_run = not self.corrected_run_id or str(self.corrected_run_id).strip().lower() in ("none", "null", "")
            if no_run:
                if not is_inconsistent_repair_attempt(self):
                    raise ValueError(
                        "A repair attempt cannot enter REVERIFIED status without a genuine corrected_run_id."
                    )
        return self

    def model_post_init(self, __context: Any) -> None:
        canonical = self.repair_id or self.id or f"rep-{uuid.uuid4().hex[:12]}"
        self.repair_id = canonical
        self.id = canonical
        canonical_file = self.corrected_filename or self.filename or "solution.py"
        self.corrected_filename = canonical_file
        self.filename = canonical_file


class RepairAttemptResponse(BaseModel):
    """API response model for a repair attempt."""

    model_config = ConfigDict(populate_by_name=True)

    repair_id: str = Field(description="Canonical repair attempt ID")
    id: Optional[str] = Field(default=None, description="Alias matching repair_id")
    original_run_id: str = Field(description="Original verification run ID")
    original_submission_id: str = Field(description="Original submission ID")
    feedback_iteration_id: str = Field(description="Associated feedback iteration ID")
    corrected_submission_id: str = Field(description="Corrected submission ID")
    corrected_run_id: Optional[str] = Field(default=None, description="Re-verification run ID")
    corrected_code: Optional[str] = Field(default=None, description="Corrected source code artifact")
    corrected_filename: str = Field(default="solution.py", description="Filename of corrected code")
    filename: Optional[str] = Field(default=None, description="Alias for corrected_filename")
    repair_source: RepairSource = Field(description="Repair source")
    status: RepairResponseStatus = Field(description="Status of repair attempt")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")
    external_repair_job_id: Optional[str] = Field(default=None, description="External repair job ID")
    notes: Optional[str] = Field(default=None, description="Notes")
    comparison: Optional[DefectResolutionComparison] = Field(default=None, description="Resolution comparison")
    is_inconsistent: bool = Field(
        default=False,
        description="Flag indicating if this record has an inconsistent lifecycle status",
    )
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Update timestamp")

    @model_validator(mode="before")
    @classmethod
    def unify_repair_identifier(cls, data: Any) -> Any:
        inconsistent = is_inconsistent_repair_attempt(data)
        if isinstance(data, dict):
            canonical = (
                data.get("repair_id")
                or data.get("id")
                or data.get("_id")
            )
            if canonical:
                data["repair_id"] = str(canonical)
                data["id"] = str(canonical)

            canonical_file = (
                data.get("corrected_filename")
                or data.get("filename")
                or "solution.py"
            )
            data["corrected_filename"] = canonical_file
            data["filename"] = canonical_file
            data["is_inconsistent"] = inconsistent
        elif hasattr(data, "repair_id") or hasattr(data, "id"):
            canonical = getattr(data, "repair_id", None) or getattr(data, "id", None)
            if hasattr(data, "model_dump"):
                d = data.model_dump()
            elif hasattr(data, "__dict__"):
                d = dict(data.__dict__)
            else:
                d = {}
            if canonical:
                d["repair_id"] = str(canonical)
                d["id"] = str(canonical)
            canonical_file = (
                d.get("corrected_filename")
                or d.get("filename")
                or "solution.py"
            )
            d["corrected_filename"] = canonical_file
            d["filename"] = canonical_file
            d["is_inconsistent"] = inconsistent
            return d
        return data

    def model_post_init(self, __context: Any) -> None:
        canonical = self.repair_id or self.id
        if canonical:
            self.repair_id = canonical
            self.id = canonical
        canonical_file = self.corrected_filename or self.filename or "solution.py"
        self.corrected_filename = canonical_file
        self.filename = canonical_file


class RepairAttemptListResponse(BaseModel):
    """List response for repair attempts associated with a verification run."""

    total: int = Field(description="Total count of repair attempts")
    items: List[RepairAttemptResponse] = Field(description="List of repair attempts")
