"""
Phase 3C.2 Family 04: User Authentication & Access Control (FAM-04-AUTH).
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
    # 1.1 Password minimum length validation (>= vs >)
    clean_code_1 = """def validate_password_length(password: str, min_len: int = 8) -> bool:
    return len(password) >= min_len
"""
    mut_code_1 = """def validate_password_length(password: str, min_len: int = 8) -> bool:
    return len(password) > min_len
"""
    oracle_1 = """def run_oracle():
    assert validate_password_length("12345678", 8) is True, "Exact 8-character password must be accepted"
    assert validate_password_length("1234567", 8) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Length Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Accept passwords meeting exact min length",
        observed_behavior="Rejects passwords meeting exact minimum length", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Account lockout failed attempts threshold
    clean_code_2 = """def is_account_locked(failed_attempts: int, max_allowed: int = 5) -> bool:
    return failed_attempts >= max_allowed
"""
    mut_code_2 = """def is_account_locked(failed_attempts: int, max_allowed: int = 5) -> bool:
    return failed_attempts > max_allowed
"""
    oracle_2 = """def run_oracle():
    assert is_account_locked(5, 5) is True, "5 failed attempts out of 5 must lock account"
    assert is_account_locked(4, 5) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Account Lockout Attempt Threshold", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Lock account at or above max attempts",
        observed_behavior="Allows an additional unauthorized attempt at max limit", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 JWT token expiration timestamp comparison
    clean_code_3 = """def is_token_expired(exp_timestamp: int, current_timestamp: int) -> bool:
    return current_timestamp >= exp_timestamp
"""
    mut_code_3 = """def is_token_expired(exp_timestamp: int, current_timestamp: int) -> bool:
    return current_timestamp < exp_timestamp
"""
    oracle_3 = """def run_oracle():
    assert is_token_expired(100, 150) is True, "Current time 150 > exp 100 is expired"
    assert is_token_expired(200, 150) is False, "Current time 150 < exp 200 is valid"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Token Expiration Temporal Inequality", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_INVERSION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Token expired when current >= expiration",
        observed_behavior="Inverts expiration logic treating active tokens as expired", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Role permission hierarchy check
    clean_code_4 = """def has_sufficient_role(user_role: str, required_role: str) -> bool:
    ranks = {"USER": 1, "MODERATOR": 2, "ADMIN": 3}
    return ranks.get(user_role, 0) >= ranks.get(required_role, 999)
"""
    mut_code_4 = """def has_sufficient_role(user_role: str, required_role: str) -> bool:
    ranks = {"USER": 1, "MODERATOR": 2, "ADMIN": 3}
    return ranks.get(user_role, 0) <= ranks.get(required_role, 999)
"""
    oracle_4 = """def run_oracle():
    assert has_sufficient_role("ADMIN", "MODERATOR") is True, "ADMIN outranks MODERATOR"
    assert has_sufficient_role("USER", "ADMIN") is False, "USER cannot access ADMIN"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Role Rank Hierarchy Relational Check", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="RELATIONAL_OPERATOR_INVERSION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="User rank must be >= required rank",
        observed_behavior="Inverts hierarchy allowing low-privilege users access", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Session inactivity timeout calculation
    clean_code_5 = """def is_session_inactive(last_activity: int, current_time: int, max_idle: int = 1800) -> bool:
    idle_time = current_time - last_activity
    return idle_time > max_idle
"""
    mut_code_5 = """def is_session_inactive(last_activity: int, current_time: int, max_idle: int = 1800) -> bool:
    idle_time = last_activity - current_time
    return idle_time > max_idle
"""
    oracle_5 = """def run_oracle():
    assert is_session_inactive(1000, 3000, 1800) is True, "2000s idle exceeds 1800s timeout"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Session Idle Subtraction Order", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OPERAND_SUBTRACTION_INVERSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Subtract last activity from current time",
        observed_behavior="Subtracts current from last producing negative idle time", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 MFA 6-digit numeric code validator
    clean_code_6 = """def is_valid_mfa_code(code: str) -> bool:
    return len(code) == 6 and code.isdigit()
"""
    mut_code_6 = """def is_valid_mfa_code(code: str) -> bool:
    return len(code) == 6 or code.isdigit()
"""
    oracle_6 = """def run_oracle():
    assert is_valid_mfa_code("123456") is True, "Valid 6 digit code"
    assert is_valid_mfa_code("12345") is False, "5 digit code is invalid"
    assert is_valid_mfa_code("abcdef") is False, "Alphabetic 6-char is invalid"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="MFA Code Boolean Compound Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Require both 6-char length AND all digits",
        observed_behavior="Uses OR accepting non-digit or incorrect length codes", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Bearer token prefix stripping
    clean_code_7 = """def extract_bearer_token(header_val: str) -> str:
    prefix = "Bearer "
    if header_val.startswith(prefix):
        return header_val[len(prefix):].strip()
    return ""
"""
    mut_code_7 = """def extract_bearer_token(header_val: str) -> str:
    prefix = "Bearer "
    if header_val.startswith(prefix):
        return header_val.strip()
    return ""
"""
    oracle_7 = """def run_oracle():
    tok = extract_bearer_token("Bearer secret_jwt_123")
    assert tok == "secret_jwt_123", f"Expected 'secret_jwt_123' stripped, got '{tok}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bearer Header Prefix Stripping", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="SLICE_OMISSION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Strip 'Bearer ' prefix returning raw token",
        observed_behavior="Leaves 'Bearer ' prefix intact", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Password complexity symbol requirement
    clean_code_8 = """def has_required_symbol(password: str) -> bool:
    symbols = set("!@#$%^&*()-_=+")
    return any(c in symbols for c in password)
"""
    mut_code_8 = """def has_required_symbol(password: str) -> bool:
    symbols = set("!@#$%^&*()-_=+")
    return all(c in symbols for c in password)
"""
    oracle_8 = """def run_oracle():
    assert has_required_symbol("P@ssword1") is True, "Contains '@' symbol"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Symbol Any vs All Check", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="BUILTIN_FUNCTION_REPLACEMENT", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Require at least one symbol using any()",
        observed_behavior="Uses all() requiring every character to be a symbol", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Refresh token rotation sequence increment
    clean_code_9 = """def rotate_refresh_token(current_seq: int) -> int:
    return current_seq + 1
"""
    mut_code_9 = """def rotate_refresh_token(current_seq: int) -> int:
    return current_seq - 1
"""
    oracle_9 = """def run_oracle():
    new_seq = rotate_refresh_token(5)
    assert new_seq == 6, f"Expected 6, got {new_seq}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Token Rotation Sequence Increment", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Increment token rotation generation",
        observed_behavior="Decrements token rotation generation", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Scope authorization matching
    clean_code_10 = """def is_scope_authorized(granted_scopes: list, required_scope: str) -> bool:
    return required_scope in granted_scopes or "admin:all" in granted_scopes
"""
    mut_code_10 = """def is_scope_authorized(granted_scopes: list, required_scope: str) -> bool:
    return required_scope in granted_scopes and "admin:all" in granted_scopes
"""
    oracle_10 = """def run_oracle():
    assert is_scope_authorized(["read:users"], "read:users") is True, "Exact scope match is authorized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Scope Authorization Disjunction Logic", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Authorize if scope present OR admin:all present",
        observed_behavior="Requires both exact scope AND admin:all", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 API Key checksum verification
    clean_code_11 = """def verify_api_key_format(key: str) -> bool:
    return key.startswith("ak_live_") and len(key) == 32
"""
    mut_code_11 = """def verify_api_key_format(key: str) -> bool:
    return key.startswith("ak_live_") or len(key) == 32
"""
    oracle_11 = """def run_oracle():
    assert verify_api_key_format("ak_live_" + "0" * 24) is True
    assert verify_api_key_format("ak_test_" + "0" * 24) is False, "Must have live prefix"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Key Format Verification Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Require both live prefix AND 32-char length",
        observed_behavior="Accepts invalid test keys if length matches", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Multi-tenant user org isolation check
    clean_code_12 = """def can_access_tenant_data(user_org: str, resource_org: str) -> bool:
    return bool(user_org) and user_org == resource_org
"""
    mut_code_12 = """def can_access_tenant_data(user_org: str, resource_org: str) -> bool:
    return bool(user_org) or user_org == resource_org
"""
    oracle_12 = """def run_oracle():
    assert can_access_tenant_data("ORG-A", "ORG-B") is False, "Cross-tenant access forbidden"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Multi-Tenant Org Isolation Boundary", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Strict org equality check",
        observed_behavior="Allows cross-tenant access whenever user has any org", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in user authentication lookup
    clean_sec_1 = """def find_user_by_username(db_cursor, username: str):
    query = "SELECT id, password_hash, role FROM users WHERE username = ?"
    db_cursor.execute(query, (username,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def find_user_by_username(db_cursor, username: str):
    query = f"SELECT id, password_hash, role FROM users WHERE username = '{username}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockAuthCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockAuthCur()
    find_user_by_username(cur, "admin' OR '1'='1")
    assert cur.params is not None, "Authentication lookup must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Authentication SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized user query",
        observed_behavior="String interpolation allows SQL injection bypass", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in SSH key export utility
    clean_sec_2 = """import subprocess
def generate_user_ssh_cert(username: str, cert_path: str):
    if not username.isalnum():
        raise ValueError("Invalid username")
    subprocess.run(["ssh-keygen", "-s", "ca_key", "-n", username, cert_path], check=True)
"""
    mut_sec_2 = """import subprocess
def generate_user_ssh_cert(username: str, cert_path: str):
    subprocess.run(f"ssh-keygen -s ca_key -n {username} {cert_path}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(generate_user_ssh_cert)
    assert "shell=True" not in src, "Must avoid shell execution in certificate generation"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Certificate Generator Subprocess Security", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Execute binary with argument list",
        observed_behavior="Shell execution with unquoted username string", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in user avatar profile loader
    clean_sec_3 = """import os
def load_user_avatar(avatar_filename: str) -> str:
    base = "/app/user_avatars"
    clean = os.path.basename(avatar_filename)
    return os.path.join(base, clean)
"""
    mut_sec_3 = """import os
def load_user_avatar(avatar_filename: str) -> str:
    base = "/app/user_avatars"
    return os.path.join(base, avatar_filename)
"""
    oracle_sec_3 = """def run_oracle():
    p = load_user_avatar("../../../etc/passwd")
    assert "/etc/passwd" not in p and ".." not in p, "Path traversal in avatar resolution"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Avatar Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=4,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Strip path components using basename",
        observed_behavior="Relative directory traversal escapes avatar folder", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in user display name banner
    clean_sec_4 = """import html
def render_welcome_banner(display_name: str) -> str:
    return f"<h1>Welcome, {html.escape(display_name)}</h1>"
"""
    mut_sec_4 = """def render_welcome_banner(display_name: str) -> str:
    return f"<h1>Welcome, {display_name}</h1>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_welcome_banner("<script>alert(1)</script>")
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Welcome Banner HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in display name",
        observed_behavior="Unescaped reflection allows script execution", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on password reset endpoint
    clean_sec_5 = """def execute_password_reset(user_id: str, new_hash: str, reset_token: str) -> bool:
    if not reset_token:
        raise PermissionError("Unauthenticated password reset request")
    return True
"""
    mut_sec_5 = """def execute_password_reset(user_id: str, new_hash: str, reset_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        execute_password_reset("USER-1", "hash", "")
        assert False, "Password reset without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Reset Token Authentication", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify reset token presence before updating credentials",
        observed_behavior="Permits arbitrary unauthenticated password resets", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for user deletion
    clean_sec_6 = """def delete_user_account(caller_role: str, target_user: str) -> bool:
    return caller_role == "SUPER_ADMIN"
"""
    mut_sec_6 = """def delete_user_account(caller_role: str, target_user: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert delete_user_account("GUEST", "USER-42") is False, "Guest role cannot delete user accounts"
    assert delete_user_account("SUPER_ADMIN", "USER-42") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Account Deletion Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict account deletion to SUPER_ADMIN",
        observed_behavior="Grants account deletion to any caller", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear lookup in allowed permissions list
    clean_perf_1 = """def has_permission(user_perms_set: set, req_perm: str) -> bool:
    return req_perm in user_perms_set
"""
    mut_perf_1 = """def has_permission(user_perms_list: list, req_perm: str) -> bool:
    for p in user_perms_list:
        if p == req_perm:
            return True
    return False
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(has_permission)
    assert "set" in src or "in user_perms_set" in src, "Permission check must use set for O(1) membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Permissions Hash Set Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) set membership check",
        observed_behavior="O(N) linear list scan", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic role group membership filter
    clean_perf_2 = """def filter_authorized_roles(roles: list, valid_set: set) -> list:
    return [r for r in roles if r in valid_set]
"""
    mut_perf_2 = """def filter_authorized_roles(roles: list, valid_list: list) -> list:
    res = []
    for r in roles:
        found = False
        for v in valid_list:
            if r == v:
                found = True
                break
        if found:
            res.append(r)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_authorized_roles)
    assert "set" in src, "Role filtering must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Role Authorization Set Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based role filtering in O(N)",
        observed_behavior="Nested linear search in O(N*M)", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive role inheritance resolution
    clean_perf_3 = """def resolve_inherited_roles(role: str, hierarchy: dict, memo=None) -> set:
    if memo is None:
        memo = {}
    if role in memo:
        return memo[role]
    parents = hierarchy.get(role, [])
    res = {role}
    for p in parents:
        res.update(resolve_inherited_roles(p, hierarchy, memo))
    memo[role] = res
    return res
"""
    mut_perf_3 = """def resolve_inherited_roles(role: str, hierarchy: dict, memo=None) -> set:
    parents = hierarchy.get(role, [])
    res = {role}
    for p in parents:
        res.update(resolve_inherited_roles(p, hierarchy))
    return res
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(resolve_inherited_roles)
    assert "memo" in src and "memo[" in src, "Role hierarchy DAG resolution must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Role Hierarchy Inheritance Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized role resolution",
        observed_behavior="Exponential re-traversal of shared parent roles", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in auth audit log builder
    clean_perf_4 = """def build_auth_audit_log(events: list) -> str:
    lines = ["AUTH AUDIT LOG\\n"]
    for ev in events:
        lines.append(f"{ev['user']}:{ev['action']}:{ev['ip']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def build_auth_audit_log(events: list) -> str:
    res = "AUTH AUDIT LOG\\n"
    for ev in events:
        res = res + f"{ev['user']}:{ev['action']}:{ev['ip']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(build_auth_audit_log)
    assert ".join(" in src, "Audit log exporter must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Auth Audit Log String Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join list buffer in O(N)",
        observed_behavior="Repeated string reallocation in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of username validation regex
    clean_perf_5 = """import re
_USER_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
def is_valid_username(username: str) -> bool:
    return bool(_USER_RE.match(username))
"""
    mut_perf_5 = """import re
def is_valid_username(username: str) -> bool:
    r = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
    return bool(r.match(username))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_username)
    assert "re.compile" not in src, "Username regex must be precompiled once at module scope"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Username Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles pattern inside function", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty password rejection
    clean_reg_1 = """def authenticate_credentials(username: str, password_hash: str) -> bool:
    if not password_hash:
        raise ValueError("Password hash cannot be empty")
    return True
"""
    mut_reg_1 = """def authenticate_credentials(username: str, password_hash: str) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        authenticate_credentials("admin", "")
        assert False, "Regression: Empty password hash must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Empty Password Hash Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty password hashes",
        observed_behavior="Accepts empty password hashes", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative login attempts
    clean_reg_2 = """def increment_failed_logins(current: int) -> int:
    if current < 0:
        raise ValueError("Failed attempts cannot be negative")
    return current + 1
"""
    mut_reg_2 = """def increment_failed_logins(current: int) -> int:
    return current + 1
"""
    oracle_reg_2 = """def run_oracle():
    try:
        increment_failed_logins(-10)
        assert False, "Regression: Negative attempt count must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Login Attempt Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative attempt counts",
        observed_behavior="Allows negative attempt counts resetting lockout counter", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy user ID prefix
    clean_reg_3 = """def format_user_id(seq: int) -> str:
    return f"USR-{seq:06d}"
"""
    mut_reg_3 = """def format_user_id(seq: int) -> str:
    return f"{seq:06d}"
"""
    oracle_reg_3 = """def run_oracle():
    uid = format_user_id(7)
    assert uid == "USR-000007", f"Expected USR-000007, got {uid}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User ID Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include USR- prefix",
        observed_behavior="Drops USR- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in username normalizer
    clean_reg_4 = """def normalize_username(raw: str) -> str:
    cleaned = raw.strip().lower()
    if not cleaned:
        raise ValueError("Empty username")
    return cleaned
"""
    mut_reg_4 = """def normalize_username(raw: str) -> str:
    return raw.lower()
"""
    oracle_reg_4 = """def run_oracle():
    res = normalize_username("  Alice  ")
    assert res == "alice", f"Expected 'alice' without spaces, got '{res}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Username Whitespace Normalization Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on user display title
    clean_reg_5 = """def format_user_title(title: str) -> str:
    if title is None:
        return "Member"
    return title.strip()
"""
    mut_reg_5 = """def format_user_title(title: str) -> str:
    return title.strip()
"""
    oracle_reg_5 = """def run_oracle():
    assert format_user_title(None) == "Member", "None title must default to 'Member'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Title Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None title gracefully",
        observed_behavior="Raises AttributeError on None title", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed token response payload keys
    clean_integ_1 = """def build_token_response(access_tok: str, expires_in_sec: int) -> dict:
    return {"access_token": access_tok, "expires_in": expires_in_sec, "token_type": "Bearer"}
"""
    mut_integ_1 = """def build_token_response(access_tok: str, expires_in_sec: int) -> dict:
    return {"token": access_tok, "ttl": expires_in_sec, "type": "Bearer"}
"""
    oracle_integ_1 = """def run_oracle():
    res = build_token_response("tok_abc", 3600)
    assert "access_token" in res and "expires_in" in res, "OAuth2 specification requires 'access_token' and 'expires_in'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="OAuth2 Token Response Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="OAuth2 RFC 6749 compliant keys",
        observed_behavior="Emits proprietary non-standard keys", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs string) in session info endpoint
    clean_integ_2 = """def fetch_session_info(sid: str) -> dict:
    return {"session_id": sid, "is_valid": True}
"""
    mut_integ_2 = """def fetch_session_info(sid: str) -> str:
    return f"session:{sid}"
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_session_info("S-101")
    assert isinstance(res, dict) and "is_valid" in res, "Consumer expects session dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Session Info Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns raw string", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in downstream auth proxy
    clean_integ_3 = """def build_proxy_auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Forwarded-Proto": "https", "Content-Type": "application/json"}
"""
    mut_integ_3 = """def build_proxy_auth_headers(token: str) -> dict:
    return {"X-Forwarded-Proto": "https", "Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_proxy_auth_headers("tok_xyz")
    assert "Authorization" in h, "Downstream proxy requires Authorization header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Downstream Proxy Auth Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include Authorization header",
        observed_behavior="Omits Authorization header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in password expiry notification
    clean_integ_4 = """def format_password_expiry_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_password_expiry_date(year: int, month: int, day: int) -> str:
    return f"{day:02d}/{month:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    res = format_password_expiry_date(2026, 12, 31)
    assert res == "2026-12-31", f"Expected ISO 8601 YYYY-MM-DD, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Expiry Date Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date breaking downstream client", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Role casing mismatch in JWT claim serializer
    clean_integ_5 = """def serialize_jwt_role_claim(role: str) -> str:
    return role.strip().upper()
"""
    mut_integ_5 = """def serialize_jwt_role_claim(role: str) -> str:
    return role.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_jwt_role_claim("admin") == "ADMIN", "Role claims must be uppercase"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="JWT Role Claim Casing", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase role claim",
        observed_behavior="Emits lowercase role claim", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened password entropy assertion
    clean_drift_1 = """def is_secure_password(pwd: str) -> bool:
    has_upper = any(c.isupper() for c in pwd)
    has_lower = any(c.islower() for c in pwd)
    has_digit = any(c.isdigit() for c in pwd)
    return has_upper and has_lower and has_digit and len(pwd) >= 8
"""
    mut_drift_1 = """def is_secure_password(pwd: str) -> bool:
    # Drift: loosened requirement to only require length
    return len(pwd) >= 8
"""
    oracle_drift_1 = """def run_oracle():
    assert is_secure_password("lowercaseonly") is False, "Drift: Password missing upper and digits must fail"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Entropy Verification Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce mixed case, digits, and length",
        observed_behavior="Loosens check to only length allowing weak passwords", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping account lockout after failed logins
    clean_drift_2 = """def process_failed_attempt(user_record: dict) -> dict:
    fails = user_record.get("failed_count", 0) + 1
    locked = fails >= 5
    return {"failed_count": fails, "is_locked": locked}
"""
    mut_drift_2 = """def process_failed_attempt(user_record: dict) -> dict:
    # Drift: increments count but never sets is_locked to True
    fails = user_record.get("failed_count", 0) + 1
    return {"failed_count": fails, "is_locked": False}
"""
    oracle_drift_2 = """def run_oracle():
    res = process_failed_attempt({"failed_count": 4})
    assert res["is_locked"] is True, "Drift: 5th failure must trigger account lockout"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Account Lockout Action Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Lock account after 5 failed attempts",
        observed_behavior="Silently drops lockout action allowing brute force", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum concurrent active sessions invariant removal
    clean_drift_3 = """def can_open_new_session(active_count: int, max_allowed: int = 3) -> bool:
    if active_count >= max_allowed:
        return False
    return True
"""
    mut_drift_3 = """def can_open_new_session(active_count: int, max_allowed: int = 3) -> bool:
    # Drift: maximum session limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert can_open_new_session(5, 3) is False, "Drift: Exceeding active session limit must be rejected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Concurrent Session Limit Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce concurrent session ceiling",
        observed_behavior="Unconditionally permits unbounded active sessions", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in session expiration TTL
    clean_drift_4 = """def calculate_session_ttl(hours: float) -> int:
    from decimal import Decimal, ROUND_HALF_UP
    dec_sec = Decimal(str(hours)) * Decimal("3600")
    return int(dec_sec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def calculate_session_ttl(hours: float) -> int:
    # Drift: integer truncation of fractional hours before multiplying
    return int(hours) * 3600
"""
    oracle_drift_4 = """def run_oracle():
    res = calculate_session_ttl(1.5)
    assert res == 5400, f"Expected 5400s for 1.5h, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Session TTL Calculation Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate seconds calculation for fractional hours",
        observed_behavior="Truncates hour fraction losing 1800 seconds", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting session timeout policy requirements
    clean_conv_1 = """def check_session_timeout_policy(idle_seconds: int) -> bool:
    # Harmonized policy: idle allowed between 300 and 1800 seconds
    return 300 <= idle_seconds <= 1800
"""
    mut_conv_1 = """def check_session_timeout_policy(idle_seconds: int) -> bool:
    # Invariant conflict: Spec A requires idle < 200, Spec B requires idle > 500
    return idle_seconds < 200 and idle_seconds > 500
"""
    oracle_conv_1 = """def run_oracle():
    assert check_session_timeout_policy(600) is True, "Harmonized rule permits 600s"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Session Timeout Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid idle range",
        observed_behavior="Mutually contradictory rules (idle < 200 AND idle > 500)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: password retry limit operator
    clean_conv_2 = """def evaluate_retry_limit(attempts: int, limit: int) -> str:
    if attempts >= limit:
        return "LOCKED"
    return "OK"
"""
    mut_conv_2 = """def evaluate_retry_limit(attempts: int, limit: int) -> str:
    if attempts > limit:
        return "LOCKED"
    return "OK"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_retry_limit(5, 5) == "LOCKED", "Exact limit must be LOCKED"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Password Retry Limit Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact limit locks account",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in user lifecycle workflow
    clean_conv_3 = """def advance_user_lifecycle(status: str) -> str:
    flow = {"PENDING": "ACTIVE", "ACTIVE": "SUSPENDED", "SUSPENDED": "TERMINATED", "TERMINATED": "TERMINATED"}
    return flow.get(status, "PENDING")
"""
    mut_conv_3 = """def advance_user_lifecycle(status: str) -> str:
    # Circular loop between SUSPENDED and ACTIVE
    flow = {"PENDING": "ACTIVE", "ACTIVE": "SUSPENDED", "SUSPENDED": "ACTIVE", "TERMINATED": "TERMINATED"}
    return flow.get(status, "PENDING")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_user_lifecycle(advance_user_lifecycle("ACTIVE"))
    assert res == "TERMINATED", "State progression must reach terminal TERMINATED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="User Lifecycle State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to TERMINATED",
        observed_behavior="Infinite oscillation between ACTIVE and SUSPENDED",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def auth_clean_routine_{c_idx}(token_val: int) -> int:
    # Clean control {c_idx}: verified authentication helper with boundary guard
    if token_val < 0:
        return 0
    return (token_val * 7) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = auth_clean_routine_{c_idx}(5)
    assert res == 35 + {c_idx}, f"Expected {{35 + {c_idx}}}, got {{res}}"
    assert auth_clean_routine_{c_idx}(-2) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Auth Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified auth calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
