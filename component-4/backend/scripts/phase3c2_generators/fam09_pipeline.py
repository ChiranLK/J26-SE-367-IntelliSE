"""
Phase 3C.2 Family 09: Batch ETL & Data Pipelines (FAM-09-PIPELINE).
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
    # 1.1 Batch chunking slice division
    clean_code_1 = """def chunk_record_stream(records: list, chunk_size: int) -> list:
    if chunk_size <= 0:
        return [records] if records else []
    return [records[i:i + chunk_size] for i in range(0, len(records), chunk_size)]
"""
    mut_code_1 = """def chunk_record_stream(records: list, chunk_size: int) -> list:
    if chunk_size <= 0:
        return [records] if records else []
    return [records[i:i + chunk_size - 1] for i in range(0, len(records), chunk_size)]
"""
    oracle_1 = """def run_oracle():
    chunks = chunk_record_stream([1, 2, 3, 4, 5, 6], 2)
    assert len(chunks) == 3 and chunks[0] == [1, 2], f"Expected 3 chunks of size 2, got {chunks}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Batch Chunking Slice Width Offset", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="OFF_BY_ONE_SLICE", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Extract chunks of exact requested size",
        observed_behavior="Extracts chunk_size - 1 items losing stream records", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 CSV column delimiter splitting
    clean_code_2 = """def parse_csv_line(line: str, delimiter: str = ",") -> list:
    return [col.strip() for col in line.split(delimiter)]
"""
    mut_code_2 = """def parse_csv_line(line: str, delimiter: str = ",") -> list:
    return [col.strip() for col in line.split(";")]
"""
    oracle_2 = """def run_oracle():
    cols = parse_csv_line("id,name,value", ",")
    assert cols == ["id", "name", "value"], f"Expected 3 comma-separated columns, got {cols}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="CSV Delimiter String Literal Substitution", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="STRING_LITERAL_MUTATION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Split line using provided delimiter parameter",
        observed_behavior="Hardcoded semicolon delimiter fails on comma separated lines", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Record enrichment key join
    clean_code_3 = """def enrich_records(primary: list, lookup_map: dict, join_key: str) -> list:
    res = []
    for r in primary:
        merged = dict(r)
        lookup_val = r.get(join_key)
        if lookup_val in lookup_map:
            merged.update(lookup_map[lookup_val])
        res.append(merged)
    return res
"""
    mut_code_3 = """def enrich_records(primary: list, lookup_map: dict, join_key: str) -> list:
    res = []
    for r in primary:
        merged = dict(r)
        lookup_val = r.get(join_key)
        if lookup_val not in lookup_map:
            merged.update(lookup_map.get(lookup_val, {}))
        res.append(merged)
    return res
"""
    oracle_3 = """def run_oracle():
    records = [{"id": 1, "val": 10}]
    lookup = {1: {"enriched": True}}
    res = enrich_records(records, lookup, "id")
    assert res[0].get("enriched") is True, f"Expected enriched record, got {res[0]}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Record Join Key Membership Inversion", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Enrich record when join key exists in lookup map",
        observed_behavior="Inverts check dropping enrichment for valid keys", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Type casting with numeric conversion
    clean_code_4 = """def cast_field_to_int(val: str, default: int = 0) -> int:
    try:
        return int(val.strip())
    except (ValueError, TypeError, AttributeError):
        return default
"""
    mut_code_4 = """def cast_field_to_int(val: str, default: int = 0) -> int:
    try:
        return int(float(val.strip()))
    except (ValueError, TypeError, AttributeError):
        return -default
"""
    oracle_4 = """def run_oracle():
    res = cast_field_to_int("bad_data", 5)
    assert res == 5, f"Expected default 5 on failure, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Type Cast Fallback Value Sign Error", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Return exact default value on failure",
        observed_behavior="Negates default value on exception fallback", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Record deduplication on composite hash
    clean_code_5 = """def deduplicate_dataset(records: list, key_fields: tuple) -> list:
    seen = set()
    res = []
    for r in records:
        comp_key = tuple(r.get(f) for f in key_fields)
        if comp_key not in seen:
            seen.add(comp_key)
            res.append(r)
    return res
"""
    mut_code_5 = """def deduplicate_dataset(records: list, key_fields: tuple) -> list:
    seen = set()
    res = []
    for r in records:
        comp_key = tuple(r.get(f) for f in key_fields)
        if comp_key in seen:
            seen.add(comp_key)
            res.append(r)
    return res
"""
    oracle_5 = """def run_oracle():
    recs = [{"id": 1, "v": "a"}, {"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
    dedup = deduplicate_dataset(recs, ("id", "v"))
    assert len(dedup) == 2, f"Expected 2 unique records, got {len(dedup)}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Dataset Deduplication Membership Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Retain first occurrence of unique composite key",
        observed_behavior="Inverts check retaining only duplicate entries", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Dead-letter queue threshold count
    clean_code_6 = """def should_route_to_dlq(error_count: int, max_retry_limit: int = 3) -> bool:
    return error_count >= max_retry_limit
"""
    mut_code_6 = """def should_route_to_dlq(error_count: int, max_retry_limit: int = 3) -> bool:
    return error_count > max_retry_limit
"""
    oracle_6 = """def run_oracle():
    assert should_route_to_dlq(3, 3) is True, "3 errors out of 3 limit must route to DLQ"
    assert should_route_to_dlq(2, 3) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Dead-Letter Queue Retry Threshold Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Route to DLQ at or above retry limit",
        observed_behavior="Allows an additional retry beyond defined ceiling", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 JSON nested dictionary key flattener
    clean_code_7 = """def flatten_json_record(data: dict, prefix: str = "") -> dict:
    res = {}
    for k, v in data.items():
        composite_k = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            res.update(flatten_json_record(v, composite_k))
        else:
            res[composite_k] = v
    return res
"""
    mut_code_7 = """def flatten_json_record(data: dict, prefix: str = "") -> dict:
    res = {}
    for k, v in data.items():
        composite_k = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            res.update(flatten_json_record(v, prefix))
        else:
            res[composite_k] = v
    return res
"""
    oracle_7 = """def run_oracle():
    nested = {"user": {"profile": {"name": "Alice"}}}
    flat = flatten_json_record(nested)
    assert "user.profile.name" in flat and flat["user.profile.name"] == "Alice", f"Expected user.profile.name, got {flat}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="JSON Flattener Nested Key Prefix Accumulation", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="ARGUMENT_VARIABLE_SUBSTITUTION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Pass composite key down recursive call",
        observed_behavior="Passes parent prefix dropping intermediate hierarchy levels", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Pipeline checkpoint offset commit
    clean_code_8 = """def commit_pipeline_checkpoint(current_offset: int, batch_count: int) -> int:
    return current_offset + batch_count
"""
    mut_code_8 = """def commit_pipeline_checkpoint(current_offset: int, batch_count: int) -> int:
    return current_offset - batch_count
"""
    oracle_8 = """def run_oracle():
    new_offset = commit_pipeline_checkpoint(1000, 250)
    assert new_offset == 1250, f"Expected offset 1250, got {new_offset}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Checkpoint Offset Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Add processed batch count to checkpoint",
        observed_behavior="Subtracts batch count moving checkpoint backwards", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 PII email masking transformer
    clean_code_9 = """def mask_pii_email(email: str) -> str:
    if "@" not in email:
        return email
    user, domain = email.split("@", 1)
    masked_user = user[0] + "***" if user else "***"
    return f"{masked_user}@{domain}"
"""
    mut_code_9 = """def mask_pii_email(email: str) -> str:
    if "@" not in email:
        return email
    user, domain = email.split("@", 1)
    masked_user = user + "***" if user else "***"
    return f"{masked_user}@{domain}"
"""
    oracle_9 = """def run_oracle():
    masked = mask_pii_email("john.doe@example.com")
    assert masked == "j***@example.com", f"Expected j***@example.com, got {masked}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="PII Masking Substring Retention", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="SLICE_OMISSION", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Retain only first character of username followed by asterisks",
        observed_behavior="Appends asterisks to full username leaking PII", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Field nullability validation rule
    clean_code_10 = """def validate_required_fields(record: dict, required_keys: set) -> bool:
    return required_keys.issubset(record.keys()) and all(record[k] is not None for k in required_keys)
"""
    mut_code_10 = """def validate_required_fields(record: dict, required_keys: set) -> bool:
    return required_keys.issubset(record.keys()) and any(record[k] is not None for k in required_keys)
"""
    oracle_10 = """def run_oracle():
    rec = {"id": 1, "name": None}
    assert validate_required_fields(rec, {"id", "name"}) is False, "Record with None for required field must fail"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Required Field All vs Any Check", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="BUILTIN_FUNCTION_REPLACEMENT", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Require ALL required fields to be non-None",
        observed_behavior="Uses any() permitting null values in required columns", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Record filtering condition combining
    clean_code_11 = """def is_record_eligible(status: str, is_active: bool) -> bool:
    return status == "VERIFIED" and is_active
"""
    mut_code_11 = """def is_record_eligible(status: str, is_active: bool) -> bool:
    return status == "VERIFIED" or is_active
"""
    oracle_11 = """def run_oracle():
    assert is_record_eligible("UNVERIFIED", True) is False, "Unverified active record is not eligible"
    assert is_record_eligible("VERIFIED", True) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Record Eligibility Compound Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Require both VERIFIED status AND active flag",
        observed_behavior="Uses OR permitting unverified records", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 CSV row counter header offset
    clean_code_12 = """def count_data_rows(total_lines: int, has_header: bool) -> int:
    offset = 1 if has_header else 0
    return max(0, total_lines - offset)
"""
    mut_code_12 = """def count_data_rows(total_lines: int, has_header: bool) -> int:
    offset = 1 if has_header else 0
    return max(0, total_lines + offset)
"""
    oracle_12 = """def run_oracle():
    rows = count_data_rows(100, True)
    assert rows == 99, f"Expected 99 data rows (100 - 1 header), got {rows}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Header Line Count Offset Direction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Subtract header line from line count",
        observed_behavior="Adds header line artificially inflating record count", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in pipeline database sink batch loader
    clean_sec_1 = """def bulk_insert_pipeline_records(db_cursor, table_name: str, records: list):
    allowed_tables = {"raw_events", "clean_events", "audit_log"}
    if table_name not in allowed_tables:
        raise ValueError("Invalid target table")
    query = f"INSERT INTO {table_name} (record_id, payload) VALUES (?, ?)"
    db_cursor.executemany(query, [(r['id'], r['payload']) for r in records])
"""
    mut_sec_1 = """def bulk_insert_pipeline_records(db_cursor, table_name: str, records: list):
    for r in records:
        query = f"INSERT INTO {table_name} (record_id, payload) VALUES ('{r['id']}', '{r['payload']}')"
        db_cursor.execute(query)
"""
    oracle_sec_1 = """class MockPipelineCur:
    def __init__(self):
        self.many_params = None
        self.last_query = ""
    def executemany(self, q, p):
        self.last_query = q
        self.many_params = p
    def execute(self, q):
        self.last_query = q

def run_oracle():
    cur = MockPipelineCur()
    bulk_insert_pipeline_records(cur, "raw_events", [{"id": "1", "payload": "test"}])
    assert cur.many_params is not None or "?" in cur.last_query, "Batch insert must use parameterized query placeholders"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Sink SQL Batch Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=3,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized executemany insert query",
        observed_behavior="Unsanitized string interpolation in SQL values", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in external ETL preprocessor script
    clean_sec_2 = """import subprocess
def run_etl_normalizer_binary(input_file: str, out_file: str):
    if not input_file.endswith(".csv") or ".." in input_file:
        raise ValueError("Invalid input file")
    subprocess.run(["/usr/bin/normalizer", "--in", input_file, "--out", out_file], check=True)
"""
    mut_sec_2 = """import subprocess
def run_etl_normalizer_binary(input_file: str, out_file: str):
    subprocess.run(f"/usr/bin/normalizer --in {input_file} --out {out_file}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(run_etl_normalizer_binary)
    assert "shell=True" not in src, "Must avoid shell execution in ETL normalizer"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="ETL Normalizer Subprocess Shell Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Subprocess list execution without shell",
        observed_behavior="Shell execution with unquoted file arguments", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in CSV data source directory reader
    clean_sec_3 = """import os
def load_source_csv_filepath(source_filename: str) -> str:
    base = "/app/data/sources"
    clean = os.path.basename(source_filename)
    return os.path.join(base, clean)
"""
    mut_sec_3 = """import os
def load_source_csv_filepath(source_filename: str) -> str:
    base = "/app/data/sources"
    return os.path.join(base, source_filename)
"""
    oracle_sec_3 = """def run_oracle():
    target = load_source_csv_filepath("../../etc/passwd")
    assert "/etc/passwd" not in target and ".." not in target, "Path traversal in data source loader"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Data Pipeline Source Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=3,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize source path with basename",
        observed_behavior="Direct path join allows directory traversal", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in data quality validation HTML report
    clean_sec_4 = """import html
def render_data_quality_card(col_name: str, error_msg: str) -> str:
    return f"<div class='error-card'>{html.escape(col_name)}: {html.escape(error_msg)}</div>"
"""
    mut_sec_4 = """def render_data_quality_card(col_name: str, error_msg: str) -> str:
    return f"<div class='error-card'>{col_name}: {error_msg}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_data_quality_card("<script>alert(1)</script>", "error")
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Data Quality Card HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in quality report cards",
        observed_behavior="Unescaped column name reflection allows XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on batch pipeline trigger
    clean_sec_5 = """def trigger_batch_pipeline(pipeline_id: str, caller_token: str) -> bool:
    if not caller_token:
        raise PermissionError("Unauthenticated pipeline trigger request")
    return True
"""
    mut_sec_5 = """def trigger_batch_pipeline(pipeline_id: str, caller_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        trigger_batch_pipeline("PIPE-101", "")
        assert False, "Pipeline trigger without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Trigger Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller token before starting pipeline",
        observed_behavior="Allows unauthenticated pipeline triggers", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for pipeline configuration reload
    clean_sec_6 = """def reload_pipeline_config(user_role: str, config_id: str) -> bool:
    return user_role in {"DATA_PLATFORM_ADMIN", "SITE_RELIABILITY_ENGINEER"}
"""
    mut_sec_6 = """def reload_pipeline_config(user_role: str, config_id: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert reload_pipeline_config("ANALYST", "CFG-1") is False, "Analyst cannot reload pipeline configs"
    assert reload_pipeline_config("DATA_PLATFORM_ADMIN", "CFG-1") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Config Reload Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict config reloads to data platform admins",
        observed_behavior="Grants config reload to arbitrary user roles", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear search in record primary key deduplicator
    clean_perf_1 = """def is_new_record_id(seen_set: set, rec_id: str) -> bool:
    return rec_id not in seen_set
"""
    mut_perf_1 = """def is_new_record_id(seen_list: list, rec_id: str) -> bool:
    for s in seen_list:
        if s == rec_id:
            return False
    return True
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_new_record_id)
    assert "set" in src or "in seen_set" in src, "Record ID deduplication must use set for O(1) membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Record ID Deduplication Set Membership", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) set membership check",
        observed_behavior="O(N) linear list scan", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic record lookup join
    clean_perf_2 = """def filter_valid_records(records: list, valid_id_set: set) -> list:
    return [r for r in records if r['id'] in valid_id_set]
"""
    mut_perf_2 = """def filter_valid_records(records: list, valid_id_list: list) -> list:
    res = []
    for r in records:
        found = False
        for v in valid_id_list:
            if r['id'] == v:
                found = True
                break
        if found:
            res.append(r)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_valid_records)
    assert "set" in src, "Record filter must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Record Set Filter Lookup", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based ID filtering in O(N)",
        observed_behavior="Nested linear search in O(N*M)", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive schema type resolution
    clean_perf_3 = """def resolve_nested_schema_depth(field_tree: dict, memo=None) -> int:
    if memo is None:
        memo = {}
    node_id = id(field_tree)
    if node_id in memo:
        return memo[node_id]
    children = field_tree.get("fields", [])
    if not children:
        return 1
    depth = 1 + max(resolve_nested_schema_depth(c, memo) for c in children)
    memo[node_id] = depth
    return depth
"""
    mut_perf_3 = """def resolve_nested_schema_depth(field_tree: dict, memo=None) -> int:
    children = field_tree.get("fields", [])
    if not children:
        return 1
    return 1 + max(resolve_nested_schema_depth(c) for c in children)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(resolve_nested_schema_depth)
    assert "memo" in src and "memo[" in src, "Schema tree resolution must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schema Tree Depth Resolution Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized schema DAG resolution",
        observed_behavior="Exponential re-evaluation of shared sub-schemas", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in CSV record exporter
    clean_perf_4 = """def export_records_to_csv_text(records: list) -> str:
    lines = ["id,status,score\\n"]
    for r in records:
        lines.append(f"{r['id']},{r['status']},{r['score']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def export_records_to_csv_text(records: list) -> str:
    res = "id,status,score\\n"
    for r in records:
        res = res + f"{r['id']},{r['status']},{r['score']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(export_records_to_csv_text)
    assert ".join(" in src, "CSV exporter must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="CSV Record Export Buffer Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join list buffer in O(N)",
        observed_behavior="Repeated string reallocation in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of column name sanitization regex
    clean_perf_5 = """import re
_COL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
def is_valid_column_identifier(col: str) -> bool:
    return bool(_COL_RE.match(col))
"""
    mut_perf_5 = """import re
def is_valid_column_identifier(col: str) -> bool:
    r = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
    return bool(r.match(col))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_column_identifier)
    assert "re.compile" not in src, "Column regex must be compiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Column Identifier Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles regex on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty batch rejection
    clean_reg_1 = """def process_pipeline_batch(batch: list) -> bool:
    if not batch:
        raise ValueError("Cannot process empty batch")
    return True
"""
    mut_reg_1 = """def process_pipeline_batch(batch: list) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        process_pipeline_batch([])
        assert False, "Regression: Empty batch must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Empty Batch Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty batches with ValueError",
        observed_behavior="Accepts empty batches without error", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative batch size configuration
    clean_reg_2 = """def configure_batch_size(size: int) -> bool:
    if size <= 0:
        raise ValueError("Batch size must be strictly positive")
    return True
"""
    mut_reg_2 = """def configure_batch_size(size: int) -> bool:
    return True
"""
    oracle_reg_2 = """def run_oracle():
    try:
        configure_batch_size(-50)
        assert False, "Regression: Negative batch size must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Batch Size Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative batch size",
        observed_behavior="Accepts negative batch size", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy pipeline execution ID prefix
    clean_reg_3 = """def format_pipeline_run_id(seq: int) -> str:
    return f"RUN-{seq:06d}"
"""
    mut_reg_3 = """def format_pipeline_run_id(seq: int) -> str:
    return f"{seq:06d}"
"""
    oracle_reg_3 = """def run_oracle():
    rid = format_pipeline_run_id(45)
    assert rid == "RUN-000045", f"Expected RUN-000045, got {rid}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Run ID Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include RUN- prefix",
        observed_behavior="Drops RUN- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in column names
    clean_reg_4 = """def sanitize_header_column(col: str) -> str:
    cleaned = col.strip().lower()
    if not cleaned:
        raise ValueError("Empty column header")
    return cleaned
"""
    mut_reg_4 = """def sanitize_header_column(col: str) -> str:
    return col.lower()
"""
    oracle_reg_4 = """def run_oracle():
    c = sanitize_header_column("  customer_id  ")
    assert c == "customer_id", f"Expected 'customer_id' without spaces, got '{c}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Column Header Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing column header",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on transformed record dictionary
    clean_reg_5 = """def extract_record_metadata(meta: dict, key: str) -> str:
    if meta is None:
        return ""
    return str(meta.get(key, ""))
"""
    mut_reg_5 = """def extract_record_metadata(meta: dict, key: str) -> str:
    return str(meta.get(key, ""))
"""
    oracle_reg_5 = """def run_oracle():
    assert extract_record_metadata(None, "source") == "", "None meta dict must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Record Metadata Dictionary Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None meta dictionary gracefully",
        observed_behavior="Raises AttributeError on None meta", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed pipeline completion webhook payload keys
    clean_integ_1 = """def build_pipeline_completion_event(run_id: str, row_count: int) -> dict:
    return {"pipeline_run_id": run_id, "processed_row_count": row_count, "status": "COMPLETED"}
"""
    mut_integ_1 = """def build_pipeline_completion_event(run_id: str, row_count: int) -> dict:
    return {"run_id": run_id, "rows": row_count, "status": "COMPLETED"}
"""
    oracle_integ_1 = """def run_oracle():
    ev = build_pipeline_completion_event("RUN-1", 5000)
    assert "pipeline_run_id" in ev and "processed_row_count" in ev, "Consumer expects 'pipeline_run_id' and 'processed_row_count'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pipeline Completion Payload Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified event keys",
        observed_behavior="Emits abbreviated keys breaking downstream data warehouse notifier", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs list) in dead-letter record query
    clean_integ_2 = """def fetch_dlq_entry(dlq_id: str) -> dict:
    return {"dlq_id": dlq_id, "has_error": True}
"""
    mut_integ_2 = """def fetch_dlq_entry(dlq_id: str) -> list:
    return [dlq_id, True]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_dlq_entry("DLQ-101")
    assert isinstance(res, dict) and "has_error" in res, "Consumer expects DLQ entry dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="DLQ Entry Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns plain list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in sink webhook dispatcher
    clean_integ_3 = """def build_sink_auth_headers(sink_token: str) -> dict:
    return {"X-Sink-Auth": sink_token, "Content-Type": "application/json"}
"""
    mut_integ_3 = """def build_sink_auth_headers(sink_token: str) -> dict:
    return {"Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_sink_auth_headers("sink_tok_xyz")
    assert "X-Sink-Auth" in h, "Data sink requires X-Sink-Auth header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Sink Webhook Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include X-Sink-Auth header",
        observed_behavior="Omits sink authorization header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in batch ingestion partition key
    clean_integ_4 = """def format_partition_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_partition_date(year: int, month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_partition_date(2026, 12, 10)
    assert d == "2026-12-10", f"Hive partition standard requires YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Partition Date Serialization Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted partition date breaking Parquet directory path", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Compression codec casing mismatch in pipeline sink
    clean_integ_5 = """def serialize_codec_name(codec: str) -> str:
    return codec.strip().upper()
"""
    mut_integ_5 = """def serialize_codec_name(codec: str) -> str:
    return codec.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_codec_name("snappy") == "SNAPPY", "Storage format expects uppercase SNAPPY"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Compression Codec Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase codec identifier",
        observed_behavior="Emits lowercase codec string", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened schema validation assertion: omitting nullable check
    clean_drift_1 = """def verify_schema_adherence(has_required_cols: bool, types_valid: bool) -> bool:
    return has_required_cols and types_valid
"""
    mut_drift_1 = """def verify_schema_adherence(has_required_cols: bool, types_valid: bool) -> bool:
    # Drift: loosened requirement to only check column presence, ignoring type validity
    return has_required_cols
"""
    oracle_drift_1 = """def run_oracle():
    assert verify_schema_adherence(True, False) is False, "Drift: Invalid column types must reject batch"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schema Adherence Dual Check Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both column presence and type validity",
        observed_behavior="Loosens check allowing type mismatches to pass", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping dead-letter queue routing on failure
    clean_drift_2 = """def handle_corrupted_record(rec: dict) -> dict:
    if rec.get("is_corrupted", False):
        return {"action": "ROUTE_TO_DLQ", "id": rec.get("id")}
    return {"action": "PROCESS", "id": rec.get("id")}
"""
    mut_drift_2 = """def handle_corrupted_record(rec: dict) -> dict:
    # Drift: corrupted records silently marked as processed
    return {"action": "PROCESS", "id": rec.get("id")}
"""
    oracle_drift_2 = """def run_oracle():
    res = handle_corrupted_record({"is_corrupted": True, "id": 10})
    assert res["action"] == "ROUTE_TO_DLQ", "Drift: Corrupted record must route to DLQ"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Corrupted Record DLQ Routing Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Route corrupted records to DLQ",
        observed_behavior="Silently marks corrupted records as successfully processed", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum batch memory size invariant removal
    clean_drift_3 = """def validate_batch_byte_limit(batch_bytes: int, max_bytes: int = 50000000) -> bool:
    if batch_bytes > max_bytes:
        return False
    return True
"""
    mut_drift_3 = """def validate_batch_byte_limit(batch_bytes: int, max_bytes: int = 50000000) -> bool:
    # Drift: memory limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_batch_byte_limit(100000000, 50000000) is False, "Drift: 100MB exceeds 50MB batch limit"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Batch Memory Size Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce memory ceiling for batches",
        observed_behavior="Unconditionally permits unbounded batch size", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in data throughput rate
    clean_drift_4 = """def compute_throughput_mb_s(bytes_processed: int, duration_sec: float) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    dec = (Decimal(str(bytes_processed)) / Decimal("1048576")) / Decimal(str(duration_sec))
    return float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def compute_throughput_mb_s(bytes_processed: int, duration_sec: float) -> float:
    # Drift: integer truncation of megabytes
    mb = int(bytes_processed / 1048576)
    return float(int(mb / duration_sec))
"""
    oracle_drift_4 = """def run_oracle():
    res = compute_throughput_mb_s(2621440, 2.0)
    # 2.5 MB / 2s = 1.25 MB/s
    assert res == 1.25, f"Expected 1.25 MB/s, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Throughput MB/s Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate decimal throughput calculation",
        observed_behavior="Integer truncation drops fractional throughput", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting batch size policy requirements
    clean_conv_1 = """def check_batch_sizing_policy(size: int) -> bool:
    # Harmonized policy: batch size allowed between 100 and 1000
    return 100 <= size <= 1000
"""
    mut_conv_1 = """def check_batch_sizing_policy(size: int) -> bool:
    # Invariant conflict: Policy A requires size < 80, Policy B requires size > 250
    return size < 80 and size > 250
"""
    oracle_conv_1 = """def run_oracle():
    assert check_batch_sizing_policy(500) is True, "Harmonized rule permits 500"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Batch Sizing Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid batch size range",
        observed_behavior="Mutually contradictory rules (size < 80 AND size > 250)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: corruption threshold operator
    clean_conv_2 = """def evaluate_corruption_tolerance(corrupted: int, max_tolerated: int) -> str:
    if corrupted >= max_tolerated:
        return "PIPELINE_ABORT"
    return "TOLERATED"
"""
    mut_conv_2 = """def evaluate_corruption_tolerance(corrupted: int, max_tolerated: int) -> str:
    if corrupted > max_tolerated:
        return "PIPELINE_ABORT"
    return "TOLERATED"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_corruption_tolerance(5, 5) == "PIPELINE_ABORT", "Exact tolerance limit must abort pipeline"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Corruption Tolerance Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary triggers abort",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in ETL stage execution
    clean_conv_3 = """def advance_etl_stage(stage: str) -> str:
    flow = {"EXTRACT": "TRANSFORM", "TRANSFORM": "LOAD", "LOAD": "COMMITTED", "COMMITTED": "COMMITTED"}
    return flow.get(stage, "EXTRACT")
"""
    mut_conv_3 = """def advance_etl_stage(stage: str) -> str:
    # Circular loop between TRANSFORM and EXTRACT
    flow = {"EXTRACT": "TRANSFORM", "TRANSFORM": "EXTRACT", "LOAD": "COMMITTED", "COMMITTED": "COMMITTED"}
    return flow.get(stage, "EXTRACT")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_etl_stage(advance_etl_stage("TRANSFORM"))
    assert res == "COMMITTED", "ETL progression must reach terminal COMMITTED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="ETL Stage Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to COMMITTED",
        observed_behavior="Infinite oscillation between TRANSFORM and EXTRACT",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def pipeline_clean_routine_{c_idx}(batch_val: int) -> int:
    # Clean control {c_idx}: verified pipeline transformer with boundary guard
    if batch_val < 0:
        return 0
    return (batch_val * 6) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = pipeline_clean_routine_{c_idx}(15)
    assert res == 90 + {c_idx}, f"Expected {{90 + {c_idx}}}, got {{res}}"
    assert pipeline_clean_routine_{c_idx}(-3) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Pipeline Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified pipeline calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
