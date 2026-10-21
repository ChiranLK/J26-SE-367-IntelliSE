"""
Phase 3C.2 Family 06: API Integrations, Pagination & Gateway (FAM-06-API).
Contains 50 scenarios:
- 12 Functional Bugs
- 6 Security Vulnerabilities
- 5 Performance Bottlenecks
- 5 Regressions
- 5 Integration Defects
- 4 Semantic Drift
- 3 Non-Convergent Repair
- 10 Clean Controls
"""
from typing import List
from scripts.phase3c2_generators.common import ScenarioSpec


def get_family_scenarios() -> List[ScenarioSpec]:
    scenarios: List[ScenarioSpec] = []
    idx = 1

    # -------------------------------------------------------------------------
    # 1. FUNCTIONAL BUGS (12 scenarios)
    # -------------------------------------------------------------------------
    # 1.1 Cursor pagination offset calculation
    clean_code_1 = """def compute_page_offset(page: int, page_size: int) -> int:
    if page < 1:
        page = 1
    return (page - 1) * page_size
"""
    mut_code_1 = """def compute_page_offset(page: int, page_size: int) -> int:
    if page < 1:
        page = 1
    return page * page_size
"""
    oracle_1 = """def run_oracle():
    offset = compute_page_offset(1, 20)
    assert offset == 0, f"Expected offset 0 for page 1, got {offset}"
    offset_p2 = compute_page_offset(2, 20)
    assert offset_p2 == 20, f"Expected offset 20 for page 2, got {offset_p2}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pagination Page Zero Offset Calculation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="ARITHMETIC_OPERAND_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Page 1 begins at offset 0",
        observed_behavior="Multiplies page by page_size directly skipping first page", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Rate limiter token bucket refill
    clean_code_2 = """def consume_rate_limit_token(tokens: int, max_tokens: int) -> tuple:
    if tokens < 1:
        return False, tokens
    return True, tokens - 1
"""
    mut_code_2 = """def consume_rate_limit_token(tokens: int, max_tokens: int) -> tuple:
    if tokens <= 1:
        return False, tokens
    return True, tokens - 1
"""
    oracle_2 = """def run_oracle():
    allowed, rem = consume_rate_limit_token(1, 10)
    assert allowed is True and rem == 0, f"Last available token must be granted, got allowed={allowed}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Token Bucket Boundary Exhaustion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Allow request when exactly 1 token remains",
        observed_behavior="Rejects request when 1 token remains", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Webhook HMAC signature verification
    clean_code_3 = """def verify_webhook_signature(expected_sig: str, received_sig: str) -> bool:
    import hmac
    return hmac.compare_digest(expected_sig, received_sig)
"""
    mut_code_3 = """def verify_webhook_signature(expected_sig: str, received_sig: str) -> bool:
    return expected_sig != received_sig
"""
    oracle_3 = """def run_oracle():
    assert verify_webhook_signature("sig123", "sig123") is True, "Matching signatures must verify"
    assert verify_webhook_signature("sig123", "sig456") is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Webhook HMAC Signature Comparison Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_INVERSION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Verify matching signature digest",
        observed_behavior="Inverts check rejecting matching signatures", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 API response envelope wrapping
    clean_code_4 = """def wrap_api_response(data: list, total_count: int, success: bool = True) -> dict:
    return {"success": success, "data": data, "meta": {"total": total_count}}
"""
    mut_code_4 = """def wrap_api_response(data: list, total_count: int, success: bool = True) -> dict:
    return {"success": not success, "data": data, "meta": {"total": total_count}}
"""
    oracle_4 = """def run_oracle():
    res = wrap_api_response(["item"], 1, True)
    assert res["success"] is True, f"Expected success=True, got {res['success']}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Envelope Success Boolean Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="BOOLEAN_INVERSION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Preserve caller success flag",
        observed_behavior="Inverts success flag in response payload", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Query parameter whitelist filtering
    clean_code_5 = """def filter_query_parameters(params: dict, allowed_keys: set) -> dict:
    return {k: v for k, v in params.items() if k in allowed_keys}
"""
    mut_code_5 = """def filter_query_parameters(params: dict, allowed_keys: set) -> dict:
    return {k: v for k, v in params.items() if k not in allowed_keys}
"""
    oracle_5 = """def run_oracle():
    res = filter_query_parameters({"page": "1", "evil": "true"}, {"page", "limit"})
    assert "page" in res and "evil" not in res, f"Expected only allowed params, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Query Parameter Whitelist Membership Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Retain only whitelisted parameters",
        observed_behavior="Inverts whitelist retaining forbidden parameters", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Exponential retry backoff delay
    clean_code_6 = """def compute_retry_backoff(attempt: int, base_seconds: float = 1.0) -> float:
    return base_seconds * (2 ** (attempt - 1))
"""
    mut_code_6 = """def compute_retry_backoff(attempt: int, base_seconds: float = 1.0) -> float:
    return base_seconds * (2 * (attempt - 1))
"""
    oracle_6 = """def run_oracle():
    delay = compute_retry_backoff(4, 1.0)
    assert delay == 8.0, f"Expected 2^3 = 8.0s backoff for attempt 4, got {delay}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Exponential Backoff Operator Error", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Calculate power of 2 for exponential backoff",
        observed_behavior="Multiplies by 2 giving linear backoff", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 HTTP status code range classifier
    clean_code_7 = """def is_successful_status(status_code: int) -> bool:
    return 200 <= status_code < 300
"""
    mut_code_7 = """def is_successful_status(status_code: int) -> bool:
    return 200 < status_code < 300
"""
    oracle_7 = """def run_oracle():
    assert is_successful_status(200) is True, "HTTP 200 OK must be considered successful"
    assert is_successful_status(204) is True
    assert is_successful_status(404) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="HTTP 200 Status Code Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Inclusive check for 200 status code",
        observed_behavior="Strict inequality rejects HTTP 200 OK", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Idempotency key expiration check
    clean_code_8 = """def is_idempotency_key_valid(created_at: int, current_time: int, ttl: int = 3600) -> bool:
    return (current_time - created_at) <= ttl
"""
    mut_code_8 = """def is_idempotency_key_valid(created_at: int, current_time: int, ttl: int = 3600) -> bool:
    return (created_at - current_time) <= ttl
"""
    oracle_8 = """def run_oracle():
    assert is_idempotency_key_valid(1000, 2000, 3600) is True, "1000s elapsed is within 3600s TTL"
    assert is_idempotency_key_valid(1000, 5000, 3600) is False, "4000s elapsed must be expired"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Idempotency TTL Timestamp Subtraction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OPERAND_SUBTRACTION_INVERSION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Subtract created_at from current_time",
        observed_behavior="Subtracts current_time from created_at", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Route path parameter matching
    clean_code_9 = """def match_route_path(registered_route: str, incoming_path: str) -> bool:
    return registered_route.rstrip("/") == incoming_path.rstrip("/")
"""
    mut_code_9 = """def match_route_path(registered_route: str, incoming_path: str) -> bool:
    return registered_route == incoming_path
"""
    oracle_9 = """def run_oracle():
    assert match_route_path("/api/v1/users/", "/api/v1/users") is True, "Trailing slash should match route"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Trailing Slash Route Normalization", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SANITIZATION_OMISSION", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Normalize trailing slashes before route comparison",
        observed_behavior="Strict equality fails on trailing slashes", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Payload content-length limit validator
    clean_code_10 = """def validate_payload_size(content_length: int, max_bytes: int = 1048576) -> bool:
    return 0 <= content_length <= max_bytes
"""
    mut_code_10 = """def validate_payload_size(content_length: int, max_bytes: int = 1048576) -> bool:
    return 0 <= content_length < max_bytes
"""
    oracle_10 = """def run_oracle():
    assert validate_payload_size(1048576, 1048576) is True, "Exact 1MB limit must be allowed"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payload Size Upper Limit Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Allow exact maximum byte length",
        observed_behavior="Rejects payload matching exact byte ceiling", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 API request timeout duration clamp
    clean_code_11 = """def clamp_timeout_seconds(requested_timeout: float, min_val: float = 1.0, max_val: float = 30.0) -> float:
    return max(min_val, min(requested_timeout, max_val))
"""
    mut_code_11 = """def clamp_timeout_seconds(requested_timeout: float, min_val: float = 1.0, max_val: float = 30.0) -> float:
    return min(min_val, max(requested_timeout, max_val))
"""
    oracle_11 = """def run_oracle():
    t = clamp_timeout_seconds(10.0, 1.0, 30.0)
    assert t == 10.0, f"Expected 10.0 within [1, 30], got {t}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Timeout Clamping Min-Max Order", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Clamp value within [min, max]",
        observed_behavior="Inverts min/max clamp functions", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Header authorization scheme parser
    clean_code_12 = """def parse_auth_scheme(header_val: str) -> str:
    parts = header_val.strip().split()
    return parts[0].upper() if parts else ""
"""
    mut_code_12 = """def parse_auth_scheme(header_val: str) -> str:
    parts = header_val.strip().split()
    return parts[-1].upper() if parts else ""
"""
    oracle_12 = """def run_oracle():
    scheme = parse_auth_scheme("Bearer token_xyz")
    assert scheme == "BEARER", f"Expected scheme 'BEARER', got '{scheme}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Auth Header Scheme Token Index", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INDEX_POSITION_SUBSTITUTION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Extract first token as scheme",
        observed_behavior="Extracts last token instead of scheme", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in REST dynamic filter builder
    clean_sec_1 = """def build_filter_query(db_cursor, field: str, value: str):
    allowed_fields = {"status", "category", "author"}
    if field not in allowed_fields:
        raise ValueError("Invalid field")
    query = f"SELECT id, name FROM items WHERE {field} = ?"
    db_cursor.execute(query, (value,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def build_filter_query(db_cursor, field: str, value: str):
    query = f"SELECT id, name FROM items WHERE {field} = '{value}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockApiCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockApiCur()
    build_filter_query(cur, "status", "active' OR 1=1--")
    assert cur.params is not None, "Query must use parameterized values"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="REST Filter SQL Parameterization", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized query with field whitelist",
        observed_behavior="Unsanitized string interpolation allows SQL injection", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in cURL API tester
    clean_sec_2 = """import subprocess
def execute_curl_probe(target_url: str):
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        raise ValueError("Invalid URL")
    subprocess.run(["curl", "-I", target_url], check=True)
"""
    mut_sec_2 = """import subprocess
def execute_curl_probe(target_url: str):
    subprocess.run(f"curl -I {target_url}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(execute_curl_probe)
    assert "shell=True" not in src, "Must not execute curl with shell=True"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="cURL Probe Shell Command Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Execute curl as list argument without shell",
        observed_behavior="Shell execution with unquoted URL parameter", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in OpenAPI specification file server
    clean_sec_3 = """import os
def load_openapi_spec(version: str) -> str:
    base = "/app/api/specs"
    clean_ver = os.path.basename(version)
    return os.path.join(base, f"{clean_ver}.yaml")
"""
    mut_sec_3 = """import os
def load_openapi_spec(version: str) -> str:
    base = "/app/api/specs"
    return os.path.join(base, f"{version}.yaml")
"""
    oracle_sec_3 = """def run_oracle():
    res = load_openapi_spec("../../etc/passwd")
    assert "/etc/passwd" not in res and ".." not in res, "Path traversal in OpenAPI spec loader"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="OpenAPI Spec Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=3,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize spec version using basename",
        observed_behavior="Relative directory traversal escapes specs directory", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in API error message reflection
    clean_sec_4 = """import html
def build_error_html(param_name: str, message: str) -> str:
    return f"<div class='error'>{html.escape(param_name)}: {html.escape(message)}</div>"
"""
    mut_sec_4 = """def build_error_html(param_name: str, message: str) -> str:
    return f"<div class='error'>{param_name}: {message}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    out = build_error_html("<img src=x onerror=alert(1)>", "error")
    assert "<img" not in out and "&lt;img" in out, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Error HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in error output",
        observed_behavior="Unescaped error message reflection allows XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on internal debug metrics endpoint
    clean_sec_5 = """def fetch_gateway_metrics(api_key: str) -> dict:
    if not api_key:
        raise PermissionError("Unauthenticated metrics request")
    return {"requests_per_sec": 1200}
"""
    mut_sec_5 = """def fetch_gateway_metrics(api_key: str) -> dict:
    return {"requests_per_sec": 1200}
"""
    oracle_sec_5 = """def run_oracle():
    try:
        fetch_gateway_metrics("")
        assert False, "Unauthenticated metrics request must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Gateway Metrics Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify API key before exposing metrics",
        observed_behavior="Allows unauthenticated access to internal metrics", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for API key generation
    clean_sec_6 = """def generate_live_api_key(user_role: str, account_id: str) -> bool:
    return user_role in {"ORG_ADMIN", "SECURITY_ENGINEER"}
"""
    mut_sec_6 = """def generate_live_api_key(user_role: str, account_id: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert generate_live_api_key("READ_ONLY_VIEWER", "ACC-1") is False, "Viewer cannot generate live API keys"
    assert generate_live_api_key("ORG_ADMIN", "ACC-1") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Key Generation Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict API key generation to authorized roles",
        observed_behavior="Grants key generation to any caller", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear search for valid header names
    clean_perf_1 = """def is_supported_header(header: str, supported_headers: set) -> bool:
    return header.lower() in supported_headers
"""
    mut_perf_1 = """def is_supported_header(header: str, supported_headers_list: list) -> bool:
    for h in supported_headers_list:
        if h == header.lower():
            return True
    return False
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_supported_header)
    assert "set" in src and "for " not in src, "Header lookup must use set for O(1) membership without loops"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Supported Headers Set Membership Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) set membership check",
        observed_behavior="O(N) linear list iteration", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic query string parameter deduplication
    clean_perf_2 = """def deduplicate_query_pairs(pairs: list, seen: set) -> list:
    return [p for p in pairs if p['key'] not in seen]
"""
    mut_perf_2 = """def deduplicate_query_pairs(pairs: list, seen_list: list) -> list:
    res = []
    for p in pairs:
        found = False
        for s in seen_list:
            if p['key'] == s:
                found = True
                break
        if not found:
            res.append(p)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(deduplicate_query_pairs)
    assert "set" in src, "Query pairs deduplication must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Query Parameter Set Deduplication", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based deduplication in O(N)",
        observed_behavior="Nested linear search in O(N*M)", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive path router tree matching
    clean_perf_3 = """def match_nested_route_segments(segments: list, memo=None) -> str:
    if memo is None:
        memo = {}
    key = tuple(segments)
    if key in memo:
        return memo[key]
    if not segments:
        return "/"
    res = "/" + "/".join(segments)
    memo[key] = res
    return res
"""
    mut_perf_3 = """def match_nested_route_segments(segments: list, memo=None) -> str:
    if not segments:
        return "/"
    return "/" + "/".join(segments)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(match_nested_route_segments)
    assert "memo" in src and "memo[" in src, "Nested route matching must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Nested Route Segment Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized segment serialization",
        observed_behavior="Unmemoized segment parsing", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in JSON query string serializer
    clean_perf_4 = """def serialize_query_string(params: dict) -> str:
    parts = []
    for k, v in params.items():
        parts.append(f"{k}={v}")
    return "&".join(parts)
"""
    mut_perf_4 = """def serialize_query_string(params: dict) -> str:
    res = ""
    for k, v in params.items():
        if res:
            res = res + "&"
        res = res + f"{k}={v}"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(serialize_query_string)
    assert ".join(" in src, "Query serializer must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Query String Buffer Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="List buffer join in O(N)",
        observed_behavior="Repeated string reallocation in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of bearer token header regex
    clean_perf_5 = """import re
_BEARER_RE = re.compile(r"^Bearer\\s+([a-zA-Z0-9_\\-\\.]+)$")
def is_valid_bearer_header(val: str) -> bool:
    return bool(_BEARER_RE.match(val))
"""
    mut_perf_5 = """import re
def is_valid_bearer_header(val: str) -> bool:
    r = re.compile(r"^Bearer\\s+([a-zA-Z0-9_\\-\\.]+)$")
    return bool(r.match(val))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_bearer_header)
    assert "re.compile" not in src, "Bearer regex must be compiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bearer Token Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles pattern inside function", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty endpoint route guard
    clean_reg_1 = """def register_api_route(path: str) -> bool:
    if not path or not path.strip():
        raise ValueError("Route path cannot be empty")
    return True
"""
    mut_reg_1 = """def register_api_route(path: str) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        register_api_route("   ")
        assert False, "Regression: Blank route path must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Blank Route Path Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty or whitespace routes",
        observed_behavior="Accepts blank route path", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative pagination offset
    clean_reg_2 = """def validate_pagination_params(offset: int, limit: int) -> bool:
    if offset < 0 or limit < 1:
        raise ValueError("Invalid pagination parameters")
    return True
"""
    mut_reg_2 = """def validate_pagination_params(offset: int, limit: int) -> bool:
    return True
"""
    oracle_reg_2 = """def run_oracle():
    try:
        validate_pagination_params(-10, 20)
        assert False, "Regression: Negative offset must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Pagination Offset Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative offset parameter",
        observed_behavior="Accepts negative offset", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy route prefix
    clean_reg_3 = """def format_api_endpoint(resource: str) -> str:
    return f"/api/v1/{resource.strip('/')}"
"""
    mut_reg_3 = """def format_api_endpoint(resource: str) -> str:
    return f"/{resource.strip('/')}"
"""
    oracle_reg_3 = """def run_oracle():
    ep = format_api_endpoint("users")
    assert ep == "/api/v1/users", f"Expected /api/v1/users, got {ep}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Version Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include /api/v1/ prefix",
        observed_behavior="Drops /api/v1/ prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in header names
    clean_reg_4 = """def normalize_header_name(header: str) -> str:
    cleaned = header.strip().lower()
    if not cleaned:
        raise ValueError("Empty header")
    return cleaned
"""
    mut_reg_4 = """def normalize_header_name(header: str) -> str:
    return header.lower()
"""
    oracle_reg_4 = """def run_oracle():
    h = normalize_header_name("  Content-Type  ")
    assert h == "content-type", f"Expected 'content-type' without spaces, got '{h}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Header Name Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing header",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on query param dictionary
    clean_reg_5 = """def get_query_param(params: dict, key: str) -> str:
    if params is None:
        return ""
    return str(params.get(key, ""))
"""
    mut_reg_5 = """def get_query_param(params: dict, key: str) -> str:
    return str(params.get(key, ""))
"""
    oracle_reg_5 = """def run_oracle():
    assert get_query_param(None, "sort") == "", "None params dict must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Query Param Dictionary Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None params gracefully",
        observed_behavior="Raises AttributeError on None params", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed pagination response keys
    clean_integ_1 = """def build_pagination_envelope(items: list, page_num: int, total_items: int) -> dict:
    return {"records": items, "current_page": page_num, "total_records": total_items}
"""
    mut_integ_1 = """def build_pagination_envelope(items: list, page_num: int, total_items: int) -> dict:
    return {"data": items, "page": page_num, "count": total_items}
"""
    oracle_integ_1 = """def run_oracle():
    res = build_pagination_envelope([1, 2], 1, 100)
    assert "records" in res and "current_page" in res and "total_records" in res, "Schema expects 'records', 'current_page', 'total_records'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pagination Response Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified pagination keys",
        observed_behavior="Emits renamed keys breaking API client SDK", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dict vs tuple) in rate limit status endpoint
    clean_integ_2 = """def fetch_rate_limit_headers(remaining: int, reset_time: int) -> dict:
    return {"X-RateLimit-Remaining": str(remaining), "X-RateLimit-Reset": str(reset_time)}
"""
    mut_integ_2 = """def fetch_rate_limit_headers(remaining: int, reset_time: int) -> tuple:
    return (str(remaining), str(reset_time))
"""
    oracle_integ_2 = """def run_oracle():
    h = fetch_rate_limit_headers(50, 1700000000)
    assert isinstance(h, dict) and "X-RateLimit-Remaining" in h, "Consumer expects header dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Rate Limit Headers Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to HTTP headers mapping",
        observed_behavior="Returns plain tuple", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing Content-Type header in response dispatcher
    clean_integ_3 = """def build_json_response_headers() -> dict:
    return {"Content-Type": "application/json", "X-Content-Type-Options": "nosniff"}
"""
    mut_integ_3 = """def build_json_response_headers() -> dict:
    return {"X-Content-Type-Options": "nosniff"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_json_response_headers()
    assert "Content-Type" in h and h["Content-Type"] == "application/json", "Response headers must specify application/json"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Response Content-Type Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_REQUIRED_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include Content-Type: application/json",
        observed_behavior="Omits Content-Type header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in cache-control last-modified
    clean_integ_4 = """def format_http_last_modified(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_http_last_modified(year: int, month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_http_last_modified(2026, 9, 15)
    assert d == "2026-09-15", f"API date standard requires YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="HTTP Date Serialization Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 HTTP method casing mismatch in routing client
    clean_integ_5 = """def serialize_http_method(method: str) -> str:
    return method.strip().upper()
"""
    mut_integ_5 = """def serialize_http_method(method: str) -> str:
    return method.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_http_method("post") == "POST", "HTTP method must be uppercase"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="HTTP Method Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase HTTP method",
        observed_behavior="Emits lowercase HTTP method", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened rate limit check: omitting IP quota assertion
    clean_drift_1 = """def verify_request_rate_limits(user_quota_ok: bool, ip_quota_ok: bool) -> bool:
    return user_quota_ok and ip_quota_ok
"""
    mut_drift_1 = """def verify_request_rate_limits(user_quota_ok: bool, ip_quota_ok: bool) -> bool:
    # Drift: loosened requirement to only check user quota, ignoring IP limit
    return user_quota_ok
"""
    oracle_drift_1 = """def run_oracle():
    assert verify_request_rate_limits(True, False) is False, "Drift: Failed IP quota must reject request"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Rate Limit IP Quota Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both user and IP quotas",
        observed_behavior="Loosens check allowing exceeded IP quotas to pass", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping pagination max limit guard
    clean_drift_2 = """def clamp_page_limit(requested_limit: int, max_limit: int = 100) -> int:
    return min(requested_limit, max_limit)
"""
    mut_drift_2 = """def clamp_page_limit(requested_limit: int, max_limit: int = 100) -> int:
    # Drift: upper bound clamp removed
    return requested_limit
"""
    oracle_drift_2 = """def run_oracle():
    res = clamp_page_limit(5000, 100)
    assert res == 100, f"Drift: Requested 5000 items must be clamped to 100, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pagination Page Size Ceiling Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Cap requested limit at max ceiling",
        observed_behavior="Silently drops limit cap allowing unbounded queries", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum request body size invariant removal
    clean_drift_3 = """def validate_request_body_length(size_bytes: int, max_bytes: int = 1000000) -> bool:
    if size_bytes > max_bytes:
        return False
    return True
"""
    mut_drift_3 = """def validate_request_body_length(size_bytes: int, max_bytes: int = 1000000) -> bool:
    # Drift: body length limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_request_body_length(5000000, 1000000) is False, "Drift: 5MB body exceeds 1MB limit"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Request Body Size Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce request size ceiling",
        observed_behavior="Unconditionally permits unbounded body size", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in rate limit reset timestamp
    clean_drift_4 = """def calculate_reset_epoch(start_time: float, window_sec: float) -> int:
    from decimal import Decimal, ROUND_HALF_UP
    dec = Decimal(str(start_time)) + Decimal(str(window_sec))
    return int(dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def calculate_reset_epoch(start_time: float, window_sec: float) -> int:
    # Drift: integer truncation of window before addition
    return int(start_time) + int(window_sec)
"""
    oracle_drift_4 = """def run_oracle():
    res = calculate_reset_epoch(100.4, 0.7)
    assert res == 101, f"Expected 101 from 101.1, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Rate Limit Window Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate sum and decimal round",
        observed_behavior="Premature integer truncation of components", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting rate limit window policy requirements
    clean_conv_1 = """def check_rate_limit_window(seconds: int) -> bool:
    # Harmonized policy: window allowed between 60 and 3600 seconds
    return 60 <= seconds <= 3600
"""
    mut_conv_1 = """def check_rate_limit_window(seconds: int) -> bool:
    # Invariant conflict: Policy A requires seconds < 30, Policy B requires seconds > 120
    return seconds < 30 and seconds > 120
"""
    oracle_conv_1 = """def run_oracle():
    assert check_rate_limit_window(300) is True, "Harmonized rule permits 300s"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Rate Limit Window Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid window range",
        observed_behavior="Mutually contradictory rules (seconds < 30 AND seconds > 120)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: pagination limit threshold operator
    clean_conv_2 = """def evaluate_page_capacity(count: int, max_page: int) -> str:
    if count >= max_page:
        return "PAGE_FULL"
    return "HAS_ROOM"
"""
    mut_conv_2 = """def evaluate_page_capacity(count: int, max_page: int) -> str:
    if count > max_page:
        return "PAGE_FULL"
    return "HAS_ROOM"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_page_capacity(50, 50) == "PAGE_FULL", "Exact capacity must be PAGE_FULL"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Page Capacity Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary marks page as full",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in webhook dispatch status
    clean_conv_3 = """def advance_webhook_status(state: str) -> str:
    flow = {"QUEUED": "DISPATCHING", "DISPATCHING": "DELIVERED", "DELIVERED": "DELIVERED"}
    return flow.get(state, "QUEUED")
"""
    mut_conv_3 = """def advance_webhook_status(state: str) -> str:
    # Circular loop between DISPATCHING and QUEUED
    flow = {"QUEUED": "DISPATCHING", "DISPATCHING": "QUEUED", "DELIVERED": "DELIVERED"}
    return flow.get(state, "QUEUED")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_webhook_status(advance_webhook_status("QUEUED"))
    assert res == "DELIVERED", "Webhook progression must reach terminal DELIVERED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Webhook Dispatch State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to DELIVERED",
        observed_behavior="Infinite oscillation between QUEUED and DISPATCHING",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def api_clean_routine_{c_idx}(req_val: int) -> int:
    # Clean control {c_idx}: verified API calculation helper with boundary guard
    if req_val < 0:
        return 0
    return (req_val * 4) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = api_clean_routine_{c_idx}(25)
    assert res == 100 + {c_idx}, f"Expected {{100 + {c_idx}}}, got {{res}}"
    assert api_clean_routine_{c_idx}(-5) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"API Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified API calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
