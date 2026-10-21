"""
Phase 3C.2 Family 08: Job Scheduling, Calendar & Cron (FAM-08-SCHEDULE).
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
    # 1.1 Time interval overlap check (start < end)
    clean_code_1 = """def has_interval_conflict(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)
"""
    mut_code_1 = """def has_interval_conflict(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) <= min(end_a, end_b)
"""
    oracle_1 = """def run_oracle():
    # Back-to-back intervals: [10, 20] and [20, 30] do NOT overlap
    assert has_interval_conflict(10, 20, 20, 30) is False, "Adjacent intervals sharing endpoint do not conflict"
    assert has_interval_conflict(10, 25, 20, 30) is True, "Overlapping intervals must conflict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schedule Interval Conflict Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Strict inequality for interval overlap",
        observed_behavior="Uses <= flagging back-to-back adjacent intervals as conflicts", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Cron hourly interval step calculation
    clean_code_2 = """def compute_next_cron_run(current_hour: int, step_hours: int) -> int:
    if step_hours <= 0:
        return current_hour
    return (current_hour + step_hours) % 24
"""
    mut_code_2 = """def compute_next_cron_run(current_hour: int, step_hours: int) -> int:
    if step_hours <= 0:
        return current_hour
    return (current_hour - step_hours) % 24
"""
    oracle_2 = """def run_oracle():
    next_h = compute_next_cron_run(22, 4)
    assert next_h == 2, f"Expected hour 2 (22+4 mod 24), got {next_h}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cron Step Hour Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Add step hours to current hour",
        observed_behavior="Subtracts step hours moving backwards in time", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Recurrence count loop termination
    clean_code_3 = """def generate_recurrence_dates(start_day: int, step_days: int, count: int) -> list:
    return [start_day + (i * step_days) for i in range(count)]
"""
    mut_code_3 = """def generate_recurrence_dates(start_day: int, step_days: int, count: int) -> list:
    return [start_day + (i * step_days) for i in range(count - 1)]
"""
    oracle_3 = """def run_oracle():
    dates = generate_recurrence_dates(1, 7, 3)
    assert len(dates) == 3 and dates == [1, 8, 15], f"Expected 3 dates [1, 8, 15], got {dates}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Recurrence Event Count Loop Termination", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OFF_BY_ONE_COUNT", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Generate exact count of occurrences",
        observed_behavior="Generates count - 1 occurrences dropping final event", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Maintenance window containment validator
    clean_code_4 = """def is_within_maintenance_window(job_start: int, job_end: int, win_start: int, win_end: int) -> bool:
    return job_start >= win_start and job_end <= win_end
"""
    mut_code_4 = """def is_within_maintenance_window(job_start: int, job_end: int, win_start: int, win_end: int) -> bool:
    return job_start >= win_start or job_end <= win_end
"""
    oracle_4 = """def run_oracle():
    assert is_within_maintenance_window(10, 50, 10, 30) is False, "Job ending at 50 exceeds window ending at 30"
    assert is_within_maintenance_window(12, 28, 10, 30) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Maintenance Window Compound Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Require both start AND end to fit inside window",
        observed_behavior="Uses OR permitting jobs that extend past window close", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Worker pool capacity allocation
    clean_code_5 = """def can_dispatch_job(active_workers: int, pool_size: int, required_workers: int) -> bool:
    return (active_workers + required_workers) <= pool_size
"""
    mut_code_5 = """def can_dispatch_job(active_workers: int, pool_size: int, required_workers: int) -> bool:
    return (active_workers + required_workers) < pool_size
"""
    oracle_5 = """def run_oracle():
    assert can_dispatch_job(8, 10, 2) is True, "Exact pool capacity allocation is allowed"
    assert can_dispatch_job(8, 10, 3) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Worker Pool Allocation Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Allow exact pool saturation",
        observed_behavior="Rejects dispatch when job reaches exact pool capacity", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Task retry delay with exponential base
    clean_code_6 = """def compute_task_retry_delay(attempt: int, base_sec: int = 5) -> int:
    return base_sec * (2 ** max(0, attempt - 1))
"""
    mut_code_6 = """def compute_task_retry_delay(attempt: int, base_sec: int = 5) -> int:
    return base_sec + (2 ** max(0, attempt - 1))
"""
    oracle_6 = """def run_oracle():
    delay = compute_task_retry_delay(3, 5)
    # 5 * (2^2) = 20
    assert delay == 20, f"Expected 20s retry delay, got {delay}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Task Retry Delay Arithmetic Operator", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Multiply base seconds by exponential factor",
        observed_behavior="Adds exponential factor instead of multiplying", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Missed job backfill planner
    clean_code_7 = """def plan_missed_runs(last_run: int, current_time: int, interval: int) -> list:
    if interval <= 0 or current_time <= last_run:
        return []
    runs = []
    t = last_run + interval
    while t <= current_time:
        runs.append(t)
        t += interval
    return runs
"""
    mut_code_7 = """def plan_missed_runs(last_run: int, current_time: int, interval: int) -> list:
    if interval <= 0 or current_time <= last_run:
        return []
    runs = []
    t = last_run + interval
    while t < current_time:
        runs.append(t)
        t += interval
    return runs
"""
    oracle_7 = """def run_oracle():
    res = plan_missed_runs(100, 160, 20)
    assert res == [120, 140, 160], f"Expected runs including exact current_time 160, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Backfill Loop Upper Bound Inequality", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=7,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Include run matching exact current time",
        observed_behavior="Drops run scheduled at exact current time", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Calendar reminder notification offset
    clean_code_8 = """def compute_reminder_timestamp(event_time: int, minutes_before: int) -> int:
    return event_time - (minutes_before * 60)
"""
    mut_code_8 = """def compute_reminder_timestamp(event_time: int, minutes_before: int) -> int:
    return event_time + (minutes_before * 60)
"""
    oracle_8 = """def run_oracle():
    rem = compute_reminder_timestamp(3600, 15)
    assert rem == 2700, f"Expected reminder at 2700s (15 min prior), got {rem}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Reminder Lead Time Arithmetic Direction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Subtract reminder offset from event time",
        observed_behavior="Adds offset scheduling reminder after the event", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Timezone UTC offset conversion
    clean_code_9 = """def convert_to_utc(local_hour: int, tz_offset_hours: int) -> int:
    return (local_hour - tz_offset_hours) % 24
"""
    mut_code_9 = """def convert_to_utc(local_hour: int, tz_offset_hours: int) -> int:
    return (local_hour + tz_offset_hours) % 24
"""
    oracle_9 = """def run_oracle():
    # Local 15:00 in UTC+5 is 10:00 UTC
    utc = convert_to_utc(15, 5)
    assert utc == 10, f"Expected 10:00 UTC, got {utc}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Timezone Offset Subtraction Direction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Subtract positive timezone offset to reach UTC",
        observed_behavior="Adds offset shifting time in opposite direction", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Queue job priority sorting order
    clean_code_10 = """def prioritize_job_queue(jobs: list) -> list:
    # Lower priority number means higher precedence
    return sorted(jobs, key=lambda j: (j.get("priority", 10), j.get("created_at", 0)))
"""
    mut_code_10 = """def prioritize_job_queue(jobs: list) -> list:
    return sorted(jobs, key=lambda j: (-j.get("priority", 10), j.get("created_at", 0)))
"""
    oracle_10 = """def run_oracle():
    j1 = {"id": 1, "priority": 1, "created_at": 100}
    j2 = {"id": 2, "priority": 5, "created_at": 50}
    res = prioritize_job_queue([j2, j1])
    assert res[0]["id"] == 1, "Priority 1 must be dispatched before priority 5"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Queue Priority Sort Order", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SORT_ORDER_INVERSION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Ascending sort on priority rank",
        observed_behavior="Inverts priority rank processing lowest priority jobs first", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Job deadline expiration check
    clean_code_11 = """def is_job_deadline_passed(deadline: int, current_time: int) -> bool:
    return current_time > deadline
"""
    mut_code_11 = """def is_job_deadline_passed(deadline: int, current_time: int) -> bool:
    return current_time < deadline
"""
    oracle_11 = """def run_oracle():
    assert is_job_deadline_passed(100, 150) is True, "Current time 150 passed deadline 100"
    assert is_job_deadline_passed(200, 150) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Deadline Temporal Inequality", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_INVERSION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Deadline passed when current > deadline",
        observed_behavior="Inverts check treating active jobs as expired", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Cron day of week range parser (0-6)
    clean_code_12 = """def is_valid_cron_dow(dow: int) -> bool:
    return 0 <= dow <= 6
"""
    mut_code_12 = """def is_valid_cron_dow(dow: int) -> bool:
    return 0 <= dow < 6
"""
    oracle_12 = """def run_oracle():
    assert is_valid_cron_dow(6) is True, "Saturday (dow 6) is a valid day of week"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cron Day-of-Week Upper Bound", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Allow dow 6 (Saturday)",
        observed_behavior="Rejects dow 6", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in job execution history query
    clean_sec_1 = """def query_job_runs(db_cursor, job_id: str):
    query = "SELECT run_id, status, duration FROM job_runs WHERE job_id = ?"
    db_cursor.execute(query, (job_id,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_job_runs(db_cursor, job_id: str):
    query = f"SELECT run_id, status, duration FROM job_runs WHERE job_id = '{job_id}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockSchedCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockSchedCur()
    query_job_runs(cur, "JOB-10' OR '1'='1")
    assert cur.params is not None, "Job history query must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Execution History Query SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized SQL query",
        observed_behavior="String interpolation allows SQL injection in scheduler database", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in cron worker binary dispatcher
    clean_sec_2 = """import subprocess
def execute_scheduled_binary(task_name: str, config_arg: str):
    if not task_name.isalnum():
        raise ValueError("Invalid task name")
    subprocess.run(["/usr/local/bin/worker", "--task", task_name, "--config", config_arg], check=True)
"""
    mut_sec_2 = """import subprocess
def execute_scheduled_binary(task_name: str, config_arg: str):
    subprocess.run(f"/usr/local/bin/worker --task {task_name} --config {config_arg}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(execute_scheduled_binary)
    assert "shell=True" not in src, "Must avoid shell execution in worker dispatcher"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Worker Subprocess Command Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Subprocess list execution without shell",
        observed_behavior="Shell execution with unquoted parameters", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in schedule configuration YAML loader
    clean_sec_3 = """import os
def load_schedule_yaml(schedule_name: str) -> str:
    base = "/app/schedules"
    clean = os.path.basename(schedule_name)
    return os.path.join(base, f"{clean}.yaml")
"""
    mut_sec_3 = """import os
def load_schedule_yaml(schedule_name: str) -> str:
    base = "/app/schedules"
    return os.path.join(base, f"{schedule_name}.yaml")
"""
    oracle_sec_3 = """def run_oracle():
    target = load_schedule_yaml("../../etc/crontab")
    assert "/etc/crontab" not in target and ".." not in target, "Path traversal in schedule loader"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schedule Configuration Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=3,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize schedule file path with basename",
        observed_behavior="Direct join allows directory traversal", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in scheduled event calendar title display
    clean_sec_4 = """import html
def render_event_pill(title: str, hour: int) -> str:
    return f"<div class='event-pill'>{html.escape(title)} at {hour}:00</div>"
"""
    mut_sec_4 = """def render_event_pill(title: str, hour: int) -> str:
    return f"<div class='event-pill'>{title} at {hour}:00</div>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_event_pill("<script>alert('schedule')</script>", 10)
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Calendar Event Pill HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML in event titles",
        observed_behavior="Unescaped reflection allows XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on manual trigger job execution
    clean_sec_5 = """def trigger_immediate_job(job_id: str, caller_token: str) -> bool:
    if not caller_token:
        raise PermissionError("Unauthenticated job trigger request")
    return True
"""
    mut_sec_5 = """def trigger_immediate_job(job_id: str, caller_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        trigger_immediate_job("CRON-101", "")
        assert False, "Triggering job without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Manual Job Trigger Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller token before triggering jobs",
        observed_behavior="Allows unauthenticated manual job execution", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for worker pool pause action
    clean_sec_6 = """def pause_worker_pool(user_role: str, pool_id: str) -> bool:
    return user_role in {"DEVOPS_ENGINEER", "CLUSTER_ADMIN"}
"""
    mut_sec_6 = """def pause_worker_pool(user_role: str, pool_id: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert pause_worker_pool("DEVELOPER", "POOL-1") is False, "Standard developer cannot pause worker pools"
    assert pause_worker_pool("CLUSTER_ADMIN", "POOL-1") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Worker Pool Pause Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict worker pool pause to cluster administrators",
        observed_behavior="Grants worker pause action to arbitrary caller roles", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear search in job priority lookup table
    clean_perf_1 = """def get_queue_timeout(priority_map: dict, priority: str) -> int:
    return priority_map.get(priority, 60)
"""
    mut_perf_1 = """def get_queue_timeout(priority_list: list, priority: str) -> int:
    for p in priority_list:
        if p['name'] == priority:
            return p['timeout']
    return 60
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(get_queue_timeout)
    assert "dict" in src or "get(" in src, "Priority timeout lookup must use O(1) hash map"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Queue Priority Hash Map Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) hash map timeout lookup",
        observed_behavior="O(N) linear list search", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic schedule overlap conflict search
    clean_perf_2 = """def filter_available_slots(requested_slots: list, busy_set: set) -> list:
    return [s for s in requested_slots if s not in busy_set]
"""
    mut_perf_2 = """def filter_available_slots(requested_slots: list, busy_list: list) -> list:
    res = []
    for s in requested_slots:
        found = False
        for b in busy_list:
            if s == b:
                found = True
                break
        if not found:
            res.append(s)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_available_slots)
    assert "set" in src, "Slot availability check must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Available Slot Set Membership Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based slot filtering in linear time",
        observed_behavior="Nested list scan in O(N*M)", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive calendar recurrence expansion
    clean_perf_3 = """def expand_recurrence_tree(depth: int, memo=None) -> int:
    if memo is None:
        memo = {}
    if depth in memo:
        return memo[depth]
    if depth <= 1:
        return 1
    val = expand_recurrence_tree(depth - 1, memo) + expand_recurrence_tree(depth - 2, memo)
    memo[depth] = val
    return val
"""
    mut_perf_3 = """def expand_recurrence_tree(depth: int, memo=None) -> int:
    if depth <= 1:
        return 1
    return expand_recurrence_tree(depth - 1) + expand_recurrence_tree(depth - 2)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(expand_recurrence_tree)
    assert "memo" in src and "memo[" in src, "Recurrence expansion must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Recurrence Tree Expansion Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized recurrence expansion in O(N)",
        observed_behavior="O(2^N) exponential recursion", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in schedule export builder
    clean_perf_4 = """def export_schedule_entries(entries: list) -> str:
    lines = ["SCHEDULE MANIFEST\\n"]
    for e in entries:
        lines.append(f"{e['job_id']}:{e['cron']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def export_schedule_entries(entries: list) -> str:
    res = "SCHEDULE MANIFEST\\n"
    for e in entries:
        res = res + f"{e['job_id']}:{e['cron']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(export_schedule_entries)
    assert ".join(" in src, "Schedule exporter must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schedule Buffer String Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join list buffer in O(N)",
        observed_behavior="Repeated string copies in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of cron expression syntax regex
    clean_perf_5 = """import re
_CRON_FIELD_RE = re.compile(r"^(\\*|\\d+)(/\\d+)?$")
def is_valid_cron_field(val: str) -> bool:
    return bool(_CRON_FIELD_RE.match(val))
"""
    mut_perf_5 = """import re
def is_valid_cron_field(val: str) -> bool:
    r = re.compile(r"^(\\*|\\d+)(/\\d+)?$")
    return bool(r.match(val))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_cron_field)
    assert "re.compile" not in src, "Cron regex must be compiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cron Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles regex on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty job title guard
    clean_reg_1 = """def create_scheduled_job(job_name: str) -> bool:
    if not job_name or not job_name.strip():
        raise ValueError("Job name cannot be blank")
    return True
"""
    mut_reg_1 = """def create_scheduled_job(job_name: str) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        create_scheduled_job("   ")
        assert False, "Regression: Blank job name must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Blank Job Name Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty job names with ValueError",
        observed_behavior="Accepts blank job names", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative interval duration
    clean_reg_2 = """def set_job_interval(interval_sec: int) -> bool:
    if interval_sec <= 0:
        raise ValueError("Interval must be strictly positive")
    return True
"""
    mut_reg_2 = """def set_job_interval(interval_sec: int) -> bool:
    return True
"""
    oracle_reg_2 = """def run_oracle():
    try:
        set_job_interval(-60)
        assert False, "Regression: Negative interval must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Interval Duration Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative interval seconds",
        observed_behavior="Accepts negative interval duration", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy job ID prefix
    clean_reg_3 = """def format_job_identifier(seq: int) -> str:
    return f"JOB-{seq:06d}"
"""
    mut_reg_3 = """def format_job_identifier(seq: int) -> str:
    return f"{seq:06d}"
"""
    oracle_reg_3 = """def run_oracle():
    jid = format_job_identifier(88)
    assert jid == "JOB-000088", f"Expected JOB-000088, got {jid}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Identifier Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include JOB- prefix",
        observed_behavior="Drops JOB- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in cron expressions
    clean_reg_4 = """def normalize_cron_expression(expr: str) -> str:
    cleaned = " ".join(expr.strip().split())
    if not cleaned:
        raise ValueError("Empty cron expression")
    return cleaned
"""
    mut_reg_4 = """def normalize_cron_expression(expr: str) -> str:
    return expr
"""
    oracle_reg_4 = """def run_oracle():
    res = normalize_cron_expression("  */5   *   *   *   *  ")
    assert res == "*/5 * * * *", f"Expected normalized single spaces, got '{res}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cron Expression Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Normalize internal and surrounding whitespace",
        observed_behavior="Preserves arbitrary whitespace", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on task parameter dictionary
    clean_reg_5 = """def extract_task_argument(args: dict, key: str) -> str:
    if args is None:
        return ""
    return str(args.get(key, ""))
"""
    mut_reg_5 = """def extract_task_argument(args: dict, key: str) -> str:
    return str(args.get(key, ""))
"""
    oracle_reg_5 = """def run_oracle():
    assert extract_task_argument(None, "timeout") == "", "None args dict must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Task Parameter Dictionary Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None args dictionary gracefully",
        observed_behavior="Raises AttributeError on None args", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed schedule trigger payload keys
    clean_integ_1 = """def build_job_trigger_payload(job_id: str, run_epoch: int) -> dict:
    return {"job_identifier": job_id, "trigger_epoch": run_epoch, "action": "RUN"}
"""
    mut_integ_1 = """def build_job_trigger_payload(job_id: str, run_epoch: int) -> dict:
    return {"id": job_id, "epoch": run_epoch, "action": "RUN"}
"""
    oracle_integ_1 = """def run_oracle():
    p = build_job_trigger_payload("J-1", 1700000000)
    assert "job_identifier" in p and "trigger_epoch" in p, "Trigger consumer expects 'job_identifier' and 'trigger_epoch'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Trigger Payload Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified trigger payload keys",
        observed_behavior="Emits renamed keys breaking worker executor", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs tuple) in job status query
    clean_integ_2 = """def fetch_job_state(job_id: str) -> dict:
    return {"job_id": job_id, "is_active": True}
"""
    mut_integ_2 = """def fetch_job_state(job_id: str) -> tuple:
    return (job_id, True)
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_job_state("J-101")
    assert isinstance(res, dict) and "is_active" in res, "Consumer expects state dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job State Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns plain tuple", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in worker heartbeat dispatcher
    clean_integ_3 = """def build_heartbeat_headers(worker_token: str) -> dict:
    return {"X-Worker-Token": worker_token, "Content-Type": "application/json"}
"""
    mut_integ_3 = """def build_heartbeat_headers(worker_token: str) -> dict:
    return {"Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_heartbeat_headers("worker_tok_123")
    assert "X-Worker-Token" in h, "Scheduler receiver requires X-Worker-Token header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Worker Heartbeat Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include X-Worker-Token header",
        observed_behavior="Omits token header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in scheduled execution timestamp
    clean_integ_4 = """def format_scheduled_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_scheduled_date(year: int, month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_scheduled_date(2026, 11, 23)
    assert d == "2026-11-23", f"Scheduler standard requires YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Scheduled Execution Date Serialization", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Priority casing mismatch in job dispatch client
    clean_integ_5 = """def serialize_job_priority(priority: str) -> str:
    return priority.strip().upper()
"""
    mut_integ_5 = """def serialize_job_priority(priority: str) -> str:
    return priority.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_job_priority("high") == "HIGH", "Scheduler protocol requires uppercase priority"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Priority Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase priority string",
        observed_behavior="Emits lowercase priority string", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened overlap detection assertion
    clean_drift_1 = """def verify_schedule_safety(no_overlap: bool, resources_available: bool) -> bool:
    return no_overlap and resources_available
"""
    mut_drift_1 = """def verify_schedule_safety(no_overlap: bool, resources_available: bool) -> bool:
    # Drift: loosened requirement to only check resource counts, ignoring overlap conflicts
    return resources_available
"""
    oracle_drift_1 = """def run_oracle():
    assert verify_schedule_safety(False, True) is False, "Drift: Overlapping schedule must reject dispatch"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schedule Safety Dual Check Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both non-overlapping schedule and resources",
        observed_behavior="Loosens check allowing schedule collisions to pass", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping recurrence count guard
    clean_drift_2 = """def expand_bounded_recurrence(count: int, max_limit: int = 100) -> int:
    if count > max_limit:
        raise ValueError("Exceeds maximum allowed recurrence iterations")
    return count
"""
    mut_drift_2 = """def expand_bounded_recurrence(count: int, max_limit: int = 100) -> int:
    # Drift: max limit check dropped
    return count
"""
    oracle_drift_2 = """def run_oracle():
    try:
        expand_bounded_recurrence(500, 100)
        assert False, "Drift: Count above max_limit must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Recurrence Expansion Bound Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Reject unbounded recurrence counts",
        observed_behavior="Silently permits unbounded iteration count", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum concurrent jobs invariant removal
    clean_drift_3 = """def validate_max_concurrent_jobs(running_jobs: int, max_allowed: int = 10) -> bool:
    if running_jobs >= max_allowed:
        return False
    return True
"""
    mut_drift_3 = """def validate_max_concurrent_jobs(running_jobs: int, max_allowed: int = 10) -> bool:
    # Drift: max concurrent limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_max_concurrent_jobs(15, 10) is False, "Drift: 15 active jobs exceeds limit of 10"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Max Concurrent Jobs Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce concurrent job ceiling",
        observed_behavior="Unconditionally permits unbounded active jobs", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in cron schedule interval
    clean_drift_4 = """def compute_interval_seconds(minutes: float) -> int:
    from decimal import Decimal, ROUND_HALF_UP
    dec = Decimal(str(minutes)) * Decimal("60")
    return int(dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def compute_interval_seconds(minutes: float) -> int:
    # Drift: integer truncation of minutes before multiplying
    return int(minutes) * 60
"""
    oracle_drift_4 = """def run_oracle():
    res = compute_interval_seconds(2.5)
    assert res == 150, f"Expected 150 seconds for 2.5 min, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Schedule Interval Seconds Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate seconds calculation for fractional minutes",
        observed_behavior="Integer truncation drops 30 seconds", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting schedule duration policy requirements
    clean_conv_1 = """def check_schedule_duration_policy(duration_sec: int) -> bool:
    # Harmonized policy: task duration allowed between 60 and 1800 seconds
    return 60 <= duration_sec <= 1800
"""
    mut_conv_1 = """def check_schedule_duration_policy(duration_sec: int) -> bool:
    # Invariant conflict: Policy A requires duration < 50, Policy B requires duration > 200
    return duration_sec < 50 and duration_sec > 200
"""
    oracle_conv_1 = """def run_oracle():
    assert check_schedule_duration_policy(300) is True, "Harmonized rule permits 300s duration"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Task Duration Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid task duration range",
        observed_behavior="Mutually contradictory rules (duration < 50 AND duration > 200)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: retry quota threshold operator
    clean_conv_2 = """def evaluate_retry_quota(retries: int, max_retries: int) -> str:
    if retries >= max_retries:
        return "RETRIES_EXHAUSTED"
    return "CAN_RETRY"
"""
    mut_conv_2 = """def evaluate_retry_quota(retries: int, max_retries: int) -> str:
    if retries > max_retries:
        return "RETRIES_EXHAUSTED"
    return "CAN_RETRY"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_retry_quota(3, 3) == "RETRIES_EXHAUSTED", "Exact max retries must exhaust quota"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Retry Quota Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary marks retries as exhausted",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in job runner state machine
    clean_conv_3 = """def advance_job_state(state: str) -> str:
    flow = {"PENDING": "SCHEDULED", "SCHEDULED": "RUNNING", "RUNNING": "FINISHED", "FINISHED": "FINISHED"}
    return flow.get(state, "PENDING")
"""
    mut_conv_3 = """def advance_job_state(state: str) -> str:
    # Circular loop between RUNNING and SCHEDULED
    flow = {"PENDING": "SCHEDULED", "SCHEDULED": "RUNNING", "RUNNING": "SCHEDULED", "FINISHED": "FINISHED"}
    return flow.get(state, "PENDING")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_job_state(advance_job_state("SCHEDULED"))
    assert res == "FINISHED", "Job state progression must reach terminal FINISHED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Job Runner State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to FINISHED",
        observed_behavior="Infinite oscillation between SCHEDULED and RUNNING",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def schedule_clean_routine_{c_idx}(duration_val: int) -> int:
    # Clean control {c_idx}: verified schedule helper with boundary guard
    if duration_val < 0:
        return 0
    return (duration_val * 5) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = schedule_clean_routine_{c_idx}(20)
    assert res == 100 + {c_idx}, f"Expected {{100 + {c_idx}}}, got {{res}}"
    assert schedule_clean_routine_{c_idx}(-4) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Schedule Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified scheduling calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
