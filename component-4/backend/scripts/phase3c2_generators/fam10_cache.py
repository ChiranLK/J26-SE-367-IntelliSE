"""
Phase 3C.2 Family 10: In-Memory Caching & Eviction (FAM-10-CACHE).
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
    # 1.1 LRU cache capacity eviction boundary (> vs >=)
    clean_code_1 = """def should_evict_lru(current_size: int, max_capacity: int) -> bool:
    return current_size >= max_capacity
"""
    mut_code_1 = """def should_evict_lru(current_size: int, max_capacity: int) -> bool:
    return current_size > max_capacity
"""
    oracle_1 = """def run_oracle():
    assert should_evict_lru(100, 100) is True, "Cache at exact capacity must trigger eviction before inserting new item"
    assert should_evict_lru(99, 100) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="LRU Capacity Eviction Threshold Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Trigger eviction at exact capacity",
        observed_behavior="Allows cache to grow beyond max capacity before evicting", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 TTL expiration timestamp check
    clean_code_2 = """def is_entry_expired(stored_time: int, current_time: int, ttl: int) -> bool:
    return (current_time - stored_time) > ttl
"""
    mut_code_2 = """def is_entry_expired(stored_time: int, current_time: int, ttl: int) -> bool:
    return (stored_time - current_time) > ttl
"""
    oracle_2 = """def run_oracle():
    expired = is_entry_expired(100, 250, 100)
    assert expired is True, "150s elapsed exceeds 100s TTL"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="TTL Expiration Subtraction Direction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OPERAND_SUBTRACTION_INVERSION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Subtract stored_time from current_time",
        observed_behavior="Subtracts current_time from stored_time producing negative elapsed duration", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Cache hit ratio formula
    clean_code_3 = """def calculate_hit_ratio(hits: int, misses: int) -> float:
    total = hits + misses
    if total <= 0:
        return 0.0
    return round((hits / total) * 100.0, 2)
"""
    mut_code_3 = """def calculate_hit_ratio(hits: int, misses: int) -> float:
    total = hits + misses
    if total <= 0:
        return 0.0
    return round((misses / total) * 100.0, 2)
"""
    oracle_3 = """def run_oracle():
    ratio = calculate_hit_ratio(80, 20)
    assert ratio == 80.0, f"Expected 80.0% hit ratio, got {ratio}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Hit Ratio Variable Substitution", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="VARIABLE_SUBSTITUTION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Calculate percentage of hits",
        observed_behavior="Calculates percentage of misses instead of hits", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 LFU frequency counter increment
    clean_code_4 = """def increment_lfu_frequency(freq_map: dict, key: str) -> int:
    current = freq_map.get(key, 0)
    freq_map[key] = current + 1
    return freq_map[key]
"""
    mut_code_4 = """def increment_lfu_frequency(freq_map: dict, key: str) -> int:
    current = freq_map.get(key, 0)
    freq_map[key] = current - 1
    return freq_map[key]
"""
    oracle_4 = """def run_oracle():
    m = {"k1": 5}
    new_f = increment_lfu_frequency(m, "k1")
    assert new_f == 6, f"Expected frequency 6, got {new_f}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="LFU Frequency Counter Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Increment access frequency",
        observed_behavior="Decrements frequency on cache hit", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Cache-aside lock release on exception
    clean_code_5 = """def acquire_cache_lock(lock_map: dict, key: str) -> bool:
    if lock_map.get(key, False):
        return False
    lock_map[key] = True
    return True
"""
    mut_code_5 = """def acquire_cache_lock(lock_map: dict, key: str) -> bool:
    if not lock_map.get(key, False):
        return False
    lock_map[key] = True
    return True
"""
    oracle_5 = """def run_oracle():
    locks = {"key1": False}
    acquired = acquire_cache_lock(locks, "key1")
    assert acquired is True, "Unlocked key must be successfully acquired"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Stampede Mutex Acquisition Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="BOOLEAN_INVERSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Acquire lock when key is not currently locked",
        observed_behavior="Inverts check only permitting acquisition when already locked", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Tag-based cache invalidation
    clean_code_6 = """def invalidate_tagged_keys(cache: dict, tag_map: dict, target_tag: str) -> int:
    keys_to_remove = tag_map.get(target_tag, set())
    count = 0
    for k in list(keys_to_remove):
        if k in cache:
            del cache[k]
            count += 1
    return count
"""
    mut_code_6 = """def invalidate_tagged_keys(cache: dict, tag_map: dict, target_tag: str) -> int:
    keys_to_remove = tag_map.get(target_tag, set())
    count = 0
    for k in list(keys_to_remove):
        if k not in cache:
            del cache[k]
            count += 1
    return count
"""
    oracle_6 = """def run_oracle():
    c = {"user:1": "data1", "user:2": "data2"}
    tags = {"users": {"user:1"}}
    removed = invalidate_tagged_keys(c, tags, "users")
    assert removed == 1 and "user:1" not in c, f"Expected 1 key removed, got {removed}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tag Invalidation Cache Key Membership Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Delete key when it exists in cache",
        observed_behavior="Attempts to delete missing keys triggering KeyError", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Memory footprint size estimation clamp
    clean_code_7 = """def estimate_cache_entry_bytes(key: str, val_bytes: int) -> int:
    overhead = 64
    return len(key.encode('utf-8')) + val_bytes + overhead
"""
    mut_code_7 = """def estimate_cache_entry_bytes(key: str, val_bytes: int) -> int:
    overhead = 64
    return len(key.encode('utf-8')) + val_bytes - overhead
"""
    oracle_7 = """def run_oracle():
    b = estimate_cache_entry_bytes("my_key", 100)
    assert b == 170, f"Expected 6 bytes + 100 + 64 = 170 bytes, got {b}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Memory Overhead Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Add internal memory overhead to entry size",
        observed_behavior="Subtracts overhead underestimating memory usage", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Bounded ring buffer write index wrapping
    clean_code_8 = """def advance_ring_buffer_head(head_idx: int, capacity: int) -> int:
    return (head_idx + 1) % capacity
"""
    mut_code_8 = """def advance_ring_buffer_head(head_idx: int, capacity: int) -> int:
    return (head_idx + 1)
"""
    oracle_8 = """def run_oracle():
    new_h = advance_ring_buffer_head(9, 10)
    assert new_h == 0, f"Expected wrap around to 0 at capacity 10, got {new_h}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Ring Buffer Modulo Wrap Omission", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MODULO_WRAP_OMISSION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Wrap buffer index around capacity using modulo",
        observed_behavior="Omits modulo allowing index to grow out of bounds", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Key namespace isolation prefix builder
    clean_code_9 = """def build_namespaced_key(namespace: str, raw_key: str) -> str:
    return f"{namespace.strip()}:{raw_key.strip()}"
"""
    mut_code_9 = """def build_namespaced_key(namespace: str, raw_key: str) -> str:
    return f"{raw_key.strip()}:{namespace.strip()}"
"""
    oracle_9 = """def run_oracle():
    k = build_namespaced_key("tenant1", "session123")
    assert k == "tenant1:session123", f"Expected namespace prefix, got {k}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Namespace Key Prefix Order Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="STRING_INTERPOLATION_ORDER_INVERSION", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Format namespace followed by key",
        observed_behavior="Inverts order placing key before namespace", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Minimum cache TTL duration validator
    clean_code_10 = """def validate_cache_ttl(ttl_sec: int, min_ttl: int = 5, max_ttl: int = 86400) -> bool:
    return min_ttl <= ttl_sec <= max_ttl
"""
    mut_code_10 = """def validate_cache_ttl(ttl_sec: int, min_ttl: int = 5, max_ttl: int = 86400) -> bool:
    return min_ttl < ttl_sec < max_ttl
"""
    oracle_10 = """def run_oracle():
    assert validate_cache_ttl(5, 5, 86400) is True, "Exact minimum TTL must be allowed"
    assert validate_cache_ttl(86400, 5, 86400) is True, "Exact maximum TTL must be allowed"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache TTL Inclusive Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Inclusive comparison for valid TTL duration",
        observed_behavior="Strict inequalities reject exact boundary values", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Eviction candidate minimum frequency selector
    clean_code_11 = """def find_lfu_eviction_candidate(freq_map: dict) -> str:
    if not freq_map:
        return ""
    return min(freq_map.keys(), key=lambda k: freq_map[k])
"""
    mut_code_11 = """def find_lfu_eviction_candidate(freq_map: dict) -> str:
    if not freq_map:
        return ""
    return max(freq_map.keys(), key=lambda k: freq_map[k])
"""
    oracle_11 = """def run_oracle():
    freqs = {"popular": 100, "rare": 1}
    victim = find_lfu_eviction_candidate(freqs)
    assert victim == "rare", f"Expected least frequently used 'rare' to be evicted, got {victim}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="LFU Eviction Min vs Max Candidate Selector", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Select item with lowest frequency using min()",
        observed_behavior="Uses max() evicting most frequently used item", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Sliding window hit counter window purge
    clean_code_12 = """def purge_stale_window_hits(timestamps: list, cutoff_time: int) -> list:
    return [t for t in timestamps if t >= cutoff_time]
"""
    mut_code_12 = """def purge_stale_window_hits(timestamps: list, cutoff_time: int) -> list:
    return [t for t in timestamps if t < cutoff_time]
"""
    oracle_12 = """def run_oracle():
    hits = [100, 200, 300]
    fresh = purge_stale_window_hits(hits, 200)
    assert fresh == [200, 300], f"Expected hits >= 200 to be preserved, got {fresh}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Sliding Window Hit Cutoff Relational Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_INVERSION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Retain timestamps >= cutoff time",
        observed_behavior="Inverts check retaining stale entries and dropping fresh hits", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in cache persistence dump query
    clean_sec_1 = """def query_cached_persisted_record(db_cursor, cache_key: str):
    query = "SELECT value, expires_at FROM persistent_cache WHERE cache_key = ?"
    db_cursor.execute(query, (cache_key,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_cached_persisted_record(db_cursor, cache_key: str):
    query = f"SELECT value, expires_at FROM persistent_cache WHERE cache_key = '{cache_key}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockCacheCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockCacheCur()
    query_cached_persisted_record(cur, "session' OR 1=1--")
    assert cur.params is not None, "Persistent cache query must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Persistent Cache Query SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized SQL query for cache store",
        observed_behavior="Unsanitized string interpolation allows SQL injection", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in Redis backup snapshot tool
    clean_sec_2 = """import subprocess
def trigger_redis_bgsave_tool(host: str, port: int):
    if not host.replace(".", "").isalnum():
        raise ValueError("Invalid host")
    subprocess.run(["redis-cli", "-h", host, "-p", str(port), "bgsave"], check=True)
"""
    mut_sec_2 = """import subprocess
def trigger_redis_bgsave_tool(host: str, port: int):
    subprocess.run(f"redis-cli -h {host} -p {port} bgsave", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(trigger_redis_bgsave_tool)
    assert "shell=True" not in src, "Must avoid shell execution in cache backup utility"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Redis Snapshot Subprocess Shell Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Subprocess list execution without shell",
        observed_behavior="Shell execution with unquoted host parameter", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in cache snapshot file persistence
    clean_sec_3 = """import os
def resolve_cache_dump_filepath(snapshot_name: str) -> str:
    base = "/app/cache/dumps"
    clean = os.path.basename(snapshot_name)
    return os.path.join(base, f"{clean}.rdb")
"""
    mut_sec_3 = """import os
def resolve_cache_dump_filepath(snapshot_name: str) -> str:
    base = "/app/cache/dumps"
    return os.path.join(base, f"{snapshot_name}.rdb")
"""
    oracle_sec_3 = """def run_oracle():
    target = resolve_cache_dump_filepath("../../etc/passwd")
    assert "/etc/passwd" not in target and ".." not in target, "Path traversal in cache snapshot path"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Snapshot File Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=3,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize snapshot filename using basename",
        observed_behavior="Direct join allows directory traversal", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in cache inspector debug HTML dashboard
    clean_sec_4 = """import html
def render_cache_entry_row(key: str, val_str: str) -> str:
    return f"<tr><td>{html.escape(key)}</td><td>{html.escape(val_str)}</td></tr>"
"""
    mut_sec_4 = """def render_cache_entry_row(key: str, val_str: str) -> str:
    return f"<tr><td>{key}</td><td>{val_str}</td></tr>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_cache_entry_row("<script>alert(1)</script>", "val")
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Inspector HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML in cache key display",
        observed_behavior="Unescaped key reflection allows XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on cache flush endpoint
    clean_sec_5 = """def flush_all_cache_entries(admin_token: str) -> bool:
    if not admin_token:
        raise PermissionError("Unauthenticated cache flush request")
    return True
"""
    mut_sec_5 = """def flush_all_cache_entries(admin_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        flush_all_cache_entries("")
        assert False, "Flushing cache without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Flush Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller token before flushing cache",
        observed_behavior="Allows unauthenticated cache flushes", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for cache max memory limit update
    clean_sec_6 = """def update_cache_memory_limit(user_role: str, limit_mb: int) -> bool:
    return user_role in {"INFRASTRUCTURE_ADMIN", "SITE_RELIABILITY_LEAD"}
"""
    mut_sec_6 = """def update_cache_memory_limit(user_role: str, limit_mb: int) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert update_cache_memory_limit("APP_USER", 4096) is False, "Standard app user cannot modify memory limits"
    assert update_cache_memory_limit("INFRASTRUCTURE_ADMIN", 4096) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Memory Limit Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict cache memory limit updates to infrastructure admins",
        observed_behavior="Grants memory configuration access to any role", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear key lookup in cache entries list
    clean_perf_1 = """def fetch_cached_value(cache_map: dict, key: str) -> str:
    return cache_map.get(key, "")
"""
    mut_perf_1 = """def fetch_cached_value(cache_list: list, key: str) -> str:
    for item in cache_list:
        if item['key'] == key:
            return item['val']
    return ""
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(fetch_cached_value)
    assert "dict" in src or "get(" in src, "Cache lookup must use O(1) hash map"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Key Hash Map O(1) Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) hash map key lookup",
        observed_behavior="O(N) linear list scan", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic key invalidation membership check
    clean_perf_2 = """def filter_retained_cache_keys(keys: list, evicted_set: set) -> list:
    return [k for k in keys if k not in evicted_set]
"""
    mut_perf_2 = """def filter_retained_cache_keys(keys: list, evicted_list: list) -> list:
    res = []
    for k in keys:
        found = False
        for e in evicted_list:
            if k == e:
                found = True
                break
        if not found:
            res.append(k)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_retained_cache_keys)
    assert "set" in src, "Eviction filter must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Eviction Retained Keys Set Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based key retention filter in O(N)",
        observed_behavior="Nested linear search in O(N*M)", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive cache tree size calculation
    clean_perf_3 = """def calculate_cache_tree_size(node: dict, memo=None) -> int:
    if memo is None:
        memo = {}
    node_id = id(node)
    if node_id in memo:
        return memo[node_id]
    children = node.get("subcaches", [])
    total = len(node.get("keys", [])) + sum(calculate_cache_tree_size(c, memo) for c in children)
    memo[node_id] = total
    return total
"""
    mut_perf_3 = """def calculate_cache_tree_size(node: dict, memo=None) -> int:
    children = node.get("subcaches", [])
    return len(node.get("keys", [])) + sum(calculate_cache_tree_size(c) for c in children)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(calculate_cache_tree_size)
    assert "memo" in src and "memo[" in src, "Cache hierarchy size traversal must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Hierarchy Size Traversal Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized hierarchical size evaluation",
        observed_behavior="Exponential re-traversal of shared sub-caches", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in cache dump export builder
    clean_perf_4 = """def export_cache_dump(entries: list) -> str:
    lines = ["CACHE DUMP\\n"]
    for e in entries:
        lines.append(f"{e['key']}:{e['val']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def export_cache_dump(entries: list) -> str:
    res = "CACHE DUMP\\n"
    for e in entries:
        res = res + f"{e['key']}:{e['val']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(export_cache_dump)
    assert ".join(" in src, "Cache dump exporter must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Dump Buffer String Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join list buffer in O(N)",
        observed_behavior="Repeated string reallocation in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of cache key namespace regex
    clean_perf_5 = """import re
_CACHE_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+:[a-zA-Z0-9_\\-\\.]+$")
def is_valid_cache_key_syntax(key: str) -> bool:
    return bool(_CACHE_KEY_RE.match(key))
"""
    mut_perf_5 = """import re
def is_valid_cache_key_syntax(key: str) -> bool:
    r = re.compile(r"^[a-zA-Z0-9_]+:[a-zA-Z0-9_\\-\\.]+$")
    return bool(r.match(key))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_cache_key_syntax)
    assert "re.compile" not in src, "Cache key regex must be compiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Key Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles regex on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty cache key rejection
    clean_reg_1 = """def store_cache_entry(key: str, val: str) -> bool:
    if not key or not key.strip():
        raise ValueError("Cache key cannot be empty")
    return True
"""
    mut_reg_1 = """def store_cache_entry(key: str, val: str) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        store_cache_entry("   ", "val")
        assert False, "Regression: Blank cache key must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Blank Cache Key Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty or whitespace cache keys with ValueError",
        observed_behavior="Stores entries with blank keys", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative cache capacity configuration
    clean_reg_2 = """def configure_cache_capacity(cap: int) -> bool:
    if cap <= 0:
        raise ValueError("Cache capacity must be strictly positive")
    return True
"""
    mut_reg_2 = """def configure_cache_capacity(cap: int) -> bool:
    return True
"""
    oracle_reg_2 = """def run_oracle():
    try:
        configure_cache_capacity(-100)
        assert False, "Regression: Negative cache capacity must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Cache Capacity Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative cache capacity",
        observed_behavior="Accepts negative capacity setting", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy cache cluster ID prefix
    clean_reg_3 = """def format_cluster_node_id(seq: int) -> str:
    return f"NODE-{seq:04d}"
"""
    mut_reg_3 = """def format_cluster_node_id(seq: int) -> str:
    return f"{seq:04d}"
"""
    oracle_reg_3 = """def run_oracle():
    nid = format_cluster_node_id(12)
    assert nid == "NODE-0012", f"Expected NODE-0012, got {nid}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cluster Node ID Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include NODE- prefix",
        observed_behavior="Drops NODE- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in cache keys
    clean_reg_4 = """def normalize_cache_key(raw_key: str) -> str:
    cleaned = raw_key.strip()
    if not cleaned:
        raise ValueError("Empty key")
    return cleaned
"""
    mut_reg_4 = """def normalize_cache_key(raw_key: str) -> str:
    return raw_key
"""
    oracle_reg_4 = """def run_oracle():
    k = normalize_cache_key("  session_token  ")
    assert k == "session_token", f"Expected 'session_token' without spaces, got '{k}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Key Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before storing cache key",
        observed_behavior="Preserves leading/trailing spaces causing cache misses", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on cached metadata dictionary
    clean_reg_5 = """def extract_cache_header(meta: dict, key: str) -> str:
    if meta is None:
        return ""
    return str(meta.get(key, ""))
"""
    mut_reg_5 = """def extract_cache_header(meta: dict, key: str) -> str:
    return str(meta.get(key, ""))
"""
    oracle_reg_5 = """def run_oracle():
    assert extract_cache_header(None, "etag") == "", "None meta dict must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Metadata Dictionary Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None meta dictionary gracefully",
        observed_behavior="Raises AttributeError on None meta", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed cache metrics payload schema keys
    clean_integ_1 = """def build_cache_stats_payload(hit_count: int, miss_count: int) -> dict:
    return {"total_hits": hit_count, "total_misses": miss_count, "status": "ONLINE"}
"""
    mut_integ_1 = """def build_cache_stats_payload(hit_count: int, miss_count: int) -> dict:
    return {"hits": hit_count, "misses": miss_count, "status": "ONLINE"}
"""
    oracle_integ_1 = """def run_oracle():
    p = build_cache_stats_payload(100, 20)
    assert "total_hits" in p and "total_misses" in p, "Schema requires 'total_hits' and 'total_misses'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Statistics Payload Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified cache stats keys",
        observed_behavior="Emits abbreviated keys breaking monitoring integration", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs list) in cache eviction event
    clean_integ_2 = """def fetch_eviction_event(eviction_id: str) -> dict:
    return {"eviction_id": eviction_id, "evicted": True}
"""
    mut_integ_2 = """def fetch_eviction_event(eviction_id: str) -> list:
    return [eviction_id, True]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_eviction_event("EV-1")
    assert isinstance(res, dict) and "evicted" in res, "Consumer expects eviction event dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Eviction Event Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns plain list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in cache replication webhook
    clean_integ_3 = """def build_replication_headers(token: str) -> dict:
    return {"X-Replication-Token": token, "Content-Type": "application/json"}
"""
    mut_integ_3 = """def build_replication_headers(token: str) -> dict:
    return {"Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_replication_headers("repl_tok_123")
    assert "X-Replication-Token" in h, "Replication slave requires X-Replication-Token header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Replication Webhook Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include X-Replication-Token header",
        observed_behavior="Omits replication token header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in cache expiration timestamp
    clean_integ_4 = """def format_cache_expiry_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_cache_expiry_date(year: int, month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_cache_expiry_date(2026, 12, 31)
    assert d == "2026-12-31", f"Cache expiration format requires YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Expiry Date Serialization Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Eviction policy casing mismatch in cache configuration
    clean_integ_5 = """def serialize_eviction_policy(policy: str) -> str:
    return policy.strip().upper()
"""
    mut_integ_5 = """def serialize_eviction_policy(policy: str) -> str:
    return policy.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_eviction_policy("lru") == "LRU", "Cache config standard requires uppercase LRU"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Eviction Policy Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase eviction policy name",
        observed_behavior="Emits lowercase policy name", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened cache eviction invariant assertion: omitting capacity check
    clean_drift_1 = """def verify_eviction_correctness(victim_is_oldest: bool, size_decremented: bool) -> bool:
    return victim_is_oldest and size_decremented
"""
    mut_drift_1 = """def verify_eviction_correctness(victim_is_oldest: bool, size_decremented: bool) -> bool:
    # Drift: loosened requirement to only check size decrement, ignoring LRU age ordering
    return size_decremented
"""
    oracle_drift_1 = """def run_oracle():
    assert verify_eviction_correctness(False, True) is False, "Drift: Evicting non-oldest item must fail correctness check"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="LRU Age Eviction Invariant Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both oldest candidate and size decrement",
        observed_behavior="Loosens check allowing arbitrary item eviction", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping TTL expiration pruning
    clean_drift_2 = """def retrieve_active_entry(entry: dict, current_time: int) -> dict:
    if current_time >= entry.get("expires_at", 0):
        return {}
    return entry
"""
    mut_drift_2 = """def retrieve_active_entry(entry: dict, current_time: int) -> dict:
    # Drift: expiration check dropped, returns stale entries
    return entry
"""
    oracle_drift_2 = """def run_oracle():
    expired_entry = {"key": "k", "expires_at": 100}
    res = retrieve_active_entry(expired_entry, 150)
    assert res == {}, "Drift: Expired entry must return empty dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Stale Entry Pruning Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Return empty dict for expired entries",
        observed_behavior="Silently serves expired cache entries", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum item payload size invariant removal
    clean_drift_3 = """def validate_cache_item_size(size_bytes: int, max_bytes: int = 1048576) -> bool:
    if size_bytes > max_bytes:
        return False
    return True
"""
    mut_drift_3 = """def validate_cache_item_size(size_bytes: int, max_bytes: int = 1048576) -> bool:
    # Drift: item size limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_cache_item_size(5000000, 1048576) is False, "Drift: 5MB item exceeds 1MB max"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Item Size Limit Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce item byte ceiling",
        observed_behavior="Unconditionally permits unbounded item size", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in cache hit ratio calculation
    clean_drift_4 = """def compute_hit_ratio_fraction(hits: int, total: int) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    dec = (Decimal(str(hits)) / Decimal(str(total))) * Decimal("100")
    return float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def compute_hit_ratio_fraction(hits: int, total: int) -> float:
    # Drift: integer truncation of percentage
    return float(int(hits * 100 / total))
"""
    oracle_drift_4 = """def run_oracle():
    res = compute_hit_ratio_fraction(2, 3)
    assert res == 66.67, f"Expected 66.67% after half-up rounding, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Hit Ratio Decimal Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate 2-decimal half-up hit ratio rounding",
        observed_behavior="Integer truncation drops decimal fraction", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting cache capacity policy requirements
    clean_conv_1 = """def check_cache_capacity_policy(cap: int) -> bool:
    # Harmonized policy: capacity allowed between 100 and 10000
    return 100 <= cap <= 10000
"""
    mut_conv_1 = """def check_cache_capacity_policy(cap: int) -> bool:
    # Invariant conflict: Policy A requires cap < 80, Policy B requires cap > 200
    return cap < 80 and cap > 200
"""
    oracle_conv_1 = """def run_oracle():
    assert check_cache_capacity_policy(500) is True, "Harmonized rule permits 500"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Capacity Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid capacity range",
        observed_behavior="Mutually contradictory rules (cap < 80 AND cap > 200)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: eviction water mark operator
    clean_conv_2 = """def evaluate_watermark(usage_pct: float, high_watermark: float) -> str:
    if usage_pct >= high_watermark:
        return "EVICTION_TRIGGERED"
    return "STABLE"
"""
    mut_conv_2 = """def evaluate_watermark(usage_pct: float, high_watermark: float) -> str:
    if usage_pct > high_watermark:
        return "EVICTION_TRIGGERED"
    return "STABLE"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_watermark(85.0, 85.0) == "EVICTION_TRIGGERED", "Exact high watermark must trigger eviction"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Watermark Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary triggers eviction",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in cache node lifecycle
    clean_conv_3 = """def advance_node_lifecycle(state: str) -> str:
    flow = {"JOINING": "SYNCING", "SYNCING": "ONLINE", "ONLINE": "ONLINE"}
    return flow.get(state, "JOINING")
"""
    mut_conv_3 = """def advance_node_lifecycle(state: str) -> str:
    # Circular loop between SYNCING and JOINING
    flow = {"JOINING": "SYNCING", "SYNCING": "JOINING", "ONLINE": "ONLINE"}
    return flow.get(state, "JOINING")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_node_lifecycle(advance_node_lifecycle("JOINING"))
    assert res == "ONLINE", "Node lifecycle must reach terminal ONLINE state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cache Node Lifecycle State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to ONLINE",
        observed_behavior="Infinite oscillation between JOINING and SYNCING",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def cache_clean_routine_{c_idx}(key_val: int) -> int:
    # Clean control {c_idx}: verified caching calculation with boundary guard
    if key_val < 0:
        return 0
    return (key_val * 8) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = cache_clean_routine_{c_idx}(10)
    assert res == 80 + {c_idx}, f"Expected {{80 + {c_idx}}}, got {{res}}"
    assert cache_clean_routine_{c_idx}(-2) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Cache Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified cache calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
