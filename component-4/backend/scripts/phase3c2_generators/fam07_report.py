"""
Phase 3C.2 Family 07: Analytics Summarizers & Metrics Reporting (FAM-07-REPORT).
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
    # 1.1 Percentile calculation index rounding (nearest rank method)
    clean_code_1 = """def compute_percentile(values: list, percentile: float) -> float:
    if not values:
        return 0.0
    import math
    s = sorted(values)
    idx = math.ceil((percentile / 100.0) * len(s)) - 1
    idx = max(0, min(idx, len(s) - 1))
    return float(s[idx])
"""
    mut_code_1 = """def compute_percentile(values: list, percentile: float) -> float:
    if not values:
        return 0.0
    import math
    s = sorted(values)
    idx = math.floor((percentile / 100.0) * len(s))
    idx = max(0, min(idx, len(s) - 1))
    return float(s[idx])
"""
    oracle_1 = """def run_oracle():
    # Nearest rank for p90 of [1..10]: ceil(0.9 * 10) - 1 = 8 -> index 8 (value 9)
    res = compute_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90.0)
    assert res == 9.0, f"Expected 9.0 for 90th percentile of 10 items, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Percentile Nearest Rank Index Calculation", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="ROUNDING_DIRECTION_INVERSION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Ceiling index minus 1 for nearest rank percentile",
        observed_behavior="Floor index without subtraction shifts percentile rank", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Moving average window denominator
    clean_code_2 = """def compute_simple_moving_average(samples: list, window_size: int) -> list:
    if window_size < 1 or len(samples) < window_size:
        return []
    res = []
    for i in range(len(samples) - window_size + 1):
        window = samples[i:i + window_size]
        res.append(round(sum(window) / window_size, 2))
    return res
"""
    mut_code_2 = """def compute_simple_moving_average(samples: list, window_size: int) -> list:
    if window_size < 1 or len(samples) < window_size:
        return []
    res = []
    for i in range(len(samples) - window_size + 1):
        window = samples[i:i + window_size]
        res.append(round(sum(window) / len(samples), 2))
    return res
"""
    oracle_2 = """def run_oracle():
    sma = compute_simple_moving_average([10.0, 20.0, 30.0, 40.0], 2)
    assert sma == [15.0, 25.0, 35.0], f"Expected [15.0, 25.0, 35.0], got {sma}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Moving Average Window Denominator Error", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=7,
        mutation_op="OPERAND_SUBSTITUTION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Divide by window_size",
        observed_behavior="Divides by total dataset length", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Outlier detection via IQR multiplier
    clean_code_3 = """def is_iqr_outlier(val: float, q1: float, q3: float, k: float = 1.5) -> bool:
    iqr = q3 - q1
    lower_bound = q1 - (k * iqr)
    upper_bound = q3 + (k * iqr)
    return val < lower_bound or val > upper_bound
"""
    mut_code_3 = """def is_iqr_outlier(val: float, q1: float, q3: float, k: float = 1.5) -> bool:
    iqr = q3 - q1
    lower_bound = q1 + (k * iqr)
    upper_bound = q3 - (k * iqr)
    return val < lower_bound or val > upper_bound
"""
    oracle_3 = """def run_oracle():
    # Q1=10, Q3=20, IQR=10, Lower = 10 - 15 = -5, Upper = 20 + 15 = 35
    assert is_iqr_outlier(15.0, 10.0, 20.0, 1.5) is False, "15 is within [-5, 35]"
    assert is_iqr_outlier(40.0, 10.0, 20.0, 1.5) is True, "40 exceeds upper bound 35"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="IQR Outlier Fence Boundary Arithmetic", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="q1 - k*iqr and q3 + k*iqr",
        observed_behavior="Inverts signs narrowing fences and falsely classifying normal values as outliers", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Weighted metric average denominator
    clean_code_4 = """def compute_weighted_metric(values: list, weights: list) -> float:
    if len(values) != len(weights) or not values or sum(weights) == 0:
        return 0.0
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return round(weighted_sum / sum(weights), 2)
"""
    mut_code_4 = """def compute_weighted_metric(values: list, weights: list) -> float:
    if len(values) != len(weights) or not values or sum(weights) == 0:
        return 0.0
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return round(weighted_sum / len(values), 2)
"""
    oracle_4 = """def run_oracle():
    res = compute_weighted_metric([10.0, 20.0], [1.0, 3.0])
    # (10*1 + 20*3) / 4 = 70 / 4 = 17.5
    assert res == 17.5, f"Expected 17.5, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Weighted Average Normalization Denominator", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="OPERAND_SUBSTITUTION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Divide by sum of weights",
        observed_behavior="Divides by number of items ignoring weight scale", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Error rate percentage formula
    clean_code_5 = """def compute_error_percentage(errors: int, total_requests: int) -> float:
    if total_requests <= 0:
        return 0.0
    return round((errors / total_requests) * 100.0, 2)
"""
    mut_code_5 = """def compute_error_percentage(errors: int, total_requests: int) -> float:
    if total_requests <= 0:
        return 0.0
    return round((total_requests / errors) * 100.0, 2) if errors > 0 else 0.0
"""
    oracle_5 = """def run_oracle():
    rate = compute_error_percentage(5, 100)
    assert rate == 5.0, f"Expected 5.0% error rate, got {rate}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Error Percentage Ratio Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="OPERAND_ORDER_INVERSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Divide errors by total requests",
        observed_behavior="Inverts ratio dividing total requests by errors", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Histogram bin partitioner boundary (<= vs <)
    clean_code_6 = """def assign_histogram_bin(value: float, bin_edges: list) -> int:
    for idx, edge in enumerate(bin_edges):
        if value <= edge:
            return idx
    return len(bin_edges)
"""
    mut_code_6 = """def assign_histogram_bin(value: float, bin_edges: list) -> int:
    for idx, edge in enumerate(bin_edges):
        if value < edge:
            return idx
    return len(bin_edges)
"""
    oracle_6 = """def run_oracle():
    b = assign_histogram_bin(10.0, [10.0, 20.0, 30.0])
    assert b == 0, f"Value 10.0 matching exact first edge must fall into bin 0, got bin {b}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Histogram Edge Boundary Inequality", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Inclusive bin edge match",
        observed_behavior="Strict inequality pushes exact edge match to next bin", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Conversion funnel dropoff percentage
    clean_code_7 = """def compute_dropoff_rate(step1_count: int, step2_count: int) -> float:
    if step1_count <= 0:
        return 0.0
    lost = step1_count - step2_count
    return round((lost / step1_count) * 100.0, 2)
"""
    mut_code_7 = """def compute_dropoff_rate(step1_count: int, step2_count: int) -> float:
    if step1_count <= 0:
        return 0.0
    lost = step2_count - step1_count
    return round((lost / step1_count) * 100.0, 2)
"""
    oracle_7 = """def run_oracle():
    drop = compute_dropoff_rate(100, 80)
    assert drop == 20.0, f"Expected 20.0% dropoff, got {drop}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Funnel Dropoff Loss Subtraction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="OPERAND_SUBTRACTION_INVERSION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Calculate lost users as step1 minus step2",
        observed_behavior="Calculates step2 minus step1 producing negative dropoff", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Daily active user unique counting
    clean_code_8 = """def count_unique_active_users(user_event_log: list) -> int:
    return len(set(ev['user_id'] for ev in user_event_log))
"""
    mut_code_8 = """def count_unique_active_users(user_event_log: list) -> int:
    return len([ev['user_id'] for ev in user_event_log])
"""
    oracle_8 = """def run_oracle():
    events = [{"user_id": 1}, {"user_id": 2}, {"user_id": 1}]
    count = count_unique_active_users(events)
    assert count == 2, f"Expected 2 unique users, got {count}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="DAU Unique Set Deduplication", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATA_STRUCTURE_SUBSTITUTION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Count unique user IDs using set",
        observed_behavior="Counts raw event list without deduplication", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Throughput requests per second calculator
    clean_code_9 = """def compute_rps(total_requests: int, duration_seconds: float) -> float:
    if duration_seconds <= 0.0:
        return 0.0
    return round(total_requests / duration_seconds, 2)
"""
    mut_code_9 = """def compute_rps(total_requests: int, duration_seconds: float) -> float:
    if duration_seconds <= 0.0:
        return 0.0
    return round(duration_seconds / total_requests, 2) if total_requests > 0 else 0.0
"""
    oracle_9 = """def run_oracle():
    rps = compute_rps(500, 10.0)
    assert rps == 50.0, f"Expected 50.0 req/sec, got {rps}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Throughput Requests Ratio Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="OPERAND_ORDER_INVERSION", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Divide total requests by duration seconds",
        observed_behavior="Inverts ratio calculating seconds per request instead of RPS", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Metric threshold alert condition
    clean_code_10 = """def should_trigger_metric_alert(current_val: float, alert_threshold: float) -> bool:
    return current_val >= alert_threshold
"""
    mut_code_10 = """def should_trigger_metric_alert(current_val: float, alert_threshold: float) -> bool:
    return current_val > alert_threshold
"""
    oracle_10 = """def run_oracle():
    assert should_trigger_metric_alert(95.0, 95.0) is True, "Exact alert threshold must fire alert"
    assert should_trigger_metric_alert(94.9, 95.0) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Alert Threshold Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Trigger alert at or above threshold",
        observed_behavior="Fails to alert when metric equals threshold exactly", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Cumulative distribution fraction
    clean_code_11 = """def compute_cdf_fraction(samples: list, threshold: float) -> float:
    if not samples:
        return 0.0
    count = sum(1 for x in samples if x <= threshold)
    return round(count / len(samples), 3)
"""
    mut_code_11 = """def compute_cdf_fraction(samples: list, threshold: float) -> float:
    if not samples:
        return 0.0
    count = sum(1 for x in samples if x < threshold)
    return round(count / len(samples), 3)
"""
    oracle_11 = """def run_oracle():
    cdf = compute_cdf_fraction([10.0, 20.0, 30.0], 20.0)
    assert cdf == 0.667, f"Expected 2/3 = 0.667 for <= 20.0, got {cdf}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="CDF Inequality Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Inclusive comparison (<= threshold) for empirical CDF",
        observed_behavior="Strict inequality omits exact threshold observations", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Variance calculation degrees of freedom (N-1 vs N)
    clean_code_12 = """def compute_sample_variance(samples: list) -> float:
    n = len(samples)
    if n < 2:
        return 0.0
    mean = sum(samples) / n
    sq_diff = sum((x - mean) ** 2 for x in samples)
    return round(sq_diff / (n - 1), 3)
"""
    mut_code_12 = """def compute_sample_variance(samples: list) -> float:
    n = len(samples)
    if n < 2:
        return 0.0
    mean = sum(samples) / n
    sq_diff = sum((x - mean) ** 2 for x in samples)
    return round(sq_diff / n, 3)
"""
    oracle_12 = """def run_oracle():
    v = compute_sample_variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert v == 4.571, f"Expected sample variance with n-1 = 4.571, got {v}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Sample Variance Degrees of Freedom", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=7,
        mutation_op="DEGREES_OF_FREEDOM_BIAS", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Bessel's correction dividing by n-1 for sample variance",
        observed_behavior="Divides by n yielding biased population variance", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in analytics aggregation query
    clean_sec_1 = """def query_aggregated_metrics(db_cursor, metric_name: str):
    query = "SELECT timestamp, value FROM metrics WHERE name = ?"
    db_cursor.execute(query, (metric_name,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_aggregated_metrics(db_cursor, metric_name: str):
    query = f"SELECT timestamp, value FROM metrics WHERE name = '{metric_name}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockReportCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockReportCur()
    query_aggregated_metrics(cur, "cpu_usage' OR '1'='1")
    assert cur.params is not None, "Metric query must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Analytics Metrics Query SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized SQL query",
        observed_behavior="String interpolation allows SQL injection in analytics database", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in gnuplot report renderer
    clean_sec_2 = """import subprocess
def generate_metric_plot(plot_script: str, output_png: str):
    if not output_png.endswith(".png") or ".." in output_png:
        raise ValueError("Invalid output filename")
    subprocess.run(["gnuplot", "-e", f"set output '{output_png}'", plot_script], check=True)
"""
    mut_sec_2 = """import subprocess
def generate_metric_plot(plot_script: str, output_png: str):
    subprocess.run(f"gnuplot -e \\"set output '{output_png}'\\" {plot_script}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(generate_metric_plot)
    assert "shell=True" not in src, "Must avoid shell execution in plot generator"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Plot Generator Subprocess Shell Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Execute gnuplot with argument list without shell",
        observed_behavior="Shell execution with unquoted script path", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in CSV report export
    clean_sec_3 = """import os
def resolve_report_filepath(report_name: str) -> str:
    base = "/app/reports/exports"
    clean = os.path.basename(report_name)
    return os.path.join(base, f"{clean}.csv")
"""
    mut_sec_3 = """import os
def resolve_report_filepath(report_name: str) -> str:
    base = "/app/reports/exports"
    return os.path.join(base, f"{report_name}.csv")
"""
    oracle_sec_3 = """def run_oracle():
    target = resolve_report_filepath("../../etc/shadow")
    assert "/etc/shadow" not in target and ".." not in target, "Path traversal in report path resolution"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Report Export Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=3,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize report name using basename",
        observed_behavior="Relative directory traversal escapes reports folder", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in HTML metrics report dashboard
    clean_sec_4 = """import html
def render_metric_card(metric_label: str, val: float) -> str:
    return f"<div class='card'><span class='label'>{html.escape(metric_label)}</span>: {val}</div>"
"""
    mut_sec_4 = """def render_metric_card(metric_label: str, val: float) -> str:
    return f"<div class='card'><span class='label'>{metric_label}</span>: {val}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_metric_card("<script>alert('metric')</script>", 99.0)
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metrics Dashboard HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML in metric labels",
        observed_behavior="Unescaped label reflection allows script execution", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on report export download
    clean_sec_5 = """def download_analytics_report(report_id: str, auth_token: str) -> bool:
    if not auth_token:
        raise PermissionError("Unauthenticated report download request")
    return True
"""
    mut_sec_5 = """def download_analytics_report(report_id: str, auth_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        download_analytics_report("REP-1", "")
        assert False, "Report download without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Report Download Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller token before downloading reports",
        observed_behavior="Allows unauthenticated report downloads", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for financial summary audit report
    clean_sec_6 = """def generate_financial_audit_report(user_role: str) -> bool:
    return user_role in {"CFO", "AUDIT_OFFICER"}
"""
    mut_sec_6 = """def generate_financial_audit_report(user_role: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert generate_financial_audit_report("MARKETING_ANALYST") is False, "Analyst cannot access audit reports"
    assert generate_financial_audit_report("CFO") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Financial Audit Report Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict financial audit reports to privileged roles",
        observed_behavior="Grants audit report access to arbitrary user roles", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear search in metric tag dictionary lookup
    clean_perf_1 = """def get_metric_factor(metric_weights: dict, metric_name: str) -> float:
    return metric_weights.get(metric_name, 1.0)
"""
    mut_perf_1 = """def get_metric_factor(metric_weights_list: list, metric_name: str) -> float:
    for m in metric_weights_list:
        if m['name'] == metric_name:
            return m['factor']
    return 1.0
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(get_metric_factor)
    assert "dict" in src or "get(" in src, "Metric weight lookup must use O(1) hash map"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Weight Hash Map Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) hash map lookup",
        observed_behavior="O(N) linear list scan", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic sliding window sum calculation
    clean_perf_2 = """def compute_sliding_window_sums(values: list, k: int) -> list:
    if k <= 0 or len(values) < k:
        return []
    curr = sum(values[:k])
    res = [curr]
    for i in range(len(values) - k):
        curr = curr - values[i] + values[i + k]
        res.append(curr)
    return res
"""
    mut_perf_2 = """def compute_sliding_window_sums(values: list, k: int) -> list:
    if k <= 0 or len(values) < k:
        return []
    res = []
    for i in range(len(values) - k + 1):
        res.append(sum(values[i:i + k]))
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(compute_sliding_window_sums)
    assert "curr - values[i]" in src or "values[i + k]" in src, "Sliding window must maintain rolling O(1) delta sum"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Rolling Window Delta Sum Optimization", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="QUADRATIC_RECOMPUTATION", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="O(N) rolling window updates",
        observed_behavior="O(N*K) slice recomputations in loop", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive metric trend forecasting
    clean_perf_3 = """def forecast_trend_exponential(step: int, memo=None) -> float:
    if memo is None:
        memo = {}
    if step in memo:
        return memo[step]
    if step <= 1:
        return 10.0
    val = (forecast_trend_exponential(step - 1, memo) * 1.02) + (forecast_trend_exponential(step - 2, memo) * 0.01)
    memo[step] = val
    return val
"""
    mut_perf_3 = """def forecast_trend_exponential(step: int, memo=None) -> float:
    if step <= 1:
        return 10.0
    return (forecast_trend_exponential(step - 1) * 1.02) + (forecast_trend_exponential(step - 2) * 0.01)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(forecast_trend_exponential)
    assert "memo" in src and "memo[" in src, "Trend forecasting recurrence must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Trend Forecasting Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="O(N) memoized trend forecasting",
        observed_behavior="O(2^N) exponential recurrence", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in CSV metrics report builder
    clean_perf_4 = """def export_metrics_to_csv(rows: list) -> str:
    lines = ["timestamp,metric,value\\n"]
    for r in rows:
        lines.append(f"{r['ts']},{r['name']},{r['val']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def export_metrics_to_csv(rows: list) -> str:
    res = "timestamp,metric,value\\n"
    for r in rows:
        res = res + f"{r['ts']},{r['name']},{r['val']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(export_metrics_to_csv)
    assert ".join(" in src, "CSV builder must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="CSV Metrics Buffer Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join list buffer in O(N)",
        observed_behavior="Repeated string copies in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of metric key validation regex
    clean_perf_5 = """import re
_METRIC_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\\.]{2,50}$")
def is_valid_metric_name(name: str) -> bool:
    return bool(_METRIC_RE.match(name))
"""
    mut_perf_5 = """import re
def is_valid_metric_name(name: str) -> bool:
    r = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\\.]{2,50}$")
    return bool(r.match(name))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_metric_name)
    assert "re.compile" not in src, "Metric name regex must be compiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Name Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles regex on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty sample set rejection
    clean_reg_1 = """def calculate_average_latency(latencies: list) -> float:
    if not latencies:
        raise ValueError("Latency sample list cannot be empty")
    return sum(latencies) / len(latencies)
"""
    mut_reg_1 = """def calculate_average_latency(latencies: list) -> float:
    return sum(latencies) / len(latencies)
"""
    oracle_reg_1 = """def run_oracle():
    try:
        calculate_average_latency([])
        assert False, "Regression: Empty sample list must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Empty Latency Samples Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty latency sample lists with ValueError",
        observed_behavior="Crashes with uncaught ZeroDivisionError", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative metric observation counts
    clean_reg_2 = """def record_counter_increment(current_total: int, delta: int) -> int:
    if delta < 0:
        raise ValueError("Counter delta cannot be negative")
    return current_total + delta
"""
    mut_reg_2 = """def record_counter_increment(current_total: int, delta: int) -> int:
    return current_total + delta
"""
    oracle_reg_2 = """def run_oracle():
    try:
        record_counter_increment(100, -10)
        assert False, "Regression: Negative counter delta must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Counter Delta Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative counter increments",
        observed_behavior="Decrements monotonic counter", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy report ID prefix
    clean_reg_3 = """def format_report_id(seq: int) -> str:
    return f"REP-{seq:06d}"
"""
    mut_reg_3 = """def format_report_id(seq: int) -> str:
    return f"{seq:06d}"
"""
    oracle_reg_3 = """def run_oracle():
    rid = format_report_id(15)
    assert rid == "REP-000015", f"Expected REP-000015, got {rid}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Report ID Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include REP- prefix",
        observed_behavior="Drops REP- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in metric names
    clean_reg_4 = """def normalize_metric_name(raw_name: str) -> str:
    cleaned = raw_name.strip().lower()
    if not cleaned:
        raise ValueError("Empty metric name")
    return cleaned
"""
    mut_reg_4 = """def normalize_metric_name(raw_name: str) -> str:
    return raw_name.lower()
"""
    oracle_reg_4 = """def run_oracle():
    m = normalize_metric_name("  cpu.utilization  ")
    assert m == "cpu.utilization", f"Expected 'cpu.utilization' without spaces, got '{m}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Name Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing metric name",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on metric unit string
    clean_reg_5 = """def format_metric_display(val: float, unit: str) -> str:
    if unit is None:
        unit = "units"
    return f"{val} {unit.strip()}"
"""
    mut_reg_5 = """def format_metric_display(val: float, unit: str) -> str:
    return f"{val} {unit.strip()}"
"""
    oracle_reg_5 = """def run_oracle():
    assert format_metric_display(10.0, None) == "10.0 units", "None unit must default to 'units'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Unit Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None unit gracefully",
        observed_behavior="Raises AttributeError on None unit", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed analytics report schema keys
    clean_integ_1 = """def build_metrics_summary_payload(p50: float, p99: float, sample_count: int) -> dict:
    return {"median_p50": p50, "tail_p99": p99, "total_samples": sample_count}
"""
    mut_integ_1 = """def build_metrics_summary_payload(p50: float, p99: float, sample_count: int) -> dict:
    return {"p50": p50, "p99": p99, "count": sample_count}
"""
    oracle_integ_1 = """def run_oracle():
    p = build_metrics_summary_payload(10.0, 50.0, 1000)
    assert "median_p50" in p and "tail_p99" in p and "total_samples" in p, "Schema requires median_p50, tail_p99, total_samples"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metrics Summary Payload Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified metrics summary keys",
        observed_behavior="Emits abbreviated keys breaking downstream analytics dashboard", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs list) in anomaly report
    clean_integ_2 = """def fetch_anomalies_report(metric_name: str) -> dict:
    return {"metric": metric_name, "anomaly_count": 0}
"""
    mut_integ_2 = """def fetch_anomalies_report(metric_name: str) -> list:
    return [metric_name, 0]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_anomalies_report("cpu")
    assert isinstance(res, dict) and "anomaly_count" in res, "Consumer expects anomaly dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Anomaly Report Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns plain list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in metrics dispatcher
    clean_integ_3 = """def build_metrics_dispatch_headers(token: str) -> dict:
    return {"X-Metrics-Token": token, "Content-Type": "application/json", "X-Source": "IntelliSE-Collector"}
"""
    mut_integ_3 = """def build_metrics_dispatch_headers(token: str) -> dict:
    return {"Content-Type": "application/json", "X-Source": "IntelliSE-Collector"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_metrics_dispatch_headers("tok_analytics")
    assert "X-Metrics-Token" in h, "Metrics ingestion gateway requires X-Metrics-Token header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metrics Dispatch Token Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include X-Metrics-Token header",
        observed_behavior="Omits token header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in reporting period timestamp
    clean_integ_4 = """def format_reporting_period_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_reporting_period_date(year: int, month: int, day: int) -> str:
    return f"{day:02d}/{month:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_reporting_period_date(2026, 10, 5)
    assert d == "2026-10-05", f"Reporting standard requires YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Reporting Period Date Serialization", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Unit casing mismatch in metric ingestion client
    clean_integ_5 = """def serialize_metric_unit(unit: str) -> str:
    return unit.strip().upper()
"""
    mut_integ_5 = """def serialize_metric_unit(unit: str) -> str:
    return unit.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_metric_unit("ms") == "MS", "Metric unit must be uppercase"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Metric Unit Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase metric unit",
        observed_behavior="Emits lowercase metric unit", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened outlier verification assertion
    clean_drift_1 = """def verify_outlier_filters(iqr_passed: bool, zscore_passed: bool) -> bool:
    return iqr_passed and zscore_passed
"""
    mut_drift_1 = """def verify_outlier_filters(iqr_passed: bool, zscore_passed: bool) -> bool:
    # Drift: loosened requirement to only check IQR, ignoring Z-score
    return iqr_passed
"""
    oracle_drift_1 = """def run_oracle():
    assert verify_outlier_filters(True, False) is False, "Drift: Failed Z-score filter must reject outlier"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Outlier Dual Filter Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both IQR and Z-score outlier checks",
        observed_behavior="Loosens check allowing failed Z-score observations", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping sample size sufficiency check
    clean_drift_2 = """def compute_confident_average(samples: list, min_samples: int = 30) -> float:
    if len(samples) < min_samples:
        raise ValueError("Insufficient sample size for statistical confidence")
    return round(sum(samples) / len(samples), 2)
"""
    mut_drift_2 = """def compute_confident_average(samples: list, min_samples: int = 30) -> float:
    # Drift: sample count sufficiency check dropped
    return round(sum(samples) / len(samples), 2)
"""
    oracle_drift_2 = """def run_oracle():
    try:
        compute_confident_average([10.0, 20.0], 30)
        assert False, "Drift: Sample size below 30 must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Sample Size Sufficiency Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Require minimum 30 samples for statistical validity",
        observed_behavior="Silently drops sample size requirement", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum latency percentile upper bound invariant removal
    clean_drift_3 = """def validate_p99_sla(p99_ms: float, max_sla_ms: float = 200.0) -> bool:
    if p99_ms > max_sla_ms:
        return False
    return True
"""
    mut_drift_3 = """def validate_p99_sla(p99_ms: float, max_sla_ms: float = 200.0) -> bool:
    # Drift: SLA limit check removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_p99_sla(500.0, 200.0) is False, "Drift: 500ms p99 violates 200ms SLA"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="P99 SLA Limit Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce SLA ceiling",
        observed_behavior="Unconditionally permits unbounded latency", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in percentile calculation
    clean_drift_4 = """def compute_percentile_rounded(val: float) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    dec = Decimal(str(val))
    return float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def compute_percentile_rounded(val: float) -> float:
    # Drift: integer truncation of cents
    return float(int(val * 100) / 100.0)
"""
    oracle_drift_4 = """def run_oracle():
    res = compute_percentile_rounded(12.3456)
    assert res == 12.35, f"Expected 12.35 after half-up rounding, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Percentile Metric Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate decimal half-up rounding",
        observed_behavior="Integer truncation drops decimal fraction", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting metric reporting interval policy requirements
    clean_conv_1 = """def check_aggregation_window(window_sec: int) -> bool:
    # Harmonized policy: aggregation window allowed between 10 and 300 seconds
    return 10 <= window_sec <= 300
"""
    mut_conv_1 = """def check_aggregation_window(window_sec: int) -> bool:
    # Invariant conflict: Policy A requires window < 5, Policy B requires window > 20
    return window_sec < 5 and window_sec > 20
"""
    oracle_conv_1 = """def run_oracle():
    assert check_aggregation_window(60) is True, "Harmonized rule permits 60s window"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Aggregation Window Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid aggregation window range",
        observed_behavior="Mutually contradictory rules (window < 5 AND window > 20)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: anomaly score threshold operator
    clean_conv_2 = """def evaluate_anomaly_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return "ANOMALY_CONFIRMED"
    return "NORMAL"
"""
    mut_conv_2 = """def evaluate_anomaly_score(score: float, threshold: float) -> str:
    if score > threshold:
        return "ANOMALY_CONFIRMED"
    return "NORMAL"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_anomaly_score(3.0, 3.0) == "ANOMALY_CONFIRMED", "Exact score must be ANOMALY_CONFIRMED"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Anomaly Score Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary is confirmed anomaly",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in report generation lifecycle
    clean_conv_3 = """def advance_report_generation(state: str) -> str:
    flow = {"REQUESTED": "COMPUTING", "COMPUTING": "READY", "READY": "READY"}
    return flow.get(state, "REQUESTED")
"""
    mut_conv_3 = """def advance_report_generation(state: str) -> str:
    # Circular loop between COMPUTING and REQUESTED
    flow = {"REQUESTED": "COMPUTING", "COMPUTING": "REQUESTED", "READY": "READY"}
    return flow.get(state, "REQUESTED")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_report_generation(advance_report_generation("REQUESTED"))
    assert res == "READY", "Report generation must reach terminal READY state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Report Generation State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to READY",
        observed_behavior="Infinite oscillation between REQUESTED and COMPUTING",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def report_clean_routine_{c_idx}(val: float) -> float:
    # Clean control {c_idx}: verified metrics aggregation helper with boundary guard
    if val < 0.0:
        return 0.0
    return round((val * 1.5) + {c_idx}, 2)
"""
        oracle_c = f"""def run_oracle():
    res = report_clean_routine_{c_idx}(10.0)
    assert res == 15.0 + {c_idx}, f"Expected {{15.0 + {c_idx}}}, got {{res}}"
    assert report_clean_routine_{c_idx}(-5.0) == 0.0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Report Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified reporting calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
