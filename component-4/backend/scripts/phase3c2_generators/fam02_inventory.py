"""
Phase 3C.2 Family 02: Warehouse Stock Allocation & Inventory (FAM-02-INVENTORY).
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
    # 1.1 Safety stock threshold trigger (<= vs <)
    clean_code_1 = """def should_trigger_reorder(current_stock: int, safety_stock: int) -> bool:
    return current_stock <= safety_stock
"""
    mut_code_1 = """def should_trigger_reorder(current_stock: int, safety_stock: int) -> bool:
    return current_stock < safety_stock
"""
    oracle_1 = """def run_oracle():
    assert should_trigger_reorder(50, 50) is True, "Exact safety stock must trigger reorder"
    assert should_trigger_reorder(51, 50) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Safety Stock Reorder Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Trigger reorder at or below safety stock",
        observed_behavior="Fails to trigger reorder when stock equals safety stock exactly", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Backorder queue FIFO deduction
    clean_code_2 = """def allocate_stock_to_order(available: int, requested: int) -> tuple:
    allocated = min(available, requested)
    remaining_stock = available - allocated
    backorder = requested - allocated
    return allocated, remaining_stock, backorder
"""
    mut_code_2 = """def allocate_stock_to_order(available: int, requested: int) -> tuple:
    allocated = min(available, requested)
    remaining_stock = available - allocated
    backorder = requested + allocated
    return allocated, remaining_stock, backorder
"""
    oracle_2 = """def run_oracle():
    alloc, rem, back = allocate_stock_to_order(10, 15)
    assert alloc == 10 and rem == 0 and back == 5, f"Expected backorder 5, got {back}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Backorder Quantity Calculation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Calculate backorder as requested minus allocated",
        observed_behavior="Adds allocated to requested, exaggerating backorders", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Batch reservation rollback on failure
    clean_code_3 = """def reserve_batch_items(warehouse: dict, order_items: dict) -> bool:
    for sku, qty in order_items.items():
        if warehouse.get(sku, 0) < qty:
            return False
    for sku, qty in order_items.items():
        warehouse[sku] -= qty
    return True
"""
    mut_code_3 = """def reserve_batch_items(warehouse: dict, order_items: dict) -> bool:
    for sku, qty in order_items.items():
        if warehouse.get(sku, 0) < qty:
            return False
        warehouse[sku] -= qty
    return True
"""
    oracle_3 = """def run_oracle():
    wh = {"SKU-A": 10, "SKU-B": 2}
    order = {"SKU-A": 5, "SKU-B": 5}
    ok = reserve_batch_items(wh, order)
    assert ok is False, "Batch must fail when SKU-B insufficient"
    assert wh["SKU-A"] == 10, "Failed batch must not deduct SKU-A"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Batch Reservation Atomicity", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="PREMATURE_STATE_MUTATION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Two-phase check then deduct for batch atomicity",
        observed_behavior="Mutates earlier items before checking subsequent items", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Damaged goods depreciation valuation
    clean_code_4 = """def calculate_depreciated_value(unit_cost: float, units: int, defect_rate: float) -> float:
    sound_units = units * (1.0 - defect_rate)
    return round(sound_units * unit_cost, 2)
"""
    mut_code_4 = """def calculate_depreciated_value(unit_cost: float, units: int, defect_rate: float) -> float:
    sound_units = units * defect_rate
    return round(sound_units * unit_cost, 2)
"""
    oracle_4 = """def run_oracle():
    val = calculate_depreciated_value(20.0, 100, 0.10)
    assert val == 1800.0, f"Expected 1800.0, got {val}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Damaged Stock Depreciation Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="COMPLEMENT_OPERATOR_OMISSION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Value sound units (1 - defect_rate)",
        observed_behavior="Values defective units instead of sound inventory", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Bin location capacity limit check
    clean_code_5 = """def can_place_in_bin(bin_cap: int, current_qty: int, incoming: int) -> bool:
    return (current_qty + incoming) <= bin_cap
"""
    mut_code_5 = """def can_place_in_bin(bin_cap: int, current_qty: int, incoming: int) -> bool:
    return (current_qty + incoming) < bin_cap
"""
    oracle_5 = """def run_oracle():
    assert can_place_in_bin(100, 70, 30) is True, "Exact capacity placement is valid"
    assert can_place_in_bin(100, 70, 31) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bin Location Capacity Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Allow exact bin capacity fill",
        observed_behavior="Disallows exact capacity fill", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Supplier lead time reorder date offset
    clean_code_6 = """def compute_arrival_day(order_day: int, lead_time_days: int) -> int:
    return order_day + lead_time_days
"""
    mut_code_6 = """def compute_arrival_day(order_day: int, lead_time_days: int) -> int:
    return order_day - lead_time_days
"""
    oracle_6 = """def run_oracle():
    arrival = compute_arrival_day(10, 5)
    assert arrival == 15, f"Expected 15, got {arrival}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Supplier Lead Time Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Add lead time to order date",
        observed_behavior="Subtracts lead time from order date", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Warehouse transfer volume conservation
    clean_code_7 = """def transfer_inventory(source: dict, dest: dict, sku: str, qty: int) -> bool:
    if source.get(sku, 0) < qty:
        return False
    source[sku] -= qty
    dest[sku] = dest.get(sku, 0) + qty
    return True
"""
    mut_code_7 = """def transfer_inventory(source: dict, dest: dict, sku: str, qty: int) -> bool:
    if source.get(sku, 0) < qty:
        return False
    source[sku] -= qty
    dest[sku] = dest.get(sku, 0) - qty
    return True
"""
    oracle_7 = """def run_oracle():
    s = {"SKU-1": 20}
    d = {"SKU-1": 5}
    transfer_inventory(s, d, "SKU-1", 10)
    assert s["SKU-1"] == 10 and d["SKU-1"] == 15, f"Expected 15 at destination, got {d['SKU-1']}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Warehouse Transfer Conservation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="ARITHMETIC_INVERSION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Increment destination quantity by transferred amount",
        observed_behavior="Decrements destination quantity", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Inventory shrinkage percentage rate
    clean_code_8 = """def calculate_shrinkage_rate(book_stock: int, physical_stock: int) -> float:
    if book_stock <= 0:
        return 0.0
    missing = max(0, book_stock - physical_stock)
    return round((missing / book_stock) * 100.0, 2)
"""
    mut_code_8 = """def calculate_shrinkage_rate(book_stock: int, physical_stock: int) -> float:
    if book_stock <= 0:
        return 0.0
    missing = max(0, physical_stock - book_stock)
    return round((missing / book_stock) * 100.0, 2)
"""
    oracle_8 = """def run_oracle():
    rate = calculate_shrinkage_rate(100, 95)
    assert rate == 5.0, f"Expected 5.0% shrinkage, got {rate}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Shrinkage Calculation", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="OPERAND_ORDER_INVERSION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Calculate missing as book minus physical",
        observed_behavior="Calculates physical minus book producing zero when physical < book", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Hazardous material storage isolation guard
    clean_code_9 = """def can_store_together(is_flammable_a: bool, is_oxidizer_b: bool) -> bool:
    return not (is_flammable_a and is_oxidizer_b)
"""
    mut_code_9 = """def can_store_together(is_flammable_a: bool, is_oxidizer_b: bool) -> bool:
    return not (is_flammable_a or is_oxidizer_b)
"""
    oracle_9 = """def run_oracle():
    assert can_store_together(True, False) is True, "Flammable with non-oxidizer is permitted"
    assert can_store_together(True, True) is False, "Flammable and oxidizer must be isolated"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Hazardous Chemical Incompatibility Logic", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LOGICAL_OPERATOR_REPLACEMENT", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Isolate only when both flammable and oxidizer present",
        observed_behavior="Rejects storing any single flammable item", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Pallet stacking weight limit
    clean_code_10 = """def validate_pallet_stack(pallet_weights: list, max_capacity: float) -> bool:
    return sum(pallet_weights) <= max_capacity
"""
    mut_code_10 = """def validate_pallet_stack(pallet_weights: list, max_capacity: float) -> bool:
    return sum(pallet_weights) < max_capacity
"""
    oracle_10 = """def run_oracle():
    assert validate_pallet_stack([500.0, 500.0], 1000.0) is True, "Exact capacity stack is valid"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pallet Weight Limit Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Allow exact max capacity weight",
        observed_behavior="Rejects exact max capacity weight", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Stock reservation expiry timeout check
    clean_code_11 = """def is_reservation_expired(reserved_timestamp: int, current_timestamp: int, ttl_seconds: int) -> bool:
    return (current_timestamp - reserved_timestamp) > ttl_seconds
"""
    mut_code_11 = """def is_reservation_expired(reserved_timestamp: int, current_timestamp: int, ttl_seconds: int) -> bool:
    return (reserved_timestamp - current_timestamp) > ttl_seconds
"""
    oracle_11 = """def run_oracle():
    expired = is_reservation_expired(100, 500, 300)
    assert expired is True, "400 seconds elapsed exceeds 300 second TTL"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Reservation Expiry Timestamp Order", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OPERAND_SUBTRACTION_INVERSION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Subtract reserved from current time",
        observed_behavior="Subtracts current from reserved producing negative elapsed time", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Reorder lot size rounding
    clean_code_12 = """def round_to_lot_size(required_units: int, lot_size: int) -> int:
    if required_units <= 0:
        return 0
    import math
    return math.ceil(required_units / lot_size) * lot_size
"""
    mut_code_12 = """def round_to_lot_size(required_units: int, lot_size: int) -> int:
    if required_units <= 0:
        return 0
    import math
    return math.floor(required_units / lot_size) * lot_size
"""
    oracle_12 = """def run_oracle():
    rounded = round_to_lot_size(23, 10)
    assert rounded == 30, f"Expected 30 to cover 23 units, got {rounded}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Lot Size Rounding Direction", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="ROUNDING_DIRECTION_INVERSION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Ceiling round to ensure full inventory coverage",
        observed_behavior="Floor rounds resulting in deficit", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in warehouse SKU lookup
    clean_sec_1 = """def query_sku_stock(db_cursor, sku_code: str):
    query = "SELECT quantity, location FROM inventory WHERE sku = ?"
    db_cursor.execute(query, (sku_code,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_sku_stock(db_cursor, sku_code: str):
    query = f"SELECT quantity, location FROM inventory WHERE sku = '{sku_code}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockCur:
    def __init__(self):
        self.params = None
        self.query = ""
    def execute(self, q, p=None):
        self.query = q
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockCur()
    query_sku_stock(cur, "SKU-99")
    assert cur.params is not None, "Query must use parameterized arguments"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory SKU Query Parameterization", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized SQL lookup",
        observed_behavior="Direct string interpolation SQL injection", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in barcode generation
    clean_sec_2 = """import subprocess
def generate_barcode_label(sku: str, out_file: str):
    if not sku.isalnum():
        raise ValueError("Invalid SKU")
    subprocess.run(["barcode_tool", "--sku", sku, "-o", out_file], check=True)
"""
    mut_sec_2 = """import subprocess
def generate_barcode_label(sku: str, out_file: str):
    subprocess.run(f"barcode_tool --sku {sku} -o {out_file}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(generate_barcode_label)
    assert "shell=True" not in src, "Must not use shell=True with raw string interpolation"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Barcode Generator Subprocess Security", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="List arguments without shell invocation",
        observed_behavior="Unsafe shell execution allows command injection", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in warehouse floorplan viewer
    clean_sec_3 = """import os
def load_floorplan_diagram(layout_filename: str) -> str:
    base = "/app/warehouse/maps"
    safe_name = os.path.basename(layout_filename)
    return os.path.join(base, safe_name)
"""
    mut_sec_3 = """import os
def load_floorplan_diagram(layout_filename: str) -> str:
    base = "/app/warehouse/maps"
    return os.path.join(base, layout_filename)
"""
    oracle_sec_3 = """def run_oracle():
    res = load_floorplan_diagram("../../../var/log/syslog")
    assert ".." not in res and "/var/log" not in res, "Path traversal vulnerability"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Warehouse Layout Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=4,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Strip path traversals using basename",
        observed_behavior="Direct join allows escaping root maps directory", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in stock report item description
    clean_sec_4 = """import html
def render_item_tag(name: str) -> str:
    escaped = html.escape(name)
    return f"<span class='item-tag'>{escaped}</span>"
"""
    mut_sec_4 = """def render_item_tag(name: str) -> str:
    return f"<span class='item-tag'>{name}</span>"
"""
    oracle_sec_4 = """def run_oracle():
    rendered = render_item_tag("<img src=x onerror=alert(1)>")
    assert "<img" not in rendered and "&lt;img" in rendered, "HTML tags must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Tag HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in item tag",
        observed_behavior="Reflects unescaped markup allowing XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on inventory adjustment
    clean_sec_5 = """def adjust_inventory_count(sku: str, delta: int, auth_user: str) -> bool:
    if not auth_user:
        raise PermissionError("Unauthenticated")
    return True
"""
    mut_sec_5 = """def adjust_inventory_count(sku: str, delta: int, auth_user: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        adjust_inventory_count("SKU-1", -10, "")
        assert False, "Unauthenticated adjustment must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Count Adjustment Authentication", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Authenticate user before updating stock counts",
        observed_behavior="Unauthenticated caller can adjust stock counts", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for warehouse manager restocking override
    clean_sec_6 = """def override_reorder_limit(user_role: str, limit: int) -> bool:
    return user_role in {"WAREHOUSE_DIRECTOR", "SYSTEM_ADMIN"}
"""
    mut_sec_6 = """def override_reorder_limit(user_role: str, limit: int) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert override_reorder_limit("FORKLIFT_OPERATOR", 50000) is False, "Standard operator cannot override limits"
    assert override_reorder_limit("SYSTEM_ADMIN", 50000) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Restock Override Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict limit override to privileged roles",
        observed_behavior="Grants override access to any role", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear scan for SKU instead of dict key lookup
    clean_perf_1 = """def get_stock_level(inventory_map: dict, sku: str) -> int:
    return inventory_map.get(sku, 0)
"""
    mut_perf_1 = """def get_stock_level(inventory_list: list, sku: str) -> int:
    for item in inventory_list:
        if item['sku'] == sku:
            return item['qty']
    return 0
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(get_stock_level)
    assert "dict" in src or "get(" in src, "SKU lookup must use O(1) hash map"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory SKU Map Hash Lookup", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) hash map lookup",
        observed_behavior="O(N) linear list scan", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic nested filter for incompatible SKUs
    clean_perf_2 = """def filter_compatible_items(items: list, prohibited_set: set) -> list:
    return [x for x in items if x['id'] not in prohibited_set]
"""
    mut_perf_2 = """def filter_compatible_items(items: list, prohibited_list: list) -> list:
    res = []
    for x in items:
        found = False
        for p in prohibited_list:
            if x['id'] == p:
                found = True
                break
        if not found:
            res.append(x)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_compatible_items)
    assert "set" in src or "not in" in src, "Compatibility filter must use set lookups"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Prohibited Item Set Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set membership check in O(1)",
        observed_behavior="Nested loops yielding O(N*M) runtime", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive inventory tree aggregation
    clean_perf_3 = """def aggregate_assembly_parts(node: str, tree: dict, memo=None) -> int:
    if memo is None:
        memo = {}
    if node in memo:
        return memo[node]
    subparts = tree.get(node, [])
    if not subparts:
        return 1
    total = sum(aggregate_assembly_parts(child, tree, memo) for child in subparts)
    memo[node] = total
    return total
"""
    mut_perf_3 = """def aggregate_assembly_parts(node: str, tree: dict, memo=None) -> int:
    subparts = tree.get(node, [])
    if not subparts:
        return 1
    return sum(aggregate_assembly_parts(child, tree) for child in subparts)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(aggregate_assembly_parts)
    assert "memo" in src and "memo[" in src, "Assembly parts tree aggregation must memoize shared subcomponents"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Assembly Bill-of-Materials Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized DAG traversal",
        observed_behavior="Exponential re-evaluation of shared assemblies", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in warehouse manifest builder
    clean_perf_4 = """def build_warehouse_manifest(items: list) -> str:
    lines = ["MANIFEST HEADER\\n"]
    for it in items:
        lines.append(f"{it['sku']}:{it['qty']}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def build_warehouse_manifest(items: list) -> str:
    res = "MANIFEST HEADER\\n"
    for it in items:
        res = res + f"{it['sku']}:{it['qty']}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(build_warehouse_manifest)
    assert ".join(" in src, "Manifest builder must join list buffer"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Warehouse Manifest Buffer String Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="List buffer join",
        observed_behavior="Repeated string copy in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of SKU validation regex
    clean_perf_5 = """import re
_SKU_RE = re.compile(r"^SKU-[0-9]{4,8}$")
def validate_sku_format(sku: str) -> bool:
    return bool(_SKU_RE.match(sku))
"""
    mut_perf_5 = """import re
def validate_sku_format(sku: str) -> bool:
    r = re.compile(r"^SKU-[0-9]{4,8}$")
    return bool(r.match(sku))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(validate_sku_format)
    assert "re.compile" not in src, "SKU regex must be compiled once at module scope"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="SKU Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled regex",
        observed_behavior="Recompiles pattern inside function", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped zero quantity rejection check
    clean_reg_1 = """def record_receipt(sku: str, quantity: int) -> bool:
    if quantity <= 0:
        raise ValueError("Receipt quantity must be positive")
    return True
"""
    mut_reg_1 = """def record_receipt(sku: str, quantity: int) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        record_receipt("SKU-1", 0)
        assert False, "Regression: Zero quantity must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Zero Quantity Receipt Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject zero quantity receipts",
        observed_behavior="Accepts zero quantity receipts", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative stock deduction
    clean_reg_2 = """def deduct_stock(current: int, qty: int) -> int:
    if qty < 0:
        raise ValueError("Cannot deduct negative quantity")
    if current < qty:
        raise ValueError("Insufficient inventory")
    return current - qty
"""
    mut_reg_2 = """def deduct_stock(current: int, qty: int) -> int:
    return current - qty
"""
    oracle_reg_2 = """def run_oracle():
    try:
        deduct_stock(10, -5)
        assert False, "Regression: Deducting negative quantity must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Deduction Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative deduction",
        observed_behavior="Allows negative deduction effectively creating phantom stock", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy bin code prefix
    clean_reg_3 = """def format_bin_code(aisle: int, shelf: int) -> str:
    return f"BIN-{aisle:02d}-{shelf:02d}"
"""
    mut_reg_3 = """def format_bin_code(aisle: int, shelf: int) -> str:
    return f"{aisle:02d}-{shelf:02d}"
"""
    oracle_reg_3 = """def run_oracle():
    code = format_bin_code(3, 12)
    assert code == "BIN-03-12", f"Expected BIN-03-12, got {code}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bin Code Prefix Formatting Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include BIN- prefix",
        observed_behavior="Drops BIN- prefix breaking barcode scanners", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in supplier SKU parser
    clean_reg_4 = """def parse_supplier_sku(raw: str) -> str:
    cleaned = raw.strip().upper()
    if not cleaned:
        raise ValueError("Empty SKU")
    return cleaned
"""
    mut_reg_4 = """def parse_supplier_sku(raw: str) -> str:
    return raw.upper()
"""
    oracle_reg_4 = """def run_oracle():
    res = parse_supplier_sku("  sku-123  ")
    assert res == "SKU-123", f"Expected SKU-123 without whitespace, got '{res}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Supplier SKU Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on warehouse notes
    clean_reg_5 = """def format_inventory_note(note: str) -> str:
    if note is None:
        return ""
    return note.strip()
"""
    mut_reg_5 = """def format_inventory_note(note: str) -> str:
    return note.strip()
"""
    oracle_reg_5 = """def run_oracle():
    assert format_inventory_note(None) == "", "None note must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Inventory Note Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_GUARD_REMOVAL", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Return empty string for None",
        observed_behavior="Raises AttributeError on None", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed inventory webhook payload keys
    clean_integ_1 = """def build_stock_update_event(sku: str, qty: int) -> dict:
    return {"sku_code": sku, "updated_quantity": qty, "event_type": "STOCK_ADJUSTED"}
"""
    mut_integ_1 = """def build_stock_update_event(sku: str, qty: int) -> dict:
    return {"sku": sku, "qty": qty, "type": "STOCK_ADJUSTED"}
"""
    oracle_integ_1 = """def run_oracle():
    ev = build_stock_update_event("SKU-1", 10)
    assert "sku_code" in ev and "updated_quantity" in ev, "Event consumer expects 'sku_code' and 'updated_quantity'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Stock Update Event Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Use standardized event keys",
        observed_behavior="Emits abbreviated keys breaking Kafka schema registry", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (list vs dict) in location inventory query
    clean_integ_2 = """def fetch_bin_contents(bin_id: str) -> dict:
    return {"bin_id": bin_id, "items": [{"sku": "A", "qty": 5}]}
"""
    mut_integ_2 = """def fetch_bin_contents(bin_id: str) -> list:
    return [{"sku": "A", "qty": 5}]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_bin_contents("BIN-1")
    assert isinstance(res, dict) and "bin_id" in res, "Service contract requires wrapping dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bin Content Return Type Wrapping", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return wrapped dictionary with bin_id metadata",
        observed_behavior="Returns unwrapped list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in ERP replenishment client
    clean_integ_3 = """def build_erp_headers(api_key: str) -> dict:
    return {"X-ERP-Key": api_key, "Content-Type": "application/json", "X-Client-ID": "WAREHOUSE-01"}
"""
    mut_integ_3 = """def build_erp_headers(api_key: str) -> dict:
    return {"Content-Type": "application/json", "X-Client-ID": "WAREHOUSE-01"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_erp_headers("erp_key_xyz")
    assert "X-ERP-Key" in h, "ERP gateway requires X-ERP-Key header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="ERP Client Headers Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include ERP authentication header",
        observed_behavior="Omits required authentication header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in shipment ASN
    clean_integ_4 = """def format_asn_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_asn_date(year: int, month: int, day: int) -> str:
    return f"{month:02d}-{day:02d}-{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    res = format_asn_date(2026, 8, 14)
    assert res == "2026-08-14", f"EDI ASN contract requires YYYY-MM-DD, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Shipment ASN Date Serialization", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 YYYY-MM-DD date format",
        observed_behavior="MM-DD-YYYY format breaking EDI parser", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Unit of measure code casing mismatch
    clean_integ_5 = """def serialize_unit_of_measure(uom: str) -> str:
    return uom.strip().upper()
"""
    mut_integ_5 = """def serialize_unit_of_measure(uom: str) -> str:
    return uom.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    res = serialize_unit_of_measure("kg")
    assert res == "KG", "WMS standard requires uppercase Unit of Measure"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Unit of Measure Serialization Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase unit of measure code",
        observed_behavior="Emits lowercase code", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened inspection check: omitting expiration date validation
    clean_drift_1 = """def is_perishable_stock_valid(item: dict, current_day: int) -> bool:
    return item.get("unbroken_seal", False) and item.get("expiry_day", 0) > current_day
"""
    mut_drift_1 = """def is_perishable_stock_valid(item: dict, current_day: int) -> bool:
    # Drift: loosened requirement to only check seal, ignoring expiry
    return item.get("unbroken_seal", False)
"""
    oracle_drift_1 = """def run_oracle():
    item = {"unbroken_seal": True, "expiry_day": 50}
    assert is_perishable_stock_valid(item, 100) is False, "Drift: Expired stock must not be valid"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Perishable Stock Expiry Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Verify both unbroken seal and future expiration",
        observed_behavior="Drops expiry check allowing expired perishable items", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: ignoring batch priority tags
    clean_drift_2 = """def prioritize_replenishment(batches: list) -> list:
    return sorted(batches, key=lambda b: (not b.get("is_urgent", False), b.get("order_day", 0)))
"""
    mut_drift_2 = """def prioritize_replenishment(batches: list) -> list:
    # Drift: urgent priority flag ignored, sorted purely by arrival
    return sorted(batches, key=lambda b: b.get("order_day", 0))
"""
    oracle_drift_2 = """def run_oracle():
    b1 = {"id": 1, "is_urgent": False, "order_day": 10}
    b2 = {"id": 2, "is_urgent": True, "order_day": 20}
    res = prioritize_replenishment([b1, b2])
    assert res[0]["id"] == 2, "Drift: Urgent batch must be ordered first"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Replenishment Priority Queue Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="PRIORITY_SPECIFICATION_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Prioritize urgent batches before standard batches",
        observed_behavior="Silently ignores urgency flag", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum bin weight invariant removal
    clean_drift_3 = """def validate_bin_weight(items: list, max_weight: float) -> bool:
    total = sum(it.get("weight", 0.0) for it in items)
    return total <= max_weight
"""
    mut_drift_3 = """def validate_bin_weight(items: list, max_weight: float) -> bool:
    # Drift: weight limit check removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_bin_weight([{"weight": 200.0}], 100.0) is False, "Drift: Overweight bin must be rejected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bin Weight Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce bin weight ceiling",
        observed_behavior="Unconditionally permits any weight", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in volumetric pallet calculation
    clean_drift_4 = """def calculate_cbm(length_cm: float, width_cm: float, height_cm: float) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    cbm = (Decimal(str(length_cm)) * Decimal(str(width_cm)) * Decimal(str(height_cm))) / Decimal("1000000")
    return float(cbm.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def calculate_cbm(length_cm: float, width_cm: float, height_cm: float) -> float:
    # Drift: integer truncation of intermediate volume
    return float(int(length_cm * width_cm * height_cm / 1000000))
"""
    oracle_drift_4 = """def run_oracle():
    res = calculate_cbm(100.0, 50.0, 30.0)
    assert res == 0.150, f"Expected 0.150 CBM, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pallet Volume CBM Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate 3-decimal CBM volumetric rounding",
        observed_behavior="Truncates to integer dropping fraction", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting requirements on temperature controlled storage
    clean_conv_1 = """def check_cold_storage_temp(temp_celsius: float) -> bool:
    # Harmonized spec: valid cold range between 2.0 and 8.0 C
    return 2.0 <= temp_celsius <= 8.0
"""
    mut_conv_1 = """def check_cold_storage_temp(temp_celsius: float) -> bool:
    # Invariant conflict: Spec A requires temp > 10, Spec B requires temp < 5
    return temp_celsius > 10.0 and temp_celsius < 5.0
"""
    oracle_conv_1 = """def run_oracle():
    assert check_cold_storage_temp(4.0) is True, "Harmonized rule allows 4.0 C"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Cold Storage Temperature Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid cold range 2.0 to 8.0",
        observed_behavior="Mutually exclusive conditions make satisfaction impossible",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: safety stock threshold operator
    clean_conv_2 = """def evaluate_safety_buffer(qty: int, buffer_min: int) -> str:
    if qty >= buffer_min:
        return "SAFE"
    return "CRITICAL"
"""
    mut_conv_2 = """def evaluate_safety_buffer(qty: int, buffer_min: int) -> str:
    if qty > buffer_min:
        return "SAFE"
    return "CRITICAL"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_safety_buffer(10, 10) == "SAFE", "Exact buffer must be SAFE"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Safety Buffer Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary is SAFE",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in warehouse bin status
    clean_conv_3 = """def advance_bin_status(current: str) -> str:
    transitions = {"EMPTY": "RESERVED", "RESERVED": "OCCUPIED", "OCCUPIED": "FULL", "FULL": "FULL"}
    return transitions.get(current, "EMPTY")
"""
    mut_conv_3 = """def advance_bin_status(current: str) -> str:
    # Circular loop between OCCUPIED and RESERVED
    transitions = {"EMPTY": "RESERVED", "RESERVED": "OCCUPIED", "OCCUPIED": "RESERVED", "FULL": "FULL"}
    return transitions.get(current, "EMPTY")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_bin_status(advance_bin_status("RESERVED"))
    assert res == "FULL", "Bin progression must reach terminal FULL state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bin State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to FULL",
        observed_behavior="Oscillates infinitely between RESERVED and OCCUPIED",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def inventory_clean_routine_{c_idx}(stock_level: int) -> int:
    # Clean control {c_idx}: verified warehouse calculation with boundary guard
    if stock_level < 0:
        return 0
    return (stock_level * 3) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = inventory_clean_routine_{c_idx}(10)
    assert res == 30 + {c_idx}, f"Expected {{30 + {c_idx}}}, got {{res}}"
    assert inventory_clean_routine_{c_idx}(-5) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Inventory Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified inventory calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
