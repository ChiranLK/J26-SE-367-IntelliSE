import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class DeliveryConfirmationCreate(BaseModel):
    """Payload to confirm successful downstream delivery of a verified artifact."""

    artifact_version: Optional[str] = Field(
        default=None,
        description="Exact submission ID or artifact version being confirmed. Must match the verification run's submission_id.",
    )
    delivery_channel: str = Field(
        default="user_workspace",
        description="Deployment target or channel (e.g., 'user_workspace', 'production', 'staging', 'ci_cd_deployment')",
    )
    confirmed_by: str = Field(
        default="delivery_orchestrator",
        description="Entity or agent confirming delivery (e.g., 'release_gate', 'human_operator', 'mock_simulation')",
    )
    is_simulation: bool = Field(
        default=False,
        description="Explicit flag indicating whether this confirmation is a simulated/mock delivery for testing or evaluation.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operational or deployment notes regarding the delivery.",
    )


class DeliveryConfirmation(BaseModel):
    """Immutable audit record confirming successful downstream delivery of a verified software artifact."""

    delivery_id: str = Field(
        default_factory=lambda: f"dlv-{uuid.uuid4().hex[:12]}",
        description="Unique delivery confirmation identifier",
    )
    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Exact code submission artifact version confirmed delivered")
    artifact_checksum_sha256: Optional[str] = Field(
        default=None,
        description="SHA-256 digest of delivered code artifact for cryptographic provenance",
    )
    delivery_channel: str = Field(
        default="user_workspace",
        description="Target deployment environment or delivery channel",
    )
    confirmed_by: str = Field(
        default="delivery_orchestrator",
        description="Entity or agent that recorded confirmation",
    )
    delivered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when delivery was confirmed",
    )
    is_delivered: bool = Field(
        default=True,
        description="True if delivery succeeded and artifact is deployed/available",
    )
    is_simulation: bool = Field(
        default=False,
        description="True if confirmation was generated in a simulated testing environment",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Deployment notes or metadata",
    )
