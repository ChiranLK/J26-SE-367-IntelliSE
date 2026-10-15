import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.feedback import (
    Component3StatusResponse,
    TechnicalFeedbackPayload,
)


class Component3ClientError(Exception):
    """Base exception for all Component 3 outbound client errors."""
    pass


class Component3ConfigError(Component3ClientError):
    """Raised when Component 3 integration is misconfigured or disabled."""
    pass


class Component3ConnectionError(Component3ClientError):
    """Raised when network connection to Component 3 fails."""
    pass


class Component3TimeoutError(Component3ClientError):
    """Raised when request to Component 3 times out."""
    pass


class Component3ResponseError(Component3ClientError):
    """Raised when Component 3 returns an unexpected or error HTTP response."""

    def __init__(self, message: str, status_code: int, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class Component3DispatchResult:
    """Result of an outbound dispatch attempt to Component 3."""
    success: bool
    acknowledged: bool
    job_id: Optional[str]
    status_code: Optional[int]
    message: str
    error_category: Optional[str]
    correlation_id: str
    dispatch_attempt_id: str


class Component3Client:
    """
    Dedicated outbound HTTP client for communicating technical feedback to Component 3.
    Enforces strict payload sanitization (zero XAI narratives), correlation tracking,
    timeouts, and safe fail-closed behavior when Component 3 is not ready.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        feedback_endpoint: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        connect_timeout_seconds: Optional[float] = None,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = (base_url or settings.COMPONENT_3_BASE_URL).rstrip("/")
        self.feedback_endpoint = feedback_endpoint or settings.COMPONENT_3_FEEDBACK_ENDPOINT
        self.timeout_seconds = timeout_seconds or settings.COMPONENT_3_TIMEOUT_SECONDS
        self.connect_timeout_seconds = connect_timeout_seconds or settings.COMPONENT_3_CONNECT_TIMEOUT_SECONDS
        self.enabled = enabled if enabled is not None else settings.COMPONENT_3_ENABLED
        self.api_key = api_key or settings.COMPONENT_3_API_KEY
        self._external_client = http_client

    def get_status(self) -> Component3StatusResponse:
        """
        Returns integration readiness and connectivity status for Component 3.
        Informs the frontend whether live dispatch can be attempted.
        """
        is_configured = bool(self.base_url and self.base_url.startswith(("http://", "https://")))
        
        # Component 3 discovery verified that C3 currently provides only /health and /validate-input.
        # Its feedback receiver is under active development.
        contract_status = "ACTIVE" if self.enabled else "UNDER_DEVELOPMENT"
        dispatch_allowed = bool(self.enabled and is_configured)

        if not self.enabled:
            reason = (
                "Component 3 technical feedback receiver is currently under development (provisional C1/C2 only). "
                "Outbound delivery remains safely disabled until Component 3 exposes a verified correction feedback endpoint."
            )
        elif not is_configured:
            reason = "Component 3 base URL is not configured."
        else:
            reason = f"Component 3 integration is enabled at {self.base_url}{self.feedback_endpoint}."

        return Component3StatusResponse(
            configured=is_configured,
            enabled=self.enabled,
            base_url=self.base_url,
            endpoint=self.feedback_endpoint,
            contract_status=contract_status,
            dispatch_allowed=dispatch_allowed,
            reason=reason,
        )

    def prepare_sanitized_payload(self, payload: TechnicalFeedbackPayload) -> Dict[str, Any]:
        """
        Prepares a strictly sanitized dictionary representation of TechnicalFeedbackPayload.
        Guarantees that NO human-facing XAI narratives, explanations, recommendations,
        or internal secrets are ever included in the dispatched payload.
        """
        # Forbidden keys that must NEVER leak to Component 3
        forbidden_keys = {
            "xai_explanation",
            "summary",
            "what_failed",
            "confirmed_observations",
            "evidence_based_interpretation",
            "recommendation",
            "suggested_investigations",
            "explanation_method",
            "provider",
        }

        if hasattr(payload, "model_dump"):
            raw_dict = payload.model_dump(mode="json")
        elif isinstance(payload, dict):
            raw_dict = payload.copy()
        else:
            raw_dict = dict(payload)

        for key in forbidden_keys:
            if key in raw_dict:
                del raw_dict[key]

        # Allowed structured technical fields according to contract
        sanitized = {
            "feedback_id": raw_dict.get("feedback_id"),
            "verification_run_id": raw_dict.get("verification_run_id"),
            "submission_id": raw_dict.get("submission_id"),
            "verification_status": raw_dict.get("verification_status"),
            "affected_files": raw_dict.get("affected_files", []),
            "failed_tests": raw_dict.get("failed_tests", []),
            "failed_assertions": raw_dict.get("failed_assertions", []),
            "value_comparisons": raw_dict.get("value_comparisons", []),
            "error_logs": raw_dict.get("error_logs", []),
            "test_failure_details": raw_dict.get("test_failure_details", []),
            "defect_ids": raw_dict.get("defect_ids", []),
            "evidence_references": raw_dict.get("evidence_references", {}),
            "generated_at": raw_dict.get("generated_at"),
            "schema_version": raw_dict.get("schema_version", "1.0"),
        }
        if "defects" in raw_dict:
            sanitized["defects"] = raw_dict["defects"]
        return sanitized

    async def dispatch_feedback(
        self,
        payload: TechnicalFeedbackPayload,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Component3DispatchResult:
        """
        Transmits a validated, sanitized technical feedback payload to Component 3.
        Safe fail-closed: if integration is not enabled, fails gracefully with clear rationale.
        """
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        dispatch_id = idempotency_key or f"disp-{uuid.uuid4().hex[:12]}"

        # 1. Check if Component 3 is enabled
        if not self.enabled:
            logger.info(
                "Component 3 dispatch skipped: integration is disabled (contract under development). "
                "Correlation ID: %s, Dispatch ID: %s",
                corr_id,
                dispatch_id,
            )
            return Component3DispatchResult(
                success=False,
                acknowledged=False,
                job_id=None,
                status_code=None,
                message=(
                    "Component 3 technical feedback receiver is currently under development. "
                    "Actual HTTP delivery was not attempted because COMPONENT_3_ENABLED is False."
                ),
                error_category="COMPONENT_3_DISABLED",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )

        # 2. Strict sanitization of payload
        body = self.prepare_sanitized_payload(payload)
        url = f"{self.base_url}{self.feedback_endpoint}"

        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": corr_id,
            "Idempotency-Key": dispatch_id,
            "User-Agent": "INTELISE-Component-4-VerificationEngine/0.1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=self.connect_timeout_seconds,
        )

        try:
            if self._external_client:
                response = await self._external_client.post(
                    url, json=body, headers=headers, timeout=timeout
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url, json=body, headers=headers, timeout=timeout
                    )

            # Check HTTP outcome
            status_code = response.status_code
            if status_code in (200, 201, 202):
                job_id = None
                try:
                    res_json = response.json()
                    job_id = res_json.get("job_id") or res_json.get("correction_job_id") or res_json.get("task_id")
                except Exception:
                    pass

                logger.info(
                    "Component 3 successfully acknowledged feedback %s (status %d, job_id=%s). Corr: %s",
                    payload.feedback_id,
                    status_code,
                    job_id,
                    corr_id,
                )
                return Component3DispatchResult(
                    success=True,
                    acknowledged=True,
                    job_id=job_id,
                    status_code=status_code,
                    message=f"Component 3 confirmed receipt of feedback (HTTP {status_code}).",
                    error_category=None,
                    correlation_id=corr_id,
                    dispatch_attempt_id=dispatch_id,
                )
            else:
                resp_text = response.text[:300]
                logger.warning(
                    "Component 3 returned non-success HTTP status %d: %s. Corr: %s",
                    status_code,
                    resp_text,
                    corr_id,
                )
                return Component3DispatchResult(
                    success=False,
                    acknowledged=False,
                    job_id=None,
                    status_code=status_code,
                    message=f"Component 3 rejected feedback with HTTP {status_code}: {resp_text}",
                    error_category="COMPONENT_3_ERROR_RESPONSE",
                    correlation_id=corr_id,
                    dispatch_attempt_id=dispatch_id,
                )

        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as exc:
            logger.error("Component 3 timeout on dispatch: %s. Corr: %s", exc, corr_id)
            return Component3DispatchResult(
                success=False,
                acknowledged=False,
                job_id=None,
                status_code=None,
                message=f"Connection or read timeout while attempting dispatch to Component 3: {exc}",
                error_category="TIMEOUT",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )
        except httpx.ConnectError as exc:
            logger.error("Component 3 connection refused/unreachable: %s. Corr: %s", exc, corr_id)
            return Component3DispatchResult(
                success=False,
                acknowledged=False,
                job_id=None,
                status_code=None,
                message=f"Cannot establish connection to Component 3 at {url}: {exc}",
                error_category="CONNECTION_ERROR",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )
        except Exception as exc:
            logger.error("Unexpected error during Component 3 dispatch: %s. Corr: %s", exc, corr_id)
            return Component3DispatchResult(
                success=False,
                acknowledged=False,
                job_id=None,
                status_code=None,
                message=f"Unexpected error communicating with Component 3: {exc}",
                error_category="CLIENT_ERROR",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )
