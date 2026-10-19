"""
Phase 3 Held-Out Benchmark Dataset (60 Scenarios) for INTELISE Component 4.
Document ID: INTELISE-C4-PHASE3-HELDOUT
Dataset Split: Held-Out Final Evaluation Set
Evaluation Rigor: FROZEN DATASET — ZERO GROUND-TRUTH LEAKAGE.

Methodological Constraints:
1. This held-out set is strictly frozen prior to evaluation.
2. It has NOT been used to tune detector rules, regexes, AST visitors, or thresholds.
3. Ground-truth labels are isolated from the detection pipeline.
4. Checksums are recorded in phase3_manifest.json.

Scenarios Distribution:
- Clean Controls: 10 (PH3-HELD-001 to PH3-HELD-010)
- Functional Bugs & Boundary Cases: 14 (PH3-HELD-011 to PH3-HELD-024)
- Security Vulnerabilities & Safe Controls: 10 (PH3-HELD-025 to PH3-HELD-034)
- Performance Bottlenecks & Normal Controls: 6 (PH3-HELD-035 to PH3-HELD-040)
- Integration & API Compatibility Defects: 6 (PH3-HELD-041 to PH3-HELD-046)
- Regression Defects: 6 (PH3-HELD-047 to PH3-HELD-052)
- Semantic Drift Cases: 4 (PH3-HELD-053 to PH3-HELD-056)
- Non-Convergent & Multi-Turn Repair Scenarios: 4 (PH3-HELD-057 to PH3-HELD-060)
"""
from typing import List
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.schemas.common import DefectCategory


PHASE3_HELDOUT_SCENARIOS: List[BenchmarkScenario] = [
    # =========================================================================
    # Group 1: Clean Controls (10 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-001",
        name="Bounded Circular FIFO Buffer",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-001"],
        module_code="""
class CircularBuffer:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = [None] * capacity
        self.head = 0
        self.tail = 0
        self.size = 0

    def push(self, item):
        self.buffer[self.tail] = item
        self.tail = (self.tail + 1) % self.capacity
        if self.size < self.capacity:
            self.size += 1
        else:
            self.head = (self.head + 1) % self.capacity

    def pop(self):
        if self.size == 0:
            return None
        val = self.buffer[self.head]
        self.head = (self.head + 1) % self.capacity
        self.size -= 1
        return val
""",
        test_code="""
import solution

def test_circular_buffer_fifo():
    cb = solution.CircularBuffer(3)
    cb.push("A")
    cb.push("B")
    cb.push("C")
    assert cb.pop() == "A"
    cb.push("D")
    assert cb.pop() == "B"
    assert cb.pop() == "C"
    assert cb.pop() == "D"
    assert cb.pop() is None
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-002",
        name="Luhn Algorithm Card Number Validator",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-002"],
        module_code="""
def validate_luhn_checksum(card_number: str) -> bool:
    digits = [int(c) for c in card_number if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled if doubled < 10 else doubled - 9
        else:
            checksum += d
    return checksum % 10 == 0
""",
        test_code="""
import solution

def test_luhn_valid():
    assert solution.validate_luhn_checksum("49927398716") is True
    assert solution.validate_luhn_checksum("49927398717") is False

def test_luhn_too_short():
    assert solution.validate_luhn_checksum("12345") is False
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-003",
        name="RFC Compliant Email Address Validator",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-003"],
        module_code=r"""
import re

def is_valid_email(email: str) -> bool:
    if not email or len(email) > 254:
        return False
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(pattern, email):
        return False
    domain_part = email.split("@")[1]
    return not domain_part.startswith("-") and not domain_part.endswith("-")
""",
        test_code="""
import solution

def test_valid_emails():
    assert solution.is_valid_email("user.name+tag@example.com") is True
    assert solution.is_valid_email("plainaddress") is False
    assert solution.is_valid_email("@missinguser.com") is False
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-004",
        name="Base64 URL-Safe Roundtrip Encoder",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-004"],
        module_code="""
import base64

def encode_url_safe(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def decode_url_safe(encoded: str) -> bytes:
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
""",
        test_code="""
import solution

def test_roundtrip():
    original = b"INTELISE verification payload 12345"
    encoded = solution.encode_url_safe(original)
    assert "=" not in encoded
    decoded = solution.decode_url_safe(encoded)
    assert decoded == original
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-005",
        name="Token Bucket Rate Limiter",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-005"],
        module_code="""
import time

class TokenBucketRateLimiter:
    def __init__(self, capacity: float, refill_rate_per_sec: float):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.tokens = capacity
        self.last_refill = time.time()

    def allow_request(self, cost: float = 1.0) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
""",
        test_code="""
import solution

def test_rate_limiter_burst():
    limiter = solution.TokenBucketRateLimiter(capacity=3.0, refill_rate_per_sec=1.0)
    assert limiter.allow_request(1.0) is True
    assert limiter.allow_request(1.0) is True
    assert limiter.allow_request(1.0) is True
    assert limiter.allow_request(1.0) is False
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-006",
        name="2D Matrix Determinant and Adjoint Inverse",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-006"],
        module_code="""
def invert_2x2_matrix(m: list[list[float]]) -> list[list[float]]:
    a, b = m[0][0], m[0][1]
    c, d = m[1][0], m[1][1]
    det = a * d - b * c
    if abs(det) < 1e-9:
        raise ValueError("Matrix is singular")
    inv_det = 1.0 / det
    return [
        [round(d * inv_det, 4), round(-b * inv_det, 4)],
        [round(-c * inv_det, 4), round(a * inv_det, 4)]
    ]
""",
        test_code="""
import solution
import pytest

def test_matrix_inversion():
    m = [[4.0, 7.0], [2.0, 6.0]]
    inv = solution.invert_2x2_matrix(m)
    assert inv[0][0] == 0.6
    assert inv[0][1] == -0.7
    assert inv[1][0] == -0.2
    assert inv[1][1] == 0.4

def test_singular():
    with pytest.raises(ValueError):
        solution.invert_2x2_matrix([[2.0, 4.0], [1.0, 2.0]])
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-007",
        name="IPv4 Subnet Mask Containment Checker",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-007"],
        module_code="""
def ip_to_int(ip: str) -> int:
    octets = [int(p) for p in ip.split(".")]
    return (octets[0] << 24) + (octets[1] << 16) + (octets[2] << 8) + octets[3]

def is_ip_in_subnet(ip: str, subnet_cidr: str) -> bool:
    network_str, mask_str = subnet_cidr.split("/")
    mask_bits = int(mask_str)
    netmask = (0xFFFFFFFF << (32 - mask_bits)) & 0xFFFFFFFF
    return (ip_to_int(ip) & netmask) == (ip_to_int(network_str) & netmask)
""",
        test_code="""
import solution

def test_ip_subnet_containment():
    assert solution.is_ip_in_subnet("192.168.1.50", "192.168.1.0/24") is True
    assert solution.is_ip_in_subnet("192.168.2.1", "192.168.1.0/24") is False
    assert solution.is_ip_in_subnet("10.0.0.1", "10.0.0.0/8") is True
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-008",
        name="SemVer Version Parser and Comparator",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-008"],
        module_code="""
def parse_semver(v: str) -> tuple[int, int, int]:
    parts = v.lstrip("v").split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))

def compare_semver(v1: str, v2: str) -> int:
    t1 = parse_semver(v1)
    t2 = parse_semver(v2)
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    return 0
""",
        test_code="""
import solution

def test_semver_comparisons():
    assert solution.compare_semver("1.2.3", "1.2.4") == -1
    assert solution.compare_semver("2.0.0", "1.9.9") == 1
    assert solution.compare_semver("1.10.0", "1.9.0") == 1
    assert solution.compare_semver("1.0.0", "1.0.0") == 0
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-009",
        name="JSON Schema Type Coercion Utility",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-009"],
        module_code="""
def coerce_field_type(value: str, target_type: str):
    if target_type == "integer":
        return int(value)
    elif target_type == "float":
        return float(value)
    elif target_type == "boolean":
        return value.lower() in ("true", "1", "yes")
    elif target_type == "string":
        return str(value)
    raise ValueError(f"Unsupported target type: {target_type}")
""",
        test_code="""
import solution

def test_coercions():
    assert solution.coerce_field_type("42", "integer") == 42
    assert solution.coerce_field_type("3.14", "float") == 3.14
    assert solution.coerce_field_type("true", "boolean") is True
    assert solution.coerce_field_type("no", "boolean") is False
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-010",
        name="XML Character Entity Escaper",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-010"],
        module_code="""
def escape_xml_entities(raw_text: str) -> str:
    escapes = [
        ("&", "&amp;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("'", "&apos;"),
    ]
    res = raw_text
    for char, entity in escapes:
        res = res.replace(char, entity)
    return res
""",
        test_code="""
import solution

def test_xml_escaping():
    text = '<item attr="val & co">'
    escaped = solution.escape_xml_entities(text)
    assert escaped == "&lt;item attr=&quot;val &amp; co&quot;&gt;"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    # =========================================================================
    # Group 2: Functional Defects & Boundary Cases (14 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-011",
        name="Binary Search Upper Bound Off-By-One Midpoint",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-011"],
        module_code="""
def binary_search_lookup(sorted_arr: list[int], target: int) -> int:
    low = 0
    high = len(sorted_arr)  # Defect: high initialized to len instead of len - 1
    while low <= high:
        mid = (low + high) // 2
        if mid >= len(sorted_arr):
            break
        if sorted_arr[mid] == target:
            return mid
        elif sorted_arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
""",
        test_code="""
import solution

def test_search_not_found_high():
    # Searching for element larger than array should return -1 cleanly without IndexError
    assert solution.binary_search_lookup([1, 3, 5], 10) == -1
    assert solution.binary_search_lookup([1, 3, 5], 5) == 2
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect off-by-one boundary failure in binary search high pointer",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-012",
        name="LRU Cache Eviction Policy Inverting Recency",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="hard",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-012"],
        module_code="""
class SimpleLruCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.order = []

    def get(self, key):
        if key in self.cache:
            self.order.remove(key)
            self.order.append(key)
            return self.cache[key]
        return None

    def put(self, key, value):
        if key in self.cache:
            self.order.remove(key)
        elif len(self.cache) >= self.capacity:
            # Defect: pops order[-1] (MRU) instead of order[0] (LRU)
            evicted = self.order.pop(-1)
            del self.cache[evicted]
        self.cache[key] = value
        self.order.append(key)
""",
        test_code="""
import solution

def test_lru_eviction():
    cache = solution.SimpleLruCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")  # 'a' is now MRU, 'b' is LRU
    cache.put("c", 3)  # Should evict 'b'
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=20,
        expected_system_behavior="Detect assertion failure on LRU cache incorrect eviction order",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-013",
        name="Bank Account Overdraft Limit Boundary Check",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-013"],
        module_code="""
class BankAccount:
    def __init__(self, initial_balance: float, overdraft_limit: float):
        self.balance = initial_balance
        self.overdraft_limit = overdraft_limit

    def withdraw(self, amount: float) -> bool:
        # Defect: allows withdrawal beyond overdraft limit by using > instead of >=
        if self.balance - amount > self.overdraft_limit:
            self.balance -= amount
            return True
        return False
""",
        test_code="""
import solution

def test_overdraft_boundary():
    acc = solution.BankAccount(100.0, 50.0)
    # Valid withdrawal down to -50.0
    assert acc.withdraw(150.0) is True
    # Attempting to exceed overdraft limit must return False
    assert acc.withdraw(10.0) is False
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=9,
        expected_system_behavior="Detect assertion failure on overdraft balance boundary logic",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-014",
        name="Markdown Bold Delimiter Punctuation Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-014"],
        module_code=r"""
import re

def render_markdown_bold(text: str) -> str:
    # Defect: regex requires whitespace after closing ** failing on punctuation
    pattern = r"\*\*([a-zA-Z0-9 ]+)\*\*\s"
    return re.sub(pattern, r"<b>\1</b> ", text)
""",
        test_code="""
import solution

def test_bold_followed_by_period():
    res = solution.render_markdown_bold("This is **important**.")
    assert "<b>important</b>." in res
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=6,
        expected_system_behavior="Detect assertion failure on markdown bold parser regex",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-015",
        name="Timezone UTC Offset Sign Inversion Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-015"],
        module_code="""
def apply_utc_offset(utc_hour: int, offset_hours: int) -> int:
    # Defect: subtracts offset instead of adding for positive offsets
    return (utc_hour - offset_hours) % 24
""",
        test_code="""
import solution

def test_positive_offset():
    # UTC 12:00 with +5 offset should be 17:00
    assert solution.apply_utc_offset(12, 5) == 17
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure from sign inversion in timezone offset",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-016",
        name="Shopping Cart Coupon Compounding Calculation",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-016"],
        module_code="""
def calculate_discounted_total(subtotal: float, coupon_pct: float, member_pct: float) -> float:
    # Defect: adds percentages directly instead of compounding or capping discounts
    total_discount = coupon_pct + member_pct
    return round(subtotal * (1.0 - total_discount), 2)
""",
        test_code="""
import solution

def test_independent_discounts():
    # $100 with 10% coupon ($90) then 10% member ($81.00)
    # Adding percentages yields $80.00
    res = solution.calculate_discounted_total(100.0, 0.10, 0.10)
    assert res == 81.00
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on coupon discount compounding",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-017",
        name="Pagination Total Pages Floor Division Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-017"],
        module_code="""
def compute_total_pages(total_items: int, page_size: int) -> int:
    if page_size <= 0:
        return 0
    # Defect: integer division truncates remainder, undercounting pages
    return total_items // page_size
""",
        test_code="""
import solution

def test_page_ceiling():
    assert solution.compute_total_pages(11, 5) == 3
    assert solution.compute_total_pages(10, 5) == 2
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=6,
        expected_system_behavior="Detect assertion failure on pagination total pages floor division",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-018",
        name="Graph Cycle Detection Missing Self-Loop Check",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-018"],
        module_code="""
def has_cycle(graph: dict[str, list[str]]) -> bool:
    visited = set()
    rec_stack = set()
    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor == node:
                # Defect: skips self-loop check treating it as visited pass
                continue
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False
    return any(dfs(n) for n in graph if n not in visited)
""",
        test_code="""
import solution

def test_self_loop_cycle():
    # Node with edge to itself must report has_cycle = True
    g = {"A": ["A"]}
    assert solution.has_cycle(g) is True
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=11,
        expected_system_behavior="Detect assertion failure on graph self-loop cycle omission",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-019",
        name="CSV Splitter Inadvertently Breaking Quoted Fields",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-019"],
        module_code="""
def parse_simple_csv_row(row_text: str) -> list[str]:
    # Defect: simple split(',') breaks embedded commas inside quoted fields
    return [col.strip() for col in row_text.split(",")]
""",
        test_code="""
import solution

def test_quoted_field():
    row = '101, "Acme, Inc.", 500.0'
    cols = solution.parse_simple_csv_row(row)
    assert len(cols) == 3
    assert cols[1] == '"Acme, Inc."'
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on naive comma split inside quotes",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-020",
        name="Circular Queue Size Computation Negative Modulo",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-020"],
        module_code="""
def circular_queue_count(head: int, tail: int, capacity: int) -> int:
    # Defect: returns tail - head directly, yielding negative count when tail wrapped
    return tail - head
""",
        test_code="""
import solution

def test_wrapped_queue_size():
    # Head at index 4, Tail wrapped around to index 1 in capacity 5 buffer -> size is 2
    assert solution.circular_queue_count(4, 1, 5) == 2
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure from negative circular queue size",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-021",
        name="Palindrome Checker Punctuation Normalization Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-021"],
        module_code="""
def is_palindrome(text: str) -> bool:
    # Defect: checks text reversed without stripping punctuation or whitespace
    return text == text[::-1]
""",
        test_code="""
import solution

def test_phrase_palindrome():
    assert solution.is_palindrome("A man, a plan, a canal: Panama!") is True
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on palindrome punctuation handling",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-022",
        name="Priority Queue Equal Priority Reversal",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-022"],
        module_code="""
class PriorityScheduler:
    def __init__(self):
        self.queue = []
    def add_task(self, name: str, priority: int):
        self.queue.append((priority, name))
        # Defect: lambda inverts name order when priority is equal
        self.queue.sort(key=lambda x: (x[0], x[1]), reverse=True)
    def next_task(self):
        return self.queue.pop(0)[1] if self.queue else None
""",
        test_code="""
import solution

def test_equal_priority_fifo():
    s = solution.PriorityScheduler()
    s.add_task("task_first", 10)
    s.add_task("task_second", 10)
    assert s.next_task() == "task_first"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=8,
        expected_system_behavior="Detect assertion failure on priority tie-breaker ordering",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-023",
        name="Inventory Stock Reservation Underflow Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-023"],
        module_code="""
class InventoryWarehouse:
    def __init__(self, stock: int):
        self.stock = stock

    def reserve(self, quantity: int) -> bool:
        # Defect: decrements stock before verifying sufficient inventory
        self.stock -= quantity
        if self.stock < 0:
            return False
        return True
""",
        test_code="""
import solution

def test_reserve_exhausted():
    w = solution.InventoryWarehouse(5)
    assert w.reserve(10) is False
    # Stock must not be corrupted to negative value
    assert w.stock == 5
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=8,
        expected_system_behavior="Detect assertion failure from corrupted negative inventory",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-024",
        name="Roman Numeral Subtractive Pair Defect (IV)",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-024"],
        module_code="""
def convert_roman_numeral(s: str) -> int:
    symbols = {'I': 1, 'V': 5, 'X': 10}
    val = 0
    for char in s:
        # Defect: purely additive conversion treats IV as 6 instead of 4
        val += symbols.get(char, 0)
    return val
""",
        test_code="""
import solution

def test_roman_iv():
    assert solution.convert_roman_numeral("IV") == 4
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=7,
        expected_system_behavior="Detect assertion failure on roman numeral IV subtractive parsing",
    ),

    # =========================================================================
    # Group 3: Security Vulnerabilities & Safe Negative Controls (10 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-025",
        name="CWE-89 SQL Injection in Product Search Filter",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-025"],
        module_code="""
class MockDbCursor:
    def execute(self, q: str): return [{"result": q}]

def search_products_by_name(cursor: MockDbCursor, search_term: str):
    # Vulnerability: Unsanitized string concatenation in SQL LIKE clause (CWE-89)
    query = "SELECT * FROM products WHERE title LIKE '%" + search_term + "%'"
    return cursor.execute(query)
""",
        test_code="""
import solution

def test_search_sql():
    c = solution.MockDbCursor()
    res = solution.search_products_by_name(c, "laptop")
    assert len(res) == 1
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-89",
        expected_line_number=7,
        expected_system_behavior="Detect CWE-89 SQL injection via AST security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-026",
        name="Safe Parameterized Product Search (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-026"],
        module_code="""
class MockDbCursor:
    def __init__(self): self.last_params = None
    def execute(self, q: str, p: tuple):
        self.last_params = p
        return [{"id": 1, "title": "Safe"}]

def search_products_safely(cursor: MockDbCursor, search_term: str):
    # Safe: Parameterized query placeholder prevents CWE-89
    return cursor.execute("SELECT * FROM products WHERE title LIKE ?", (f"%{search_term}%",))
""",
        test_code="""
import solution

def test_safe_product_search():
    c = solution.MockDbCursor()
    res = solution.search_products_safely(c, "laptop")
    assert len(res) == 1
    assert c.last_params == ("%laptop%",)
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-027",
        name="CWE-78 OS Command Injection in Archive Extractor",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-027"],
        module_code="""
import os

def unpack_archive(archive_name: str):
    # Vulnerability: Direct os.popen with unvalidated input (CWE-78)
    return os.popen(f"tar -xzf {archive_name}")
""",
        test_code="""
import solution

def test_unpack_call():
    res = solution.unpack_archive("test.tar.gz")
    assert res is not None
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-78",
        expected_line_number=6,
        expected_system_behavior="Detect CWE-78 OS command injection via AST security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-028",
        name="Safe Subprocess Archive Unpacker (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-028"],
        module_code="""
import subprocess

def unpack_archive_safely(archive_path: str):
    # Safe: List arguments and shell=False prevent CWE-78 command injection
    cmd = ["tar", "-xzf", archive_path]
    return cmd
""",
        test_code="""
import solution

def test_safe_unpack():
    cmd = solution.unpack_archive_safely("/tmp/safe.tar.gz")
    assert isinstance(cmd, list)
    assert cmd[0] == "tar"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-029",
        name="CWE-22 Path Traversal in Document Retrieval",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-029"],
        module_code="""
def retrieve_invoice_document(doc_id: str) -> str:
    # Vulnerability: Dynamic unconfined file path construction (CWE-22)
    path = f"/var/invoices/{doc_id}.pdf"
    with open(path, "r") as f:
        return f.read()
""",
        test_code="""
import solution

def test_invoice_read(monkeypatch):
    class MockF:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return "invoice_pdf_content"
    monkeypatch.setattr("builtins.open", lambda *a, **k: MockF())
    assert solution.retrieve_invoice_document("INV-100") == "invoice_pdf_content"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-22",
        expected_line_number=5,
        expected_system_behavior="Detect CWE-22 path traversal via AST security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-030",
        name="Safe Path Confinement with Basename (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-030"],
        module_code="""
import os

def retrieve_invoice_safely(base_dir: str, doc_id: str) -> str:
    # Safe: os.path.basename strips directory traversal sequences
    safe_name = os.path.basename(doc_id) + ".pdf"
    return os.path.join(base_dir, safe_name)
""",
        test_code="""
import solution

def test_safe_invoice_path():
    p = solution.retrieve_invoice_safely("/var/invoices", "../../etc/passwd")
    assert p == os.path.join("/var/invoices", "passwd.pdf")
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-031",
        name="CWE-95 Dynamic Expression Evaluation in Calculation Engine",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-031"],
        module_code="""
def execute_dynamic_calculation(calc_expr: str) -> float:
    # Vulnerability: Direct eval() of user calculation string (CWE-95)
    return eval(calc_expr)
""",
        test_code="""
import solution

def test_dynamic_calc():
    assert solution.execute_dynamic_calculation("100 * 1.15") == 115.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-95",
        expected_line_number=4,
        expected_system_behavior="Detect CWE-95 dynamic code execution via AST security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-032",
        name="Safe AST Mathematical Parser (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-032"],
        module_code="""
import ast

def parse_math_constant(expr: str) -> float:
    # Safe: literal_eval strictly evaluates numeric constants without arbitrary execution
    node = ast.literal_eval(expr)
    return float(node)
""",
        test_code="""
import solution

def test_safe_math():
    assert solution.parse_math_constant("42.5") == 42.5
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-033",
        name="CWE-798 Hardcoded JWT Private Secret Key",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="easy",
        provenance="cwe_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-033"],
        module_code="""
def sign_auth_token(user_id: int) -> dict:
    # Vulnerability: Hardcoded private jwt secret in source code (CWE-798)
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload12345678"
    return {"token": jwt_token, "user_id": user_id}
""",
        test_code="""
import solution

def test_sign_token():
    tok = solution.sign_auth_token(1)
    assert "token" in tok
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-798",
        expected_line_number=4,
        expected_system_behavior="Detect CWE-798 hardcoded credentials via AST security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-034",
        name="Safe Environment Secret Loader (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="held_out",
        requirement_ids=["REQ-HELD-034"],
        module_code="""
import os

def load_auth_token() -> str:
    # Safe: Secret retrieved from environment variable
    return os.environ.get("AUTH_TOKEN", "test_env_token_val")
""",
        test_code="""
import solution

def test_safe_auth_token(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "env_loaded_token")
    assert solution.load_auth_token() == "env_loaded_token"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    # =========================================================================
    # Group 4: Performance Bottlenecks & Normal Performance Controls (6 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-035",
        name="O(N^2) Pairwise Distance Matrix Bottleneck",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="hard",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-035"],
        module_code="""
def compute_distance_matrix(points: list[tuple[float, float]]) -> list[list[float]]:
    # Defect: O(N^2) exhaustive nested loop taking >200ms for large point sets
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            matrix[i][j] = (dx * dx + dy * dy) ** 0.5
    return matrix
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_distance_matrix_latency():
    pts = [(float(i % 100), float((i * 3) % 100)) for i in range(1200)]
    mat = solution.compute_distance_matrix(pts)
    assert len(mat) == 1200
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=7,
        expected_system_behavior="Breach 200ms latency SLA threshold due to O(N^2) nested distance loop",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-036",
        name="Optimized Distance Matrix (Normal Performance Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-036"],
        module_code="""
def compute_fast_distance_sample(points: list[tuple[float, float]], sample_size: int = 50) -> list[float]:
    # Optimized sub-sampling distance taking <10ms
    sample = points[:sample_size]
    distances = []
    p0 = sample[0] if sample else (0.0, 0.0)
    for p in sample:
        d = ((p[0] - p0[0]) ** 2 + (p[1] - p0[1]) ** 2) ** 0.5
        distances.append(round(d, 2))
    return distances
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_fast_distance():
    pts = [(float(i), float(i)) for i in range(500)]
    res = solution.compute_fast_distance_sample(pts, sample_size=50)
    assert len(res) == 50
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Normal performance control; latency remains well below 200ms threshold",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-037",
        name="Naive Recursive Levenshtein Distance Bottleneck",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="hard",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-037"],
        module_code="""
def levenshtein_recursive(s1: str, s2: str) -> int:
    # Defect: Exponential O(3^(M+N)) recursion without memoization
    if not s1: return len(s2)
    if not s2: return len(s1)
    if s1[0] == s2[0]:
        return levenshtein_recursive(s1[1:], s2[1:])
    return 1 + min(
        levenshtein_recursive(s1[1:], s2),
        levenshtein_recursive(s1, s2[1:]),
        levenshtein_recursive(s1[1:], s2[1:])
    )
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_levenshtein_latency():
    # Strings of length 11 cause heavy recursion taking >200ms
    res = solution.levenshtein_recursive("algorithmis", "altruisticx")
    assert res >= 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=8,
        expected_system_behavior="Breach 200ms latency SLA threshold due to exponential recursion",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-038",
        name="Dynamic Programming Levenshtein (Normal Performance Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-038"],
        module_code="""
def levenshtein_dp(s1: str, s2: str) -> int:
    # Fast DP table implementation taking <10ms
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1): dp[i][0] = i
    for j in range(n + 1): dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_dp_levenshtein():
    res = solution.levenshtein_dp("algorithmis", "altruisticx")
    assert res >= 0
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Normal performance control; executes in <15ms",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-039",
        name="Repeated Uncompiled Regex Search Loop Bottleneck",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-039"],
        module_code=r"""
import re

def filter_logs_uncompiled(logs: list[str]) -> list[str]:
    # Defect: Re-compiles complex regex on every iteration over large collection (>200ms)
    matched = []
    for line in logs:
        if re.search(r"ERROR\s+\[(AUTH|DB|NETWORK)\]:\s+code=\d{4}", line):
            matched.append(line)
    return matched
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_uncompiled_regex():
    lines = [f"INFO [APP]: user {i} logged in" for i in range(18000)]
    lines.append("ERROR [AUTH]: code=4001 session expired")
    res = solution.filter_logs_uncompiled(lines)
    assert len(res) == 1
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=8,
        expected_system_behavior="Breach 200ms latency SLA threshold due to repeated uncompiled regex",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-040",
        name="Pre-Compiled Regex Filter (Normal Performance Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="held_out",
        requested_test_types=["performance"],
        requirement_ids=["REQ-HELD-040"],
        module_code=r"""
import re

COMPILED_PATTERN = re.compile(r"ERROR\s+\[(AUTH|DB|NETWORK)\]:\s+code=\d{4}")

def filter_logs_compiled(logs: list[str]) -> list[str]:
    # Optimized: Uses pre-compiled regex taking <15ms
    return [line for line in logs if COMPILED_PATTERN.search(line)]
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_compiled_regex():
    lines = [f"INFO [APP]: user {i} logged in" for i in range(2000)]
    lines.append("ERROR [AUTH]: code=4001 session expired")
    res = solution.filter_logs_compiled(lines)
    assert len(res) == 1
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Normal performance control; completes in under 20ms",
    ),

    # =========================================================================
    # Group 5: Integration & API Compatibility Defects (6 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-041",
        name="API Paginated Response Missing Pagination Metadata Block",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-041"],
        module_code="""
def build_paginated_api_response(items: list, page: int, total_pages: int) -> dict:
    # Defect: API contract mandates 'pagination': {'page': X, 'total_pages': Y}
    # but implementation returns only 'data'
    return {"data": items}
""",
        test_code="""
import solution

def test_pagination_metadata_envelope():
    res = solution.build_paginated_api_response(["a", "b"], page=1, total_pages=5)
    assert "pagination" in res
    assert res["pagination"]["page"] == 1
    assert res["pagination"]["total_pages"] == 5
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=5,
        expected_system_behavior="Detect assertion failure on missing pagination metadata envelope",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-042",
        name="Webhook Dispatcher Missing HMAC Signature Header",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-042"],
        module_code="""
def construct_webhook_headers(payload_bytes: bytes, secret_key: str) -> dict:
    # Defect: Omits required 'X-Hub-Signature-256' header in webhook dispatch
    return {
        "Content-Type": "application/json",
        "X-Event-Type": "order.completed",
    }
""",
        test_code="""
import solution

def test_hmac_header_contract():
    headers = solution.construct_webhook_headers(b'{"order": 1}', "secret_key")
    assert "X-Hub-Signature-256" in headers
    assert headers["X-Hub-Signature-256"].startswith("sha256=")
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on missing HMAC signature header",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-043",
        name="REST Creation Handler Returning 200 Instead of 201 Created",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="easy",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-043"],
        module_code="""
def create_customer_endpoint(customer_data: dict) -> tuple[int, dict]:
    # Defect: REST specification requires HTTP 201 Created on resource creation, returns 200 OK
    return 200, {"id": "cust_123", **customer_data}
""",
        test_code="""
import solution

def test_rest_create_status_code():
    code, data = solution.create_customer_endpoint({"name": "Alice"})
    assert code == 201
    assert data["id"] == "cust_123"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on REST 201 status code contract",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-044",
        name="Payment Gateway Float Dollars vs Integer Cents Mismatch",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-044"],
        module_code="""
def prepare_gateway_charge(amount_dollars: float, currency: str) -> dict:
    # Defect: Gateway contract requires integer 'amount_cents', but sends float 'amount'
    return {
        "amount": amount_dollars,
        "currency": currency.upper(),
    }
""",
        test_code="""
import solution

def test_gateway_integer_cents():
    charge = solution.prepare_gateway_charge(19.99, "usd")
    assert "amount_cents" in charge
    assert isinstance(charge["amount_cents"], int)
    assert charge["amount_cents"] == 1999
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on payment gateway payload schema",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-045",
        name="GraphQL Error Envelope String vs Array Mismatch",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-045"],
        module_code="""
def format_graphql_error(message: str) -> dict:
    # Defect: GraphQL specification requires 'errors': [{'message': str}], returns 'errors': str
    return {"errors": message}
""",
        test_code="""
import solution

def test_graphql_error_array():
    res = solution.format_graphql_error("Field not found")
    assert isinstance(res["errors"], list)
    assert len(res["errors"]) == 1
    assert res["errors"][0]["message"] == "Field not found"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on GraphQL error response structure",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-046",
        name="JWT Claims Payload Missing Required Roles Claim",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="held_out",
        requirement_ids=["REQ-HELD-046"],
        module_code="""
def generate_token_claims(user_id: int, username: str) -> dict:
    # Defect: Downstream auth gateway requires 'roles' list in claims, but it is omitted
    return {
        "sub": str(user_id),
        "username": username,
    }
""",
        test_code="""
import solution

def test_jwt_roles_claim_contract():
    claims = solution.generate_token_claims(42, "admin_user")
    assert "roles" in claims
    assert isinstance(claims["roles"], list)
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on missing roles claim in token payload",
    ),

    # =========================================================================
    # Group 6: Regression Defects (6 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-047",
        name="Currency Formatter Dropping Trailing Zeroes Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="easy",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-047"],
        module_code="""
def format_currency_amount(amount: float) -> str:
    # Regression: str(round(...)) truncates trailing zero: 10.0 -> '10.0' or 10 -> '10' instead of '10.00'
    return f"${round(amount, 2)}"
""",
        test_code="""
import solution

def test_currency_trailing_zeroes_regression():
    assert solution.format_currency_amount(10.0) == "$10.00"
    assert solution.format_currency_amount(10.5) == "$10.50"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detect regression in financial currency formatting precision",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-048",
        name="User Permissions Calculation Inherited Roles Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-048"],
        module_code="""
def compute_user_effective_permissions(user_perms: list[str], group_perms: list[str]) -> set[str]:
    # Regression: Refactoring returned only user_perms, revoking inherited group permissions
    return set(user_perms)
""",
        test_code="""
import solution

def test_inherited_group_permissions_regression():
    u = ["read_own"]
    g = ["read_all", "export_csv"]
    eff = solution.compute_user_effective_permissions(u, g)
    assert "read_all" in eff
    assert "export_csv" in eff
    assert "read_own" in eff
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detect regression in inherited group permissions resolution",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-049",
        name="URL Slug Generator Stripping Non-ASCII Characters Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-049"],
        module_code=r"""
import re

def generate_url_slug(title: str) -> str:
    # Regression: Regex [^a-zA-Z0-9] strips unicode letters instead of transliterating/preserving
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", title)
    return re.sub(r"[\s-]+", "-", cleaned).strip("-").lower()
""",
        test_code="""
import solution

def test_slug_preserves_accents_or_dashes():
    # Previous implementation transliterated 'café' to 'cafe', regression strips 'e' entirely
    slug = solution.generate_url_slug("Café Au Lait")
    assert slug == "cafe-au-lait"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=6,
        expected_system_behavior="Detect regression in URL slug generation for international characters",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-050",
        name="Invoice Tax Calculation on Discounted Subtotal Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-050"],
        module_code="""
def compute_invoice_line_tax(subtotal: float, discount: float, tax_rate: float) -> float:
    # Regression: Tax law requires tax computed on original subtotal, not post-discount
    taxable_base = subtotal - discount
    return round(taxable_base * tax_rate, 2)
""",
        test_code="""
import solution

def test_tax_on_gross_subtotal_regression():
    # Tax of 10% on $100 subtotal with $20 discount must equal $10.00
    tax = solution.compute_invoice_line_tax(100.0, 20.0, 0.10)
    assert tax == 10.00
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detect regression on invoice taxable base calculation",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-051",
        name="Notification Dispatcher Suppressing Fallback Channel Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-051"],
        module_code="""
def dispatch_alert(email_success: bool, sms_success: bool) -> str:
    # Regression: Error handling short-circuits and ignores SMS fallback when email fails
    if not email_success:
        return "FAILED"
    return "SENT_EMAIL"
""",
        test_code="""
import solution

def test_sms_fallback_regression():
    status = solution.dispatch_alert(email_success=False, sms_success=True)
    assert status == "SENT_SMS"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detect regression in multi-channel notification fallback dispatcher",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-052",
        name="Search Phrase Indexer Dropping Stopwords Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-052"],
        module_code="""
def tokenize_search_phrase(phrase: str) -> list[str]:
    # Regression: Stopword filter applied to exact phrases, breaking searches like 'to be or not to be'
    stopwords = {"to", "be", "or", "not"}
    tokens = phrase.lower().split()
    return [t for t in tokens if t not in stopwords]
""",
        test_code="""
import solution

def test_exact_phrase_search_preserves_tokens():
    tokens = solution.tokenize_search_phrase('"to be or not to be"')
    # When enclosed in quotes, phrase tokens must be preserved
    assert len(tokens) >= 4
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=6,
        expected_system_behavior="Detect regression on search indexer phrase tokenizer",
    ),

    # =========================================================================
    # Group 7: Semantic Drift Cases (4 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-053",
        name="Positive Drift: Strict Assertion Weakened to Truthiness",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-053"],
        module_code="""
def calculate_net_salary(gross: float, tax_bracket: float) -> dict:
    # Defective tax formula: deductions inverted
    net = gross - (gross * (tax_bracket / 100.0)) + 500.0  # Erroneous addition!
    return {"net": round(net, 2), "deductions": round(gross - net, 2)}
""",
        original_test_code="""
import solution

def test_salary_calculation():
    res = solution.calculate_net_salary(5000.0, 20.0)
    assert res["net"] == 4000.00
    assert res["deductions"] == 1000.00
""",
        candidate_test_code="""
import solution

def test_salary_calculation():
    res = solution.calculate_net_salary(5000.0, 20.0)
    # Weakened assertion replacing strict net deduction verification
    assert res is not None
    assert "net" in res
""",
        test_code="""
import solution

def test_salary_calculation():
    res = solution.calculate_net_salary(5000.0, 20.0)
    assert res is not None
    assert "net" in res
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion weakening semantic drift and prevent superficial convergence",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-054",
        name="Positive Drift: Failure-Inducing Test Deleted from Suite",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-054"],
        module_code="""
def parse_percentage_value(val: str) -> float:
    # Defect: Fails on trailing percent sign '50%'
    return float(val)
""",
        original_test_code="""
import solution

def test_numeric_percentage():
    assert solution.parse_percentage_value("45.5") == 45.5

def test_formatted_percentage_symbol():
    assert solution.parse_percentage_value("45.5%") == 45.5
""",
        candidate_test_code="""
import solution

def test_numeric_percentage():
    assert solution.parse_percentage_value("45.5") == 45.5
# Defect masked by deleting test_formatted_percentage_symbol
""",
        test_code="""
import solution

def test_numeric_percentage():
    assert solution.parse_percentage_value("45.5") == 45.5
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect test deletion semantic drift and prevent superficial convergence",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-055",
        name="Negative Drift Control: Helper Function Refactoring",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-055"],
        module_code="""
def compute_box_volume(length: float, width: float, height: float) -> float:
    return length * width * height
""",
        original_test_code="""
import solution

def test_box_volume():
    assert solution.compute_box_volume(2.0, 3.0, 4.0) == 24.0
""",
        candidate_test_code="""
import solution

def test_box_volume():
    vol = solution.compute_box_volume(2.0, 3.0, 4.0)
    assert vol == 24.0
""",
        test_code="""
import solution

def test_box_volume():
    vol = solution.compute_box_volume(2.0, 3.0, 4.0)
    assert vol == 24.0
""",
        has_defect=False,
        has_semantic_drift=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Confirm clean refactoring; 0 semantic drift reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-056",
        name="Negative Drift Control: Additive Test Case Strengthening Suite",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="held_out",
        requirement_ids=["REQ-HELD-056"],
        module_code="""
def is_even_number(n: int) -> bool:
    return n % 2 == 0
""",
        original_test_code="""
import solution

def test_even_positive():
    assert solution.is_even_number(4) is True
""",
        candidate_test_code="""
import solution

def test_even_positive():
    assert solution.is_even_number(4) is True

def test_even_negative():
    assert solution.is_even_number(-2) is True
""",
        test_code="""
import solution

def test_even_positive():
    assert solution.is_even_number(4) is True

def test_even_negative():
    assert solution.is_even_number(-2) is True
""",
        has_defect=False,
        has_semantic_drift=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Confirm clean additive test enhancement; 0 semantic drift reported",
    ),

    # =========================================================================
    # Group 8: Non-Convergent Repair-Loop Scenarios (4 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-HELD-057",
        name="Conflicting Requirements Incompatible Format Oscillation",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        difficulty="hard",
        provenance="repair_loop_seeded",
        split="held_out",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-HELD-057-A", "REQ-HELD-057-B"],
        module_code="""
def format_user_identifier(prefix: str, uid: int) -> str:
    # Defective starting implementation
    return f"{uid}"
""",
        test_code="""
import solution

def test_system_a():
    # System A requires uppercase prefix with dash
    assert solution.format_user_identifier("usr", 100) == "USR-100"

def test_system_b():
    # System B requires lowercase prefix with colon
    assert solution.format_user_identifier("usr", 100) == "usr:100"
""",
        repair_candidate_patches=[
            # Patch 1 satisfies A, breaks B
            """
def format_user_identifier(prefix: str, uid: int) -> str:
    return f"{prefix.upper()}-{uid}"
""",
            # Patch 2 satisfies B, breaks A
            """
def format_user_identifier(prefix: str, uid: int) -> str:
    return f"{prefix.lower()}:{uid}"
""",
            # Patch 3 oscillates back to A
            """
def format_user_identifier(prefix: str, uid: int) -> str:
    return f"{prefix.upper()}-{uid}"
""",
        ],
        has_defect=True,
        is_non_convergent_by_design=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Exhaust 3 repair iterations and escalate to human governance",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-058",
        name="Repair Patch Introducing Non-Terminating Loop",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        difficulty="hard",
        provenance="repair_loop_seeded",
        split="held_out",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-HELD-058"],
        module_code="""
def process_work_queue(queue: list) -> int:
    return 0
""",
        test_code="""
import solution

def test_work_queue_processing():
    assert solution.process_work_queue([1, 2, 3]) == 3
""",
        repair_candidate_patches=[
            # Patch 1: raises unhandled deadlock exception
            """
def process_work_queue(queue: list) -> int:
    raise RuntimeError("Deadlock in worker dispatch")
""",
            # Patch 2: still defective
            """
def process_work_queue(queue: list) -> int:
    return -1
""",
        ],
        has_defect=True,
        is_non_convergent_by_design=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Trigger timeout / non-convergence and escalate to human review",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-059",
        name="Multi-Turn Iterative Repair Clean Convergence",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="repair_loop_seeded",
        split="held_out",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-HELD-059"],
        module_code="""
def calculate_shipping_cost(weight_kg: float, distance_km: float) -> float:
    # Initial defective implementation
    return 0.0
""",
        test_code="""
import solution

def test_shipping_rate():
    # Base fee $5.00 + $2.00 per kg + $0.50 per km
    # For 3kg and 10km: 5.0 + 6.0 + 5.0 = 16.0
    assert solution.calculate_shipping_cost(3.0, 10.0) == 16.0
""",
        repair_candidate_patches=[
            # Patch 1: partial fix (missing base fee)
            """
def calculate_shipping_cost(weight_kg: float, distance_km: float) -> float:
    return weight_kg * 2.0 + distance_km * 0.5
""",
            # Patch 2: 100% correct fix -> cleanly converges on Turn 2!
            """
def calculate_shipping_cost(weight_kg: float, distance_km: float) -> float:
    return 5.0 + weight_kg * 2.0 + distance_km * 0.5
""",
        ],
        has_defect=True,
        is_non_convergent_by_design=False,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Iteratively repair in 2 cycles and converge cleanly without escalation",
    ),

    BenchmarkScenario(
        scenario_id="PH3-HELD-060",
        name="Superficial Drift in Repair Attempt Prevented",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="hard",
        provenance="repair_loop_seeded",
        split="held_out",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-HELD-060"],
        module_code="""
def compute_tax_breakdown(gross: float) -> dict:
    # Defective implementation
    return {"federal": 0.0, "state": 0.0}
""",
        original_test_code="""
import solution

def test_tax_breakdown():
    res = solution.compute_tax_breakdown(100.0)
    assert res["federal"] == 15.0
    assert res["state"] == 5.0
""",
        candidate_test_code="""
import solution

def test_tax_breakdown():
    res = solution.compute_tax_breakdown(100.0)
    # Superficial repair attempt weakens test assertions
    assert res is not None
""",
        test_code="""
import solution

def test_tax_breakdown():
    res = solution.compute_tax_breakdown(100.0)
    assert res is not None
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect superficial convergence during repair loop and trigger governance escalation",
    ),
]
