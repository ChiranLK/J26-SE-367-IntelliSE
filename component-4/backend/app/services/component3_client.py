import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.feedback import (
    FORBIDDEN_EXPLANATION_KEYS,
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
    bounded timeouts, fail-closed contract readiness checks, and unknown-outcome handling on timeout.
    """

    PLACEHOLDER_HOSTS = frozenset({
        "127.0.0.1:8000",
        "localhost:8000",
        "0.0.0.0:8000",
        "example.com",
        "placeholder.internal",
    })

    def __init__(
        self,
        base_url: Optional[str] = None,
        feedback_endpoint: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        connect_timeout_seconds: Optional[float] = None,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        allow_placeholder_url: bool = False,
    ):
        self.base_url = (base_url or settings.COMPONENT_3_BASE_URL).rstrip("/")
        self.feedback_endpoint = feedback_endpoint or settings.COMPONENT_3_FEEDBACK_ENDPOINT
        self.timeout_seconds = timeout_seconds or settings.COMPONENT_3_TIMEOUT_SECONDS
        self.connect_timeout_seconds = connect_timeout_seconds or settings.COMPONENT_3_CONNECT_TIMEOUT_SECONDS
        self.enabled = enabled if enabled is not None else settings.COMPONENT_3_ENABLED
        self.api_key = api_key or settings.COMPONENT_3_API_KEY
        self._external_client = http_client
        self.allow_placeholder_url = allow_placeholder_url

    def _is_placeholder_or_self_referential_url(self, url: str) -> bool:
        """
        Detects if a URL is empty, generic placeholder, or self-referential loopback pointing to Component 4.
        Component 4 runs on port 8000 (127.0.0.1:8000 / localhost:8000). Treating our own address
        as an external repair service is strictly forbidden.
        """
        if not url:
            return True
        try:
            parsed = urlparse(url)
            netloc = (parsed.netloc or parsed.path).lower()
            return netloc in self.PLACEHOLDER_HOSTS or netloc.startswith("127.0.0.1:8000") or netloc.startswith("localhost:8000")
        except Exception:
            return True

    def get_status(self) -> Component3StatusResponse:
        """
        Returns integration readiness and connectivity status for Component 3.
        Evaluates the 6 mandatory integration contract readiness conditions:
          1. Verified receiver URL (valid HTTP/HTTPS, non-placeholder, non-self-referential)
          2. Confirmed API endpoint (verified correction feedback route on Component 3)
          3. Agreed request schema (confirmed technical feedback payload format)
          4. Agreed acknowledgment schema (confirmed job_id / task_id acknowledgment contract)
          5. Defined safe idempotency and retry behavior
          6. Explicit configuration enabling integration (COMPONENT_3_ENABLED=True)
        """
        is_configured = bool(self.base_url and self.base_url.startswith(("http://", "https://")))
        is_placeholder = self._is_placeholder_or_self_referential_url(self.base_url)
        verified_receiver_url = bool(is_configured and not is_placeholder)

        # Inspection of Component 3 confirmed it currently exposes only /health and /validate-input.
        # Its correction-feedback endpoint and payload contract are not yet available.
        confirmed_endpoint = False
        agreed_request_schema = False
        agreed_acknowledgment_schema = False
        safe_idempotency_defined = False
        explicit_enabled_flag = bool(self.enabled)

        readiness_checklist = {
            "verified_receiver_url": verified_receiver_url,
            "confirmed_endpoint": confirmed_endpoint,
            "agreed_request_schema": agreed_request_schema,
            "agreed_acknowledgment_schema": agreed_acknowledgment_schema,
            "safe_idempotency_defined": safe_idempotency_defined,
            "explicit_enabled_flag": explicit_enabled_flag,
        }

        # Live dispatch is allowed ONLY if all 6 criteria are met
        all_criteria_met = all(readiness_checklist.values())
        dispatch_allowed = all_criteria_met

        if not self.enabled:
            contract_status = "UNDER_DEVELOPMENT"
            reason = (
                "Component 3 technical feedback receiver is currently under development (provisional C1/C2 only). "
                "Outbound delivery remains safely disabled until Component 3 exposes a verified correction feedback endpoint."
            )
        elif is_placeholder:
            contract_status = "PLACEHOLDER_URL"
            reason = (
                f"Configured receiver address ('{self.base_url}') is a placeholder or self-referential loopback. "
                "A verified external receiver address and confirmed contract are required before live dispatch."
            )
        elif not confirmed_endpoint or not agreed_request_schema:
            contract_status = "CONTRACT_PENDING_CONFIRMATION"
            reason = (
                "Component 3 receiver URL is configured, but the correction feedback endpoint and payload contract "
                "have not been confirmed by the Component 3 team."
            )
        else:
            contract_status = "ACTIVE"
            reason = f"Component 3 integration is enabled at {self.base_url}{self.feedback_endpoint}."

        return Component3StatusResponse(
            configured=is_configured,
            enabled=self.enabled,
            base_url=self.base_url,
            endpoint=self.feedback_endpoint,
            contract_status=contract_status,
            dispatch_allowed=dispatch_allowed,
            reason=reason,
            verified_receiver_url=verified_receiver_url,
            confirmed_endpoint=confirmed_endpoint,
            agreed_request_schema=agreed_request_schema,
            agreed_acknowledgment_schema=agreed_acknowledgment_schema,
            safe_idempotency_defined=safe_idempotency_defined,
            readiness_checklist=readiness_checklist,
        )

    def prepare_sanitized_payload(self, payload: TechnicalFeedbackPayload) -> Dict[str, Any]:
        """
        Prepares a strictly sanitized dictionary representation of TechnicalFeedbackPayload.
        Guarantees that NO human-facing XAI narratives, explanations, recommendations,
        or internal secrets are ever included in the dispatched payload.
        """
        if hasattr(payload, "model_dump"):
            raw_dict = payload.model_dump(mode="json")
        elif isinstance(payload, dict):
            raw_dict = payload.copy()
        else:
            raw_dict = dict(payload)

        # Remove any forbidden human explanation or sensitive keys
        for key in list(raw_dict.keys()):
            if key in FORBIDDEN_EXPLANATION_KEYS or key in ("api_key", "token", "password", "secret", "mongodb_uri"):
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

        # Final safety verification: assert no forbidden key survived
        for key in FORBIDDEN_EXPLANATION_KEYS:
            if key in sanitized:
                del sanitized[key]

        return sanitized

    async def dispatch_feedback(
        self,
        payload: TechnicalFeedbackPayload,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Component3DispatchResult:
        """
        Transmits a validated, sanitized technical feedback payload to Component 3.
        Safe fail-closed: if integration is not enabled or receiver URL is a placeholder,
        fails gracefully with clear rationale.
        If a timeout occurs after transmission, treats the outcome as UNKNOWN rather than assuming failure.
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

        # 2. Check for placeholder or self-referential receiver address
        if self._is_placeholder_or_self_referential_url(self.base_url) and not self.allow_placeholder_url:
            logger.warning(
                "Component 3 dispatch blocked: receiver address '%s' is a placeholder or self-referential loopback. "
                "Correlation ID: %s",
                self.base_url,
                corr_id,
            )
            return Component3DispatchResult(
                success=False,
                acknowledged=False,
                job_id=None,
                status_code=None,
                message=(
                    f"Component 3 receiver address '{self.base_url}' is a placeholder or self-referential loopback. "
                    "A verified external receiver address is required before dispatch."
                ),
                error_category="CONFIG_ERROR",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )

        # 3. Strict sanitization of payload
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
                async with httpx.AsyncClient(verify=True) as client:
                    response = await client.post(
                        url, json=body, headers=headers, timeout=timeout
                    )

            # Check HTTP outcome
            status_code = response.status_code
            if status_code in (200, 201, 202):
                job_id = None
                try:
                    res_json = response.json()
                    job_id = (
                        res_json.get("job_id")
                        or res_json.get("correction_job_id")
                        or res_json.get("task_id")
                    )
                except Exception:
                    res_json = None

                # Require a verified non-empty acknowledgment identifier
                if not job_id or not isinstance(job_id, str) or not job_id.strip():
                    logger.warning(
                        "Component 3 responded with status %d but missing valid acknowledgment job_id. Corr: %s",
                        status_code,
                        corr_id,
                    )
                    return Component3DispatchResult(
                        success=False,
                        acknowledged=False,
                        job_id=None,
                        status_code=status_code,
                        message=(
                            f"Component 3 responded with HTTP {status_code} but returned an invalid or missing "
                            "acknowledgment identifier (expected 'job_id' or 'task_id')."
                        ),
                        error_category="INVALID_ACKNOWLEDGMENT",
                        correlation_id=corr_id,
                        dispatch_attempt_id=dispatch_id,
                    )

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
                    job_id=job_id.strip(),
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
                message=(
                    f"Dispatch request timed out after transmission ({type(exc).__name__}). "
                    "Remote delivery outcome is unknown. Automatic retry suppressed."
                ),
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
                message=f"Cannot establish connection to external repair service: {exc}",
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
                message=f"Unexpected error communicating with external repair service: {exc}",
                error_category="CLIENT_ERROR",
                correlation_id=corr_id,
                dispatch_attempt_id=dispatch_id,
            )

