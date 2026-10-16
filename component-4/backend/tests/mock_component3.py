"""
Mock Component 3 Receiver for Isolated Testing

Provides an in-memory HTTP transport simulating Component 3's feedback receiver
across diverse network, authentication, validation, and failure scenarios.
This mock exists strictly for automated integration and regression testing and
is never mounted or active in production environments.
"""

from typing import Any, Dict, List, Optional
import json
import httpx


class MockComponent3Receiver:
    """
    In-memory mock receiver that handles outbound requests from Component 4
    and generates deterministic responses based on configured test scenarios.
    """

    def __init__(
        self,
        scenario: str = "SUCCESS",
        expected_api_key: Optional[str] = "valid-test-key",
        transient_failures_allowed: int = 1,
    ):
        self.scenario = scenario
        self.expected_api_key = expected_api_key
        self.transient_failures_allowed = transient_failures_allowed
        self.call_count: int = 0
        self.received_requests: List[Dict[str, Any]] = []

    async def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Processes an outbound dispatch request deterministically."""
        self.call_count += 1
        body = None
        try:
            body = json.loads(request.content.decode("utf-8"))
        except Exception:
            body = None

        req_record = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
            "attempt": self.call_count,
        }
        self.received_requests.append(req_record)

        # 1. Timeout simulation
        if self.scenario == "TIMEOUT":
            raise httpx.ReadTimeout("Mock Component 3 simulated transmission timeout")

        if self.scenario == "CONNECT_TIMEOUT":
            raise httpx.ConnectTimeout("Mock Component 3 simulated connection timeout")

        if self.scenario == "CONNECTION_ERROR":
            raise httpx.ConnectError("Mock Component 3 simulated connection refused")

        # 2. Authentication check
        auth_header = request.headers.get("authorization", "")
        if self.scenario == "AUTH_FAIL":
            return httpx.Response(
                status_code=401,
                json={"detail": "Unauthorized: invalid or missing API key."},
            )

        if self.expected_api_key:
            expected_auth = f"Bearer {self.expected_api_key}"
            if auth_header != expected_auth:
                return httpx.Response(
                    status_code=401,
                    json={"detail": "Unauthorized: API key mismatch."},
                )

        # 3. Validation rejection simulation
        if self.scenario == "VALIDATION_FAIL":
            return httpx.Response(
                status_code=422,
                json={"detail": "Unprocessable Entity: invalid technical feedback schema."},
            )

        # 4. Idempotency conflict simulation (409)
        if self.scenario == "DUPLICATE_409":
            return httpx.Response(
                status_code=409,
                json={"detail": "Conflict: duplicate feedback package already processing."},
            )

        # 5. Missing job_id acknowledgment simulation
        if self.scenario == "INVALID_ACKNOWLEDGMENT":
            return httpx.Response(
                status_code=200,
                json={"status": "RECEIVED", "message": "Missing job_id field"},
            )

        # 6. Transient server error simulation (e.g. 503 on first N calls, then 200)
        if self.scenario == "TRANSIENT_503":
            if self.call_count <= self.transient_failures_allowed:
                return httpx.Response(
                    status_code=503,
                    json={"detail": "Service Temporarily Unavailable: container warming up."},
                )
            # Recover on subsequent attempt
            return httpx.Response(
                status_code=200,
                json={
                    "job_id": f"c3-job-transient-{self.call_count}",
                    "status": "RECEIVED",
                    "correlation_id": request.headers.get("x-correlation-id"),
                    "message": "Technical feedback acknowledged after transient retry.",
                },
            )

        # 7. Persistent server failure (exhaustion)
        if self.scenario == "PERSISTENT_503":
            return httpx.Response(
                status_code=503,
                json={"detail": "Service Unavailable: persistent downstream failure."},
            )

        # 8. Success scenario (HTTP 200 / 201)
        job_id = f"c3-job-success-{self.call_count}"
        return httpx.Response(
            status_code=200,
            json={
                "job_id": job_id,
                "status": "RECEIVED",
                "correlation_id": request.headers.get("x-correlation-id"),
                "message": "Technical feedback accepted for automated repair loop.",
            },
        )


def create_mock_transport_client(receiver: MockComponent3Receiver) -> httpx.AsyncClient:
    """Creates an httpx.AsyncClient backed by MockComponent3Receiver."""
    transport = httpx.MockTransport(receiver.handle_request)
    return httpx.AsyncClient(transport=transport, base_url="http://mock-component-3.test")
