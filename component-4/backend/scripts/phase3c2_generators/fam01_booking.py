"""
Phase 3C.2 Family 01: Booking & Reservation Workflows (FAM-01-BOOKING).
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
    # 1.1 Overbooking capacity check off-by-one (> vs >=)
    clean_code_1 = """def book_room(capacity: int, current_bookings: int, requested: int) -> bool:
    if current_bookings + requested > capacity:
        return False
    return True
"""
    mut_code_1 = """def book_room(capacity: int, current_bookings: int, requested: int) -> bool:
    if current_bookings + requested >= capacity:
        return False
    return True
"""
    oracle_1 = """def run_oracle():
    assert book_room(10, 8, 2) is True, "Exact capacity booking should be allowed"
    assert book_room(10, 8, 3) is False, "Overbooking should be rejected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Booking Capacity Boundary Evaluation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Allow booking up to exact maximum capacity",
        observed_behavior="Rejects booking when current + requested equals exact capacity", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Cancellation refund window calculation
    clean_code_2 = """def calculate_cancellation_refund(days_before: int, total_amount: float) -> float:
    if days_before >= 14:
        return total_amount * 1.0
    elif days_before >= 7:
        return total_amount * 0.5
    return 0.0
"""
    mut_code_2 = """def calculate_cancellation_refund(days_before: int, total_amount: float) -> float:
    if days_before > 14:
        return total_amount * 1.0
    elif days_before >= 7:
        return total_amount * 0.5
    return 0.0
"""
    oracle_2 = """def run_oracle():
    assert calculate_cancellation_refund(14, 200.0) == 200.0, "14 days exactly gets 100% refund"
    assert calculate_cancellation_refund(7, 200.0) == 100.0, "7 days exactly gets 50% refund"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cancellation Refund Tier Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="BOUNDARY_CONDITION_MUTATION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="14 days notice yields full refund",
        observed_behavior="14 days notice yields only 50% refund due to strict inequality", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 High season surcharge multiplier
    clean_code_3 = """def calculate_nightly_rate(base_rate: float, is_peak_season: bool, nights: int) -> float:
    multiplier = 1.25 if is_peak_season else 1.0
    return base_rate * multiplier * nights
"""
    mut_code_3 = """def calculate_nightly_rate(base_rate: float, is_peak_season: bool, nights: int) -> float:
    multiplier = 1.25 if is_peak_season else 1.0
    return base_rate * multiplier + nights
"""
    oracle_3 = """def run_oracle():
    res = calculate_nightly_rate(100.0, True, 3)
    assert res == 375.0, f"Expected 375.0, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Peak Season Multiplier Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Multiply rate by total nights",
        observed_behavior="Adds nights instead of multiplying", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Room upgrade tier availability
    clean_code_4 = """def select_upgrade_tier(guest_points: int, requested_tier: str) -> str:
    tiers = {"STANDARD": 0, "DELUXE": 500, "SUITE": 1500}
    required = tiers.get(requested_tier, 999999)
    if guest_points >= required:
        return requested_tier
    return "STANDARD"
"""
    mut_code_4 = """def select_upgrade_tier(guest_points: int, requested_tier: str) -> str:
    tiers = {"STANDARD": 0, "DELUXE": 500, "SUITE": 1500}
    required = tiers.get(requested_tier, 0)
    if guest_points >= required:
        return requested_tier
    return "STANDARD"
"""
    oracle_4 = """def run_oracle():
    assert select_upgrade_tier(100, "PRESIDENTIAL") == "STANDARD", "Unknown tier should default to STANDARD"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Room Upgrade Default Fallback", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="FALLBACK_VALUE_CORRUPTION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Unknown tiers rejected when guest points insufficient",
        observed_behavior="Unknown tiers granted with 0 points threshold", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Flight seat reservation lock
    clean_code_5 = """def reserve_seats(seat_map: dict, requested_seats: list) -> bool:
    for seat in requested_seats:
        if seat_map.get(seat, False):
            return False
    for seat in requested_seats:
        seat_map[seat] = True
    return True
"""
    mut_code_5 = """def reserve_seats(seat_map: dict, requested_seats: list) -> bool:
    for seat in requested_seats:
        if seat_map.get(seat, False):
            return False
        seat_map[seat] = True
    return True
"""
    oracle_5 = """def run_oracle():
    seats = {"12A": False, "12B": True}
    res = reserve_seats(seats, ["12A", "12B"])
    assert res is False, "Partial conflict must reject reservation"
    assert seats["12A"] is False, "Conflicted batch must not partially mutate state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Atomicity in Seat Reservation", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="PREMATURE_STATE_MUTATION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="All-or-nothing seat reservation",
        observed_behavior="Partial allocation leaves state corrupted on collision", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Child guest discount calculation
    clean_code_6 = """def calculate_guest_charges(base_price: float, adults: int, children: int) -> float:
    if adults < 1:
        raise ValueError("At least one adult required")
    child_rate = base_price * 0.5
    return (adults * base_price) + (children * child_rate)
"""
    mut_code_6 = """def calculate_guest_charges(base_price: float, adults: int, children: int) -> float:
    if adults < 1:
        raise ValueError("At least one adult required")
    child_rate = base_price * 0.5
    return (adults * base_price) - (children * child_rate)
"""
    oracle_6 = """def run_oracle():
    total = calculate_guest_charges(100.0, 1, 2)
    assert total == 200.0, f"Expected 200.0, got {total}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Guest Price Aggregation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="INVERTED_AGGREGATION_OPERATOR", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Add child charges to total",
        observed_behavior="Subtracts child charges from total", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Promotional coupon code validation
    clean_code_7 = """def apply_promo_code(total: float, code: str) -> float:
    discounts = {"SUMMER20": 0.20, "VIP10": 0.10}
    if code in discounts:
        return total * (1.0 - discounts[code])
    return total
"""
    mut_code_7 = """def apply_promo_code(total: float, code: str) -> float:
    discounts = {"SUMMER20": 0.20, "VIP10": 0.10}
    if code in discounts:
        return total * discounts[code]
    return total
"""
    oracle_7 = """def run_oracle():
    res = apply_promo_code(100.0, "SUMMER20")
    assert res == 80.0, f"Expected 80.0 after 20% discount, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Discount Reduction Formula", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="DISCOUNT_INVERSION_ERROR", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Reduce total by 20% yielding 80.0",
        observed_behavior="Reduces total to discount fraction (20.0)", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Loyalty tier points redemption limit
    clean_code_8 = """def redeem_loyalty_points(points: int, max_allowed: int) -> int:
    usable = min(points, max_allowed)
    return usable // 100 * 100
"""
    mut_code_8 = """def redeem_loyalty_points(points: int, max_allowed: int) -> int:
    usable = max(points, max_allowed)
    return usable // 100 * 100
"""
    oracle_8 = """def run_oracle():
    redeemed = redeem_loyalty_points(5000, 2000)
    assert redeemed == 2000, f"Expected 2000, got {redeemed}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Points Redemption Ceiling", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Cap points by max_allowed",
        observed_behavior="Uses max instead of min, violating redemption cap", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Minimum stay requirement validator
    clean_code_9 = """def validate_stay_duration(checkin: int, checkout: int, min_nights: int) -> bool:
    duration = checkout - checkin
    return duration >= min_nights and duration > 0
"""
    mut_code_9 = """def validate_stay_duration(checkin: int, checkout: int, min_nights: int) -> bool:
    duration = checkin - checkout
    return duration >= min_nights and duration > 0
"""
    oracle_9 = """def run_oracle():
    assert validate_stay_duration(10, 15, 3) is True
    assert validate_stay_duration(15, 10, 3) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Stay Duration Subtraction Order", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OPERAND_ORDER_INVERSION", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Calculate checkout minus checkin",
        observed_behavior="Calculates checkin minus checkout producing negative duration", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Multi-room booking tax aggregation
    clean_code_10 = """def calculate_total_tax(room_rates: list, tax_rate: float) -> float:
    subtotal = sum(room_rates)
    return round(subtotal * tax_rate, 2)
"""
    mut_code_10 = """def calculate_total_tax(room_rates: list, tax_rate: float) -> float:
    subtotal = sum(room_rates)
    return round(subtotal + tax_rate, 2)
"""
    oracle_10 = """def run_oracle():
    tax = calculate_total_tax([100.0, 200.0], 0.10)
    assert tax == 30.0, f"Expected 30.0, got {tax}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tax Multiplication Error", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="OPERATOR_MUTATION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Multiply subtotal by tax rate",
        observed_behavior="Adds tax rate to subtotal", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Room cleaning fee conditional application
    clean_code_11 = """def apply_cleaning_fee(nights: int, is_suite: bool) -> float:
    if nights < 3 or is_suite:
        return 50.0
    return 0.0
"""
    mut_code_11 = """def apply_cleaning_fee(nights: int, is_suite: bool) -> float:
    if nights < 3 and is_suite:
        return 50.0
    return 0.0
"""
    oracle_11 = """def run_oracle():
    assert apply_cleaning_fee(1, False) == 50.0, "Short stays must incur cleaning fee"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cleaning Fee Boolean Logic", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Charge cleaning fee if short stay OR suite",
        observed_behavior="Requires both short stay AND suite", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Early check-in fee surcharge
    clean_code_12 = """def check_early_arrival_charge(hour_of_day: int) -> float:
    if hour_of_day < 14:
        return 25.0
    return 0.0
"""
    mut_code_12 = """def check_early_arrival_charge(hour_of_day: int) -> float:
    if hour_of_day <= 14:
        return 25.0
    return 0.0
"""
    oracle_12 = """def run_oracle():
    assert check_early_arrival_charge(14) == 0.0, "Standard check-in at 14:00 has no fee"
    assert check_early_arrival_charge(11) == 25.0, "Early check-in at 11:00 has 25.0 fee"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Standard Checkin Hour Threshold", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="BOUNDARY_INEQUALITY_MUTATION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="No charge at regular checkin hour 14:00",
        observed_behavior="Charges early fee at 14:00", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQL Injection in booking query lookup
    clean_sec_1 = """def query_guest_bookings(db_cursor, guest_email: str):
    query = "SELECT id, room_id, status FROM bookings WHERE email = ?"
    db_cursor.execute(query, (guest_email,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_guest_bookings(db_cursor, guest_email: str):
    query = f"SELECT id, room_id, status FROM bookings WHERE email = '{guest_email}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockCursor:
    def __init__(self):
        self.last_query = ""
        self.params = None
    def execute(self, query, params=None):
        self.last_query = query
        self.params = params
    def fetchall(self):
        return []

def run_oracle():
    cur = MockCursor()
    query_guest_bookings(cur, "alice@example.com")
    assert cur.params is not None, "Query must use parameterized arguments"
    assert "?" in cur.last_query or "%s" in cur.last_query, "Query must contain parameter placeholder"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Booking Database Query Parameterization", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="STRING_INTERPOLATION_SQL_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Use parameterized SQL query placeholder",
        observed_behavior="F-string injection allows arbitrary SQL execution", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command Injection in invoice generation
    clean_sec_2 = """import subprocess
def generate_invoice_pdf(booking_id: str, output_path: str):
    if not booking_id.isalnum():
        raise ValueError("Invalid booking id")
    cmd = ["pdfgen", "--id", booking_id, "-o", output_path]
    return subprocess.run(cmd, check=True)
"""
    mut_sec_2 = """import subprocess
def generate_invoice_pdf(booking_id: str, output_path: str):
    cmd = f"pdfgen --id {booking_id} -o {output_path}"
    return subprocess.run(cmd, shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(generate_invoice_pdf)
    assert "shell=True" not in src, "Must not execute shell command with string interpolation"
    assert "isalnum" in src or "shlex" in src, "Must sanitize booking ID"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Invoice Generator Command Execution", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Safely execute subprocess with list arguments",
        observed_behavior="Executes shell=True with unvalidated string concatenation", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path Traversal in booking confirmation template loader
    clean_sec_3 = """import os
def load_confirmation_template(template_name: str) -> str:
    base_dir = "/app/templates"
    clean_name = os.path.basename(template_name)
    target = os.path.join(base_dir, clean_name)
    return target
"""
    mut_sec_3 = """import os
def load_confirmation_template(template_name: str) -> str:
    base_dir = "/app/templates"
    target = os.path.join(base_dir, template_name)
    return target
"""
    oracle_sec_3 = """def run_oracle():
    path = load_confirmation_template("../../etc/passwd")
    assert "/etc/passwd" not in path or path.startswith("/app/templates/"), "Path traversal detected"
    assert ".." not in path, "Relative directory traversals must be stripped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Booking Template File Path Resolution", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=4,
        mutation_op="UNVALIDATED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize template name with basename",
        observed_behavior="Direct join allows directory traversal via relative paths", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 Cross-site Scripting in booking guest notes
    clean_sec_4 = """import html
def render_guest_notes_html(notes: str) -> str:
    escaped = html.escape(notes)
    return f"<div class='notes'>{escaped}</div>"
"""
    mut_sec_4 = """def render_guest_notes_html(notes: str) -> str:
    return f"<div class='notes'>{notes}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    payload = "<script>alert('xss')</script>"
    rendered = render_guest_notes_html(payload)
    assert "<script>" not in rendered, "Script tags must be HTML entity escaped"
    assert "&lt;script&gt;" in rendered, "Escaped entity expected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Guest Notes HTML Sanitization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_OUTPUT_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="HTML escape guest supplied notes",
        observed_behavior="Direct reflection allows arbitrary script injection", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing Authentication Check on Booking Cancellation
    clean_sec_5 = """def cancel_reservation(booking_id: str, authenticated_user: str, booking_owner: str) -> bool:
    if not authenticated_user:
        raise PermissionError("Unauthenticated")
    if authenticated_user != booking_owner:
        raise PermissionError("Unauthorized")
    return True
"""
    mut_sec_5 = """def cancel_reservation(booking_id: str, authenticated_user: str, booking_owner: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        cancel_reservation("BK-100", "", "owner@test.com")
        assert False, "Should raise PermissionError for unauthenticated caller"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cancellation Authentication Invariant", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTHENTICATION_BYPASS", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller identity before cancellation",
        observed_behavior="Unauthenticated caller can cancel arbitrary bookings", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing Authorization Check for VIP Lounge Access
    clean_sec_6 = """def grant_vip_lounge_access(guest_role: str) -> bool:
    allowed_roles = {"VIP_GUEST", "CONCIERGE", "ADMIN"}
    return guest_role in allowed_roles
"""
    mut_sec_6 = """def grant_vip_lounge_access(guest_role: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert grant_vip_lounge_access("STANDARD_GUEST") is False, "Standard guest must be denied"
    assert grant_vip_lounge_access("VIP_GUEST") is True, "VIP guest must be granted"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="VIP Lounge Authorization Guard", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Check role membership before access",
        observed_behavior="Unconditionally permits any role", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 O(N^2) search in available rooms list
    clean_perf_1 = """def match_requested_amenities(available_rooms: list, requested_amenities: set) -> list:
    matched = []
    for room in available_rooms:
        if requested_amenities.issubset(room['amenity_set']):
            matched.append(room['id'])
    return matched
"""
    mut_perf_1 = """def match_requested_amenities(available_rooms: list, requested_amenities: set) -> list:
    matched = []
    for room in available_rooms:
        has_all = True
        for req in requested_amenities:
            if req not in room['amenity_list']:
                has_all = False
                break
        if has_all:
            matched.append(room['id'])
    return matched
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(match_requested_amenities)
    assert "issubset" in src, "Must utilize issubset set operation for O(1) amenity lookups"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Amenity Lookup Algorithmic Complexity", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="QUADRATIC_LIST_MEMBERSHIP_SEARCH", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="Set intersection lookup",
        observed_behavior="Nested linear scans in list", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Unmemoized recursive pricing calendar breakdown
    clean_perf_2 = """def calculate_dynamic_rate(day: int, memo=None) -> int:
    if memo is None:
        memo = {}
    if day in memo:
        return memo[day]
    if day <= 1:
        return 100
    val = (calculate_dynamic_rate(day - 1, memo) + calculate_dynamic_rate(day - 2, memo)) % 500 + 50
    memo[day] = val
    return val
"""
    mut_perf_2 = """def calculate_dynamic_rate(day: int, memo=None) -> int:
    if day <= 1:
        return 100
    return (calculate_dynamic_rate(day - 1) + calculate_dynamic_rate(day - 2)) % 500 + 50
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(calculate_dynamic_rate)
    assert "memo" in src and "memo[" in src, "Dynamic pricing must memoize recursive calls"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Dynamic Rate Calendar Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="O(N) memoized dynamic pricing computation",
        observed_behavior="O(2^N) exponential recursion", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Repeated string concatenation in booking receipt generation
    clean_perf_3 = """def build_reservation_receipt(bookings: list) -> str:
    parts = ["RECEIPT SUMMARY\\n"]
    for b in bookings:
        parts.append(f"Booking {b['id']}: {b['nights']} nights @ {b['rate']}\\n")
    return "".join(parts)
"""
    mut_perf_3 = """def build_reservation_receipt(bookings: list) -> str:
    res = "RECEIPT SUMMARY\\n"
    for b in bookings:
        res = res + f"Booking {b['id']}: {b['nights']} nights @ {b['rate']}\\n"
    return res
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(build_reservation_receipt)
    assert ".join(" in src, "Must use list buffer join instead of quadratic string concatenation"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Receipt Buffer String Accumulation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Join preallocated list parts in linear time",
        observed_behavior="Repeated string reallocation in loop", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Unindexed guest search filtering
    clean_perf_4 = """def find_booking_by_confirmation(bookings_index: dict, code: str):
    return bookings_index.get(code)
"""
    mut_perf_4 = """def find_booking_by_confirmation(bookings_list: list, code: str):
    for b in bookings_list:
        if b['code'] == code:
            return b
    return None
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(find_booking_by_confirmation)
    assert "get(" in src or "dict" in src, "Confirmation code lookup must use O(1) hash map indexing"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Confirmation Code Index Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SCAN_SUBSTITUTION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Direct dictionary lookup",
        observed_behavior="Linear iteration over booking list", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Redundant regex recompilation in booking email parser
    clean_perf_5 = """import re
_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\\.[^@]+$")
def is_valid_guest_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))
"""
    mut_perf_5 = """import re
def is_valid_guest_email(email: str) -> bool:
    regex = re.compile(r"^[^@]+@[^@]+\\.[^@]+$")
    return bool(regex.match(email))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_guest_email)
    assert "re.compile" not in src, "Regex must be precompiled at module level to avoid recompilation overhead"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Regex Compilation In Loop", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Use precompiled module regex",
        observed_behavior="Recompiles pattern on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Re-introduced single-night zero checkout bug
    clean_reg_1 = """def calculate_nights_difference(checkin_day: int, checkout_day: int) -> int:
    diff = checkout_day - checkin_day
    if diff <= 0:
        raise ValueError("Checkout must be strictly after checkin")
    return diff
"""
    mut_reg_1 = """def calculate_nights_difference(checkin_day: int, checkout_day: int) -> int:
    return checkout_day - checkin_day
"""
    oracle_reg_1 = """def run_oracle():
    try:
        calculate_nights_difference(5, 5)
        assert False, "Regression: Zero night reservation must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Same-Day Booking Validation Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="REMOVAL_OF_GUARD_CLAUSE", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Raise ValueError when checkout == checkin",
        observed_behavior="Returns 0 allowing zero-night booking", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative guest counts
    clean_reg_2 = """def parse_guest_counts(adults: int, children: int) -> int:
    if adults < 0 or children < 0:
        raise ValueError("Guest counts cannot be negative")
    return adults + children
"""
    mut_reg_2 = """def parse_guest_counts(adults: int, children: int) -> int:
    return adults + children
"""
    oracle_reg_2 = """def run_oracle():
    try:
        parse_guest_counts(-2, 5)
        assert False, "Regression: Negative guest count must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Guest Count Validation Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_NEGATIVE_CHECK", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative guest inputs",
        observed_behavior="Accepts negative guest inputs", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy booking ID prefix
    clean_reg_3 = """def format_booking_reference(ref_num: int) -> str:
    return f"BK-{ref_num:06d}"
"""
    mut_reg_3 = """def format_booking_reference(ref_num: int) -> str:
    return f"{ref_num:06d}"
"""
    oracle_reg_3 = """def run_oracle():
    formatted = format_booking_reference(42)
    assert formatted == "BK-000042", f"Expected BK-000042, got {formatted}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Booking Reference Prefix Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_FORMAT_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include BK- prefix for downstream billing compatibility",
        observed_behavior="Drops BK- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost timezone/timestamp normalization in checkout timestamp
    clean_reg_4 = """def normalize_booking_hour(hour_str: str) -> int:
    # Support timestamps like "08:30" or "14:00"
    cleaned = hour_str.strip().split(":")[0].lstrip("0")
    return int(cleaned) if cleaned else 0
"""
    mut_reg_4 = """def normalize_booking_hour(hour_str: str) -> int:
    return int(hour_str)
"""
    oracle_reg_4 = """def run_oracle():
    res = normalize_booking_hour("08:30")
    assert res == 8, f"Expected 8, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Booking Hour Timestamp Parsing Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="REMOVAL_OF_SANITIZATION", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Parse hour prefix from timestamp strings",
        observed_behavior="Direct int() call crashes on colon timestamps", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null check on guest phone number
    clean_reg_5 = """def format_contact_phone(phone: str) -> str:
    if not phone:
        return "N/A"
    return phone.strip()
"""
    mut_reg_5 = """def format_contact_phone(phone: str) -> str:
    return phone.strip()
"""
    oracle_reg_5 = """def run_oracle():
    assert format_contact_phone("") == "N/A", "Empty phone should format to N/A"
    try:
        format_contact_phone(None)
        assert False, "None phone without guard raises AttributeError on strip"
    except (AttributeError, AssertionError):
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Phone Null Safety Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Return N/A on empty/null input",
        observed_behavior="Raises AttributeError on None", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed payload key in room inventory client
    clean_integ_1 = """def prepare_inventory_reserve_payload(room_id: str, count: int) -> dict:
    return {"room_identifier": room_id, "reservation_units": count}
"""
    mut_integ_1 = """def prepare_inventory_reserve_payload(room_id: str, count: int) -> dict:
    return {"id": room_id, "units": count}
"""
    oracle_integ_1 = """def run_oracle():
    payload = prepare_inventory_reserve_payload("RM-101", 2)
    assert "room_identifier" in payload, "Downstream service expects 'room_identifier'"
    assert "reservation_units" in payload, "Downstream service expects 'reservation_units'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Subsystem Contract Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="API_CONTRACT_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Produce schema-compliant keys",
        observed_behavior="Emits renamed keys breaking downstream inventory service", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dict vs tuple) in pricing adapter
    clean_integ_2 = """def fetch_rate_quote(base_price: float, taxes: float) -> dict:
    return {"subtotal": base_price, "tax": taxes, "total": base_price + taxes}
"""
    mut_integ_2 = """def fetch_rate_quote(base_price: float, taxes: float) -> tuple:
    return (base_price, taxes, base_price + taxes)
"""
    oracle_integ_2 = """def run_oracle():
    quote = fetch_rate_quote(100.0, 15.0)
    assert isinstance(quote, dict), "Consumer expects dict with named fields"
    assert "total" in quote and quote["total"] == 115.0
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pricing Adapter Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST client",
        observed_behavior="Returns tuple breaking dictionary indexing", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing required HTTP status header in webhook dispatcher
    clean_integ_3 = """def create_webhook_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Booking-Version": "2.0"}
"""
    mut_integ_3 = """def create_webhook_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = create_webhook_headers("tok_123")
    assert "X-Booking-Version" in h, "Webhook receiver requires X-Booking-Version header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Webhook Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_REQUIRED_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include version header in webhook dispatch",
        observed_behavior="Omits required version header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch (ISO 8601 YYYY-MM-DD vs DD/MM/YYYY)
    clean_integ_4 = """def format_checkin_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_checkin_date(year: int, month: int, day: int) -> str:
    return f"{day:02d}/{month:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    formatted = format_checkin_date(2026, 5, 9)
    assert formatted == "2026-05-09", f"API contract requires ISO-8601 (YYYY-MM-DD), got {formatted}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="API Date Serialization Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO-8601 formatted date",
        observed_behavior="Locale-specific date format breaking downstream parser", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Currency code casing mismatch (uppercase vs lowercase)
    clean_integ_5 = """def serialize_currency_amount(amount: float, currency: str) -> dict:
    return {"amount": round(amount, 2), "currency": currency.strip().upper()}
"""
    mut_integ_5 = """def serialize_currency_amount(amount: float, currency: str) -> dict:
    return {"amount": round(amount, 2), "currency": currency.strip().lower()}
"""
    oracle_integ_5 = """def run_oracle():
    res = serialize_currency_amount(50.0, "usd")
    assert res["currency"] == "USD", "Payment gateway requires ISO-4217 uppercase currency"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payment Gateway Currency Casing", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_NORMALIZATION_OMISSION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase ISO 4217 currency code",
        observed_behavior="Emits lowercase currency code", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened assertion allowing unverified room state
    clean_drift_1 = """def verify_room_cleanliness(room: dict) -> bool:
    # Contract: both inspected and sanitized flags must be True
    return room.get("inspected", False) and room.get("sanitized", False)
"""
    mut_drift_1 = """def verify_room_cleanliness(room: dict) -> bool:
    # Semantic drift: loosened requirement to only checked inspected
    return room.get("inspected", False)
"""
    oracle_drift_1 = """def run_oracle():
    room = {"inspected": True, "sanitized": False}
    assert verify_room_cleanliness(room) is False, "Drift: Unsanitized room must NOT pass cleanliness check"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Room Inspection Cleanliness Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both inspected and sanitized",
        observed_behavior="Loosens invariant allowing unsanitized rooms", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: ignoring guest dietary restrictions
    clean_drift_2 = """def compile_meal_order(guest_notes: str) -> dict:
    dietary = "STANDARD"
    if "vegan" in guest_notes.lower():
        dietary = "VEGAN"
    elif "gluten-free" in guest_notes.lower():
        dietary = "GLUTEN_FREE"
    return {"meal_type": dietary}
"""
    mut_drift_2 = """def compile_meal_order(guest_notes: str) -> dict:
    # Drift: dietary preferences silently defaulted to STANDARD
    return {"meal_type": "STANDARD"}
"""
    oracle_drift_2 = """def run_oracle():
    res = compile_meal_order("Guest is strictly vegan")
    assert res["meal_type"] == "VEGAN", "Drift: Dietary preference must be respected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Dietary Preference Contract Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Parse dietary tags into meal order",
        observed_behavior="Silently drops dietary preferences", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Assertion removal in test suite: deleting maximum occupancy check
    clean_drift_3 = """def validate_room_occupancy(adults: int, children: int, max_occupancy: int) -> bool:
    if adults + children > max_occupancy:
        return False
    return True
"""
    mut_drift_3 = """def validate_room_occupancy(adults: int, children: int, max_occupancy: int) -> bool:
    # Drift: occupancy upper bound check removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_room_occupancy(4, 3, 4) is False, "Drift: 7 guests exceeds max occupancy of 4"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Room Occupancy Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Reject occupancy exceeding maximum limit",
        observed_behavior="Unconditionally accepts any guest count", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Quiet precision rounding drift in currency conversion
    clean_drift_4 = """def convert_deposit_amount(amount: float, rate: float) -> float:
    # Spec contract: Round strictly to 2 decimal places with half-up convention
    from decimal import Decimal, ROUND_HALF_UP
    dec_amount = Decimal(str(amount)) * Decimal(str(rate))
    return float(dec_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def convert_deposit_amount(amount: float, rate: float) -> float:
    # Drift: uses integer truncation instead of proper half-up rounding
    return float(int(amount * rate))
"""
    oracle_drift_4 = """def run_oracle():
    res = convert_deposit_amount(100.0, 1.255)
    assert res == 125.50, f"Expected 125.50, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Deposit Currency Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Proper decimal half-up rounding",
        observed_behavior="Integer truncation drops cents", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting requirements: mutually exclusive checkin time constraints
    clean_conv_1 = """def check_booking_window(hour: int) -> bool:
    # Harmonized requirement: check-in allowed between 14 and 22
    return 14 <= hour <= 22
"""
    mut_conv_1 = """def check_booking_window(hour: int) -> bool:
    # Invariant conflict: Condition A requires hour < 12, Condition B requires hour > 15
    return hour < 12 and hour > 15
"""
    oracle_conv_1 = """def run_oracle():
    assert check_booking_window(16) is True, "Harmonized rule allows 16:00 checkin"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Check-in Window Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid checkin range 14:00 to 22:00",
        observed_behavior="Mutually contradictory rules (hour < 12 AND hour > 15) make pass impossible",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: off-by-one boundary flip-flop
    clean_conv_2 = """def calculate_stay_tier(nights: int) -> str:
    if nights >= 7:
        return "EXTENDED"
    elif nights >= 3:
        return "STANDARD"
    return "SHORT"
"""
    mut_conv_2 = """def calculate_stay_tier(nights: int) -> str:
    if nights > 7:
        return "EXTENDED"
    elif nights > 3:
        return "STANDARD"
    return "SHORT"
"""
    oracle_conv_2 = """def run_oracle():
    assert calculate_stay_tier(7) == "EXTENDED"
    assert calculate_stay_tier(3) == "STANDARD"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Stay Tier Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact tier thresholds at 3 and 7 nights",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular dependency in room-type upgrade resolution
    clean_conv_3 = """def resolve_next_tier(current: str) -> str:
    flow = {"ECONOMY": "STANDARD", "STANDARD": "DELUXE", "DELUXE": "SUITE", "SUITE": "SUITE"}
    return flow.get(current, "STANDARD")
"""
    mut_conv_3 = """def resolve_next_tier(current: str) -> str:
    # Circular loop between SUITE and DELUXE
    flow = {"ECONOMY": "STANDARD", "STANDARD": "DELUXE", "DELUXE": "SUITE", "SUITE": "DELUXE"}
    return flow.get(current, "STANDARD")
"""
    oracle_conv_3 = """def run_oracle():
    # Calling upgrade twice from DELUXE should stay at SUITE, not oscillate
    assert resolve_next_tier(resolve_next_tier("DELUXE")) == "SUITE", "Max tier must be absorbing terminal state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Room Upgrade State Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="SUITE is terminal non-oscillating tier",
        observed_behavior="SUITE downgrades to DELUXE creating infinite upgrade loop",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def booking_clean_routine_{c_idx}(base_val: int) -> int:
    # Clean control {c_idx}: verified correct logic with boundary protection
    if base_val < 0:
        return 0
    return base_val * 2 + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = booking_clean_routine_{c_idx}(5)
    assert res == 10 + {c_idx}, f"Expected {{10 + {c_idx}}}, got {{res}}"
    assert booking_clean_routine_{c_idx}(-3) == 0, "Negative values clamped to zero"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Booking Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified booking calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
