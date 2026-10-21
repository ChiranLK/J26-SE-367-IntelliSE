"""
Phase 3C.2 Family 03: Payment Calculations, Discounts & Invoicing (FAM-03-PAYMENT).
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
    # 1.1 Tiered volume discount threshold (>= vs >)
    clean_code_1 = """def calculate_volume_discount(quantity: int, unit_price: float) -> float:
    if quantity >= 100:
        discount = 0.20
    elif quantity >= 50:
        discount = 0.10
    else:
        discount = 0.0
    return round(quantity * unit_price * (1.0 - discount), 2)
"""
    mut_code_1 = """def calculate_volume_discount(quantity: int, unit_price: float) -> float:
    if quantity > 100:
        discount = 0.20
    elif quantity >= 50:
        discount = 0.10
    else:
        discount = 0.0
    return round(quantity * unit_price * (1.0 - discount), 2)
"""
    oracle_1 = """def run_oracle():
    total = calculate_volume_discount(100, 10.0)
    assert total == 800.0, f"Expected 800.0 for 100 units with 20% discount, got {total}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Volume Discount Tier Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Apply 20% discount at 100 units",
        observed_behavior="Applies only 10% discount at exactly 100 units", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Compound VAT and local sales tax addition
    clean_code_2 = """def calculate_taxed_total(subtotal: float, vat_rate: float, local_tax_rate: float) -> float:
    total_tax_rate = vat_rate + local_tax_rate
    return round(subtotal * (1.0 + total_tax_rate), 2)
"""
    mut_code_2 = """def calculate_taxed_total(subtotal: float, vat_rate: float, local_tax_rate: float) -> float:
    total_tax_rate = vat_rate - local_tax_rate
    return round(subtotal * (1.0 + total_tax_rate), 2)
"""
    oracle_2 = """def run_oracle():
    total = calculate_taxed_total(100.0, 0.15, 0.05)
    assert total == 120.0, f"Expected 120.0, got {total}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Combined Tax Rate Arithmetic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Add VAT and local tax rates",
        observed_behavior="Subtracts local tax rate from VAT", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Subscription mid-cycle proration
    clean_code_3 = """def calculate_proration_credit(monthly_fee: float, days_used: int, total_days: int) -> float:
    if total_days <= 0:
        return 0.0
    unused_days = total_days - days_used
    return round((unused_days / total_days) * monthly_fee, 2)
"""
    mut_code_3 = """def calculate_proration_credit(monthly_fee: float, days_used: int, total_days: int) -> float:
    if total_days <= 0:
        return 0.0
    unused_days = total_days - days_used
    return round((days_used / total_days) * monthly_fee, 2)
"""
    oracle_3 = """def run_oracle():
    credit = calculate_proration_credit(30.0, 10, 30)
    assert credit == 20.0, f"Expected 20.0 refund for 20 unused days, got {credit}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Subscription Proration Credit Ratio", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="OPERAND_SUBSTITUTION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Calculate refund based on unused days",
        observed_behavior="Calculates credit based on used days", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Refund split across card and gift card
    clean_code_4 = """def split_refund_amount(total_refund: float, gift_card_paid: float) -> tuple:
    gift_card_refund = min(total_refund, gift_card_paid)
    card_refund = total_refund - gift_card_refund
    return round(card_refund, 2), round(gift_card_refund, 2)
"""
    mut_code_4 = """def split_refund_amount(total_refund: float, gift_card_paid: float) -> tuple:
    gift_card_refund = max(total_refund, gift_card_paid)
    card_refund = total_refund - gift_card_refund
    return round(card_refund, 2), round(gift_card_refund, 2)
"""
    oracle_4 = """def run_oracle():
    card, gc = split_refund_amount(50.0, 20.0)
    assert gc == 20.0 and card == 30.0, f"Expected (30.0, 20.0), got ({card}, {gc})"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Split Refund Attribution Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Refund to gift card capped at original gift card payment",
        observed_behavior="Uses max instead of min, resulting in negative card refund", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Currency exchange with spread slippage
    clean_code_5 = """def convert_currency_with_spread(amount: float, rate: float, spread: float) -> float:
    effective_rate = rate * (1.0 - spread)
    return round(amount * effective_rate, 2)
"""
    mut_code_5 = """def convert_currency_with_spread(amount: float, rate: float, spread: float) -> float:
    effective_rate = rate * (1.0 + spread)
    return round(amount * effective_rate, 2)
"""
    oracle_5 = """def run_oracle():
    res = convert_currency_with_spread(100.0, 1.20, 0.02)
    assert res == 117.60, f"Expected 117.60, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Currency Exchange Spread Deduction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Deduct spread from rate",
        observed_behavior="Adds spread to rate giving favorable conversion", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Merchant payout netting
    clean_code_6 = """def compute_merchant_payout(gross_sales: float, fee_percent: float, fixed_fee: float) -> float:
    fees = (gross_sales * fee_percent) + fixed_fee
    return round(max(0.0, gross_sales - fees), 2)
"""
    mut_code_6 = """def compute_merchant_payout(gross_sales: float, fee_percent: float, fixed_fee: float) -> float:
    fees = (gross_sales * fee_percent) - fixed_fee
    return round(max(0.0, gross_sales - fees), 2)
"""
    oracle_6 = """def run_oracle():
    payout = compute_merchant_payout(100.0, 0.03, 0.30)
    assert payout == 96.70, f"Expected 96.70, got {payout}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Merchant Fee Deductions Aggregation", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Sum percentage and fixed transaction fees",
        observed_behavior="Subtracts fixed fee reducing merchant deductions", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Credit card surcharge legal ceiling
    clean_code_7 = """def apply_credit_card_surcharge(subtotal: float, surcharge_rate: float, max_surcharge: float) -> float:
    surcharge = min(subtotal * surcharge_rate, max_surcharge)
    return round(subtotal + surcharge, 2)
"""
    mut_code_7 = """def apply_credit_card_surcharge(subtotal: float, surcharge_rate: float, max_surcharge: float) -> float:
    surcharge = max(subtotal * surcharge_rate, max_surcharge)
    return round(subtotal + surcharge, 2)
"""
    oracle_7 = """def run_oracle():
    total = apply_credit_card_surcharge(1000.0, 0.05, 10.0)
    assert total == 1010.0, f"Expected 1010.0 capped at 10.0 surcharge, got {total}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Credit Card Surcharge Statutory Cap", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Cap surcharge at max statutory ceiling",
        observed_behavior="Uses max, exceeding surcharge ceiling", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Installment payment equal allocation
    clean_code_8 = """def calculate_installments(total_amount: float, count: int) -> list:
    if count <= 0:
        return []
    base_installment = round(total_amount / count, 2)
    installments = [base_installment] * count
    # Reconcile rounding penny on first installment
    diff = round(total_amount - sum(installments), 2)
    installments[0] = round(installments[0] + diff, 2)
    return installments
"""
    mut_code_8 = """def calculate_installments(total_amount: float, count: int) -> list:
    if count <= 0:
        return []
    base_installment = round(total_amount / count, 2)
    installments = [base_installment] * count
    return installments
"""
    oracle_8 = """def run_oracle():
    inst = calculate_installments(100.0, 3)
    assert sum(inst) == 100.0, f"Total of installments must exactly equal 100.0, got {sum(inst)}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Installment Rounding Discrepancy Reconciliation", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="DISCREPANCY_RECONCILIATION_OMISSION", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Reconcile remainder pennies across installments",
        observed_behavior="Leaves pennies unallocated losing total balance", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Dispute chargeback fee attribution
    clean_code_9 = """def apply_dispute_chargeback(balance: float, chargeback_amount: float, fee: float) -> float:
    return balance - chargeback_amount - fee
"""
    mut_code_9 = """def apply_dispute_chargeback(balance: float, chargeback_amount: float, fee: float) -> float:
    return balance - chargeback_amount + fee
"""
    oracle_9 = """def run_oracle():
    new_bal = apply_dispute_chargeback(500.0, 100.0, 15.0)
    assert new_bal == 385.0, f"Expected 385.0, got {new_bal}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Dispute Chargeback Fee Deduction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Deduct dispute fee from merchant balance",
        observed_behavior="Adds fee to merchant balance", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Minimum payment threshold check
    clean_code_10 = """def is_valid_transaction_amount(amount: float, min_limit: float, max_limit: float) -> bool:
    return min_limit <= amount <= max_limit
"""
    mut_code_10 = """def is_valid_transaction_amount(amount: float, min_limit: float, max_limit: float) -> bool:
    return min_limit < amount < max_limit
"""
    oracle_10 = """def run_oracle():
    assert is_valid_transaction_amount(1.0, 1.0, 1000.0) is True, "Exact minimum limit must be allowed"
    assert is_valid_transaction_amount(1000.0, 1.0, 1000.0) is True, "Exact maximum limit must be allowed"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Transaction Limit Boundaries", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Inclusive boundary checks",
        observed_behavior="Exclusive inequalities reject exact minimum and maximum", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Coupon code maximum usage cap
    clean_code_11 = """def can_redeem_coupon(current_usage: int, max_usage: int) -> bool:
    return current_usage < max_usage
"""
    mut_code_11 = """def can_redeem_coupon(current_usage: int, max_usage: int) -> bool:
    return current_usage <= max_usage
"""
    oracle_11 = """def run_oracle():
    assert can_redeem_coupon(100, 100) is False, "Coupon at max usage cannot be redeemed again"
    assert can_redeem_coupon(99, 100) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Coupon Usage Cap Boundary", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Reject when usage equals limit",
        observed_behavior="Allows one additional redemption beyond limit", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Multi-item basket discount allocation
    clean_code_12 = """def allocate_basket_discount(item_prices: list, discount_amount: float) -> list:
    subtotal = sum(item_prices)
    if subtotal <= 0:
        return item_prices
    factor = max(0.0, (subtotal - discount_amount) / subtotal)
    return [round(p * factor, 2) for p in item_prices]
"""
    mut_code_12 = """def allocate_basket_discount(item_prices: list, discount_amount: float) -> list:
    subtotal = sum(item_prices)
    if subtotal <= 0:
        return item_prices
    factor = (subtotal + discount_amount) / subtotal
    return [round(p * factor, 2) for p in item_prices]
"""
    oracle_12 = """def run_oracle():
    discounted = allocate_basket_discount([40.0, 60.0], 20.0)
    assert sum(discounted) == 80.0, f"Expected 80.0 after 20.0 discount, got {sum(discounted)}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Basket Discount Proportion Factor", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Proportionally reduce prices by discount",
        observed_behavior="Increases prices instead of discounting", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in transaction ledger lookup
    clean_sec_1 = """def query_transaction_ledger(db_cursor, customer_id: str):
    query = "SELECT txn_id, amount, status FROM transactions WHERE customer_id = ?"
    db_cursor.execute(query, (customer_id,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def query_transaction_ledger(db_cursor, customer_id: str):
    query = f"SELECT txn_id, amount, status FROM transactions WHERE customer_id = '{customer_id}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockLedgerCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockLedgerCur()
    query_transaction_ledger(cur, "CUST-123")
    assert cur.params is not None, "Transaction query must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Transaction Query SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized SQL query",
        observed_behavior="Unsanitized string interpolation allows SQL injection", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in receipt PDF generator
    clean_sec_2 = """import subprocess
def generate_receipt_pdf(txn_id: str, out_pdf: str):
    if not txn_id.isalnum():
        raise ValueError("Invalid transaction ID")
    subprocess.run(["receipt_tool", "--txn", txn_id, "-o", out_pdf], check=True)
"""
    mut_sec_2 = """import subprocess
def generate_receipt_pdf(txn_id: str, out_pdf: str):
    subprocess.run(f"receipt_tool --txn {txn_id} -o {out_pdf}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(generate_receipt_pdf)
    assert "shell=True" not in src, "Must avoid shell execution in receipt generation"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Receipt Generator Subprocess Shell Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Subprocess list execution without shell",
        observed_behavior="Shell execution allows command injection", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in invoice template loader
    clean_sec_3 = """import os
def load_invoice_template(template_file: str) -> str:
    base = "/app/invoices/templates"
    clean = os.path.basename(template_file)
    return os.path.join(base, clean)
"""
    mut_sec_3 = """import os
def load_invoice_template(template_file: str) -> str:
    base = "/app/invoices/templates"
    return os.path.join(base, template_file)
"""
    oracle_sec_3 = """def run_oracle():
    target = load_invoice_template("../../../etc/shadow")
    assert "/etc/shadow" not in target and ".." not in target, "Path traversal in invoice template"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Invoice Template Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=4,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize template filename with basename",
        observed_behavior="Relative directory traversal escapes template folder", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in billing statement item memo
    clean_sec_4 = """import html
def render_statement_line(memo: str) -> str:
    return f"<div class='memo'>{html.escape(memo)}</div>"
"""
    mut_sec_4 = """def render_statement_line(memo: str) -> str:
    return f"<div class='memo'>{memo}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    out = render_statement_line("<script>stealCard()</script>")
    assert "<script>" not in out and "&lt;script&gt;" in out, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Statement Memo HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in statement line",
        observed_behavior="Direct string reflection allows script injection", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on manual refund trigger
    clean_sec_5 = """def issue_manual_refund(txn_id: str, amount: float, auth_token: str) -> bool:
    if not auth_token:
        raise PermissionError("Unauthenticated refund request")
    return True
"""
    mut_sec_5 = """def issue_manual_refund(txn_id: str, amount: float, auth_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        issue_manual_refund("TX-100", 50.0, "")
        assert False, "Unauthenticated refund must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Manual Refund Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller authentication token before issuing refund",
        observed_behavior="Unauthenticated caller can issue refunds", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for fee waiver
    clean_sec_6 = """def waive_processing_fee(user_role: str, fee_amount: float) -> bool:
    return user_role in {"DISPUTE_MANAGER", "CHIEF_FINANCIAL_OFFICER"}
"""
    mut_sec_6 = """def waive_processing_fee(user_role: str, fee_amount: float) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert waive_processing_fee("SUPPORT_AGENT", 250.0) is False, "Support agent cannot waive processing fees"
    assert waive_processing_fee("DISPUTE_MANAGER", 250.0) is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Fee Waiver Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict fee waivers to authorized finance roles",
        observed_behavior="Permits arbitrary roles to waive fees", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear search in payment routing fee schedule
    clean_perf_1 = """def get_gateway_fee(fee_schedule: dict, gateway_id: str) -> float:
    return fee_schedule.get(gateway_id, 0.0)
"""
    mut_perf_1 = """def get_gateway_fee(fee_list: list, gateway_id: str) -> float:
    for g in fee_list:
        if g['id'] == gateway_id:
            return g['fee']
    return 0.0
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(get_gateway_fee)
    assert "dict" in src or "get(" in src, "Fee lookup must use O(1) dictionary"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Gateway Fee Schedule Hash Map", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="O(1) dictionary fee lookup",
        observed_behavior="O(N) linear iteration over list", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic currency rate conversion matrix lookup
    clean_perf_2 = """def find_cross_rates(pairs: list, valid_currencies: set) -> list:
    return [p for p in pairs if p['base'] in valid_currencies and p['quote'] in valid_currencies]
"""
    mut_perf_2 = """def find_cross_rates(pairs: list, valid_currencies_list: list) -> list:
    res = []
    for p in pairs:
        if p['base'] in valid_currencies_list and p['quote'] in valid_currencies_list:
            res.append(p)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(find_cross_rates)
    assert "set" in src, "Valid currencies lookup must use set for O(1) membership test"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Currency Pair Set Membership Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_MEMBERSHIP_SEARCH", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set-based cross-rate filtering",
        observed_behavior="Linear scans for base and quote in list", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized multi-step currency triangular arbitrage path evaluation
    clean_perf_3 = """def calculate_triangular_rate(chain_len: int, memo=None) -> float:
    if memo is None:
        memo = {}
    if chain_len in memo:
        return memo[chain_len]
    if chain_len <= 1:
        return 1.05
    val = (calculate_triangular_rate(chain_len - 1, memo) * 1.01) % 2.0
    memo[chain_len] = val
    return val
"""
    mut_perf_3 = """def calculate_triangular_rate(chain_len: int, memo=None) -> float:
    if chain_len <= 1:
        return 1.05
    return (calculate_triangular_rate(chain_len - 1) * 1.01) % 2.0
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(calculate_triangular_rate)
    assert "memo" in src and "memo[" in src, "Multi-step conversion rates must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Currency Path Rate Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized linear recursive evaluation",
        observed_behavior="Unmemoized recomputation", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in invoice lines builder
    clean_perf_4 = """def build_invoice_text(items: list) -> str:
    lines = ["INVOICE DETAILS\\n"]
    for it in items:
        lines.append(f"{it['name']}: ${it['price']:.2f}\\n")
    return "".join(lines)
"""
    mut_perf_4 = """def build_invoice_text(items: list) -> str:
    res = "INVOICE DETAILS\\n"
    for it in items:
        res = res + f"{it['name']}: ${it['price']:.2f}\\n"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(build_invoice_text)
    assert ".join(" in src, "Must join list buffer instead of quadratic string concatenation"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Invoice Lines Buffer Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="List buffer join",
        observed_behavior="Repeated string copies in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of credit card mask regex
    clean_perf_5 = """import re
_CARD_MASK_RE = re.compile(r"^\\d{12}(\\d{4})$")
def mask_credit_card(card_num: str) -> str:
    return _CARD_MASK_RE.sub(r"************\\1", card_num)
"""
    mut_perf_5 = """import re
def mask_credit_card(card_num: str) -> str:
    r = re.compile(r"^\\d{12}(\\d{4})$")
    return r.sub(r"************\\1", card_num)
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(mask_credit_card)
    assert "re.compile" not in src, "Regex must be precompiled at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Credit Card Masking Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled card masking pattern",
        observed_behavior="Recompiles regex on every invocation", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped zero transaction amount rejection
    clean_reg_1 = """def authorize_charge(amount: float) -> bool:
    if amount <= 0.0:
        raise ValueError("Transaction amount must be strictly positive")
    return True
"""
    mut_reg_1 = """def authorize_charge(amount: float) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        authorize_charge(0.0)
        assert False, "Regression: Zero transaction amount must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Zero Amount Authorization Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject zero amount charges",
        observed_behavior="Authorizes zero amount charges", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative refund amounts
    clean_reg_2 = """def process_refund_request(refund_amount: float) -> bool:
    if refund_amount <= 0.0:
        raise ValueError("Refund amount must be positive")
    return True
"""
    mut_reg_2 = """def process_refund_request(refund_amount: float) -> bool:
    return True
"""
    oracle_reg_2 = """def run_oracle():
    try:
        process_refund_request(-25.0)
        assert False, "Regression: Negative refund must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Refund Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative refunds",
        observed_behavior="Accepts negative refund amount", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy payment reference prefix
    clean_reg_3 = """def format_payment_reference(seq: int) -> str:
    return f"PAY-{seq:08d}"
"""
    mut_reg_3 = """def format_payment_reference(seq: int) -> str:
    return f"{seq:08d}"
"""
    oracle_reg_3 = """def run_oracle():
    ref = format_payment_reference(101)
    assert ref == "PAY-00000101", f"Expected PAY-00000101, got {ref}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payment Reference Prefix Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include PAY- prefix",
        observed_behavior="Drops PAY- prefix", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in currency code
    clean_reg_4 = """def normalize_currency_code(code: str) -> str:
    cleaned = code.strip().upper()
    if len(cleaned) != 3:
        raise ValueError("Currency must be 3 characters")
    return cleaned
"""
    mut_reg_4 = """def normalize_currency_code(code: str) -> str:
    return code.upper()
"""
    oracle_reg_4 = """def run_oracle():
    c = normalize_currency_code(" eur ")
    assert c == "EUR", f"Expected 'EUR' without spaces, got '{c}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Currency Code Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before validation",
        observed_behavior="Fails to strip leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on billing address line 2
    clean_reg_5 = """def format_billing_address(line1: str, line2: str) -> str:
    if not line2:
        return line1.strip()
    return f"{line1.strip()}, {line2.strip()}"
"""
    mut_reg_5 = """def format_billing_address(line1: str, line2: str) -> str:
    return f"{line1.strip()}, {line2.strip()}"
"""
    oracle_reg_5 = """def run_oracle():
    assert format_billing_address("123 Main St", None) == "123 Main St", "None line2 must not crash"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Billing Address Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None line2 gracefully",
        observed_behavior="Raises AttributeError on None line2", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed payload key in stripe payment intent adapter
    clean_integ_1 = """def prepare_intent_payload(amount_cents: int, currency: str) -> dict:
    return {"amount_in_cents": amount_cents, "currency_iso": currency}
"""
    mut_integ_1 = """def prepare_intent_payload(amount_cents: int, currency: str) -> dict:
    return {"amount": amount_cents, "curr": currency}
"""
    oracle_integ_1 = """def run_oracle():
    p = prepare_intent_payload(1000, "USD")
    assert "amount_in_cents" in p and "currency_iso" in p, "Gateway client requires amount_in_cents and currency_iso"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payment Intent Payload Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Exact contract payload keys",
        observed_behavior="Emits renamed keys breaking payment gateway integration", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs list) in settlement breakdown
    clean_integ_2 = """def fetch_settlement_summary(batch_id: str) -> dict:
    return {"batch_id": batch_id, "gross": 500.0, "net": 485.0}
"""
    mut_integ_2 = """def fetch_settlement_summary(batch_id: str) -> list:
    return [batch_id, 500.0, 485.0]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_settlement_summary("B-1")
    assert isinstance(res, dict) and "net" in res, "Consumer expects settlement dict"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Settlement Summary Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST schema",
        observed_behavior="Returns plain list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing idempotency key header in payment gateway dispatcher
    clean_integ_3 = """def build_gateway_headers(token: str, idem_key: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key, "Content-Type": "application/json"}
"""
    mut_integ_3 = """def build_gateway_headers(token: str, idem_key: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_gateway_headers("tok", "idempotent_123")
    assert "Idempotency-Key" in h, "Payment gateway requires Idempotency-Key header to prevent duplicate charges"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Gateway Idempotency Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_REQUIRED_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include Idempotency-Key header",
        observed_behavior="Omits Idempotency-Key header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in bank reconciliation report
    clean_integ_4 = """def format_reconciliation_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_reconciliation_date(year: int, month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_reconciliation_date(2026, 11, 4)
    assert d == "2026-11-04", f"Reconciliation API expects YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Bank Reconciliation Date Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Locale slash date format", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Currency code lowercase casing mismatch in gateway dispatch
    clean_integ_5 = """def serialize_payment_currency(curr: str) -> str:
    return curr.strip().upper()
"""
    mut_integ_5 = """def serialize_payment_currency(curr: str) -> str:
    return curr.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_payment_currency("usd") == "USD", "Payment gateway requires ISO-4217 uppercase currency"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payment Gateway ISO 4217 Casing", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase currency code",
        observed_behavior="Emits lowercase currency code", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened fraud check: omitting CVV verification
    clean_drift_1 = """def verify_card_security_checks(checks: dict) -> bool:
    return checks.get("avs_passed", False) and checks.get("cvv_passed", False)
"""
    mut_drift_1 = """def verify_card_security_checks(checks: dict) -> bool:
    # Drift: loosened requirement to only check AVS address verification
    return checks.get("avs_passed", False)
"""
    oracle_drift_1 = """def run_oracle():
    checks = {"avs_passed": True, "cvv_passed": False}
    assert verify_card_security_checks(checks) is False, "Drift: Failed CVV must reject payment"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Card CVV Verification Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both AVS and CVV security checks",
        observed_behavior="Loosens invariant allowing failed CVV payments", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping non-profit tax exemption tag
    clean_drift_2 = """def compute_final_tax(subtotal: float, is_nonprofit: bool, tax_rate: float) -> float:
    if is_nonprofit:
        return 0.0
    return round(subtotal * tax_rate, 2)
"""
    mut_drift_2 = """def compute_final_tax(subtotal: float, is_nonprofit: bool, tax_rate: float) -> float:
    # Drift: tax exemption flag silently ignored
    return round(subtotal * tax_rate, 2)
"""
    oracle_drift_2 = """def run_oracle():
    tax = compute_final_tax(100.0, True, 0.10)
    assert tax == 0.0, f"Drift: Nonprofit must be exempt from tax, got {tax}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Nonprofit Tax Exemption Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Exempt registered nonprofits from tax",
        observed_behavior="Silently charges tax to exempt entities", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum single transaction limit invariant removal
    clean_drift_3 = """def validate_max_transaction_size(amount: float, max_allowed: float) -> bool:
    if amount > max_allowed:
        return False
    return True
"""
    mut_drift_3 = """def validate_max_transaction_size(amount: float, max_allowed: float) -> bool:
    # Drift: maximum limit check removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_max_transaction_size(50000.0, 10000.0) is False, "Drift: Amount exceeding max limit must be rejected"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Max Transaction Limit Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Reject transactions exceeding cap",
        observed_behavior="Unconditionally permits unbounded charges", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in multi-currency settlement
    clean_drift_4 = """def convert_settlement_units(amount: float, fx_rate: float) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    dec_val = Decimal(str(amount)) * Decimal(str(fx_rate))
    return float(dec_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def convert_settlement_units(amount: float, fx_rate: float) -> float:
    # Drift: integer cents truncation
    return float(int(amount * fx_rate * 100) / 100.0)
"""
    oracle_drift_4 = """def run_oracle():
    res = convert_settlement_units(10.0, 1.0055)
    assert res == 10.06, f"Expected 10.06 after half-up rounding, got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Settlement FX Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Strict decimal half-up rounding",
        observed_behavior="Integer truncation drops fractional cent", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting tax jurisdiction requirements
    clean_conv_1 = """def check_jurisdiction_tax_tier(amount: float) -> bool:
    # Harmonized spec: valid tier between 50.0 and 500.0
    return 50.0 <= amount <= 500.0
"""
    mut_conv_1 = """def check_jurisdiction_tax_tier(amount: float) -> bool:
    # Invariant conflict: Rule A requires amount < 40.0, Rule B requires amount > 100.0
    return amount < 40.0 and amount > 100.0
"""
    oracle_conv_1 = """def run_oracle():
    assert check_jurisdiction_tax_tier(150.0) is True, "Harmonized rule permits 150.0"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tax Jurisdiction Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid tax tier range",
        observed_behavior="Mutually contradictory rules (amount < 40 AND amount > 100)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: discount tier operator flip-flop
    clean_conv_2 = """def evaluate_tier_qualifier(spending: float, threshold: float) -> str:
    if spending >= threshold:
        return "TIER_QUALIFIED"
    return "STANDARD"
"""
    mut_conv_2 = """def evaluate_tier_qualifier(spending: float, threshold: float) -> str:
    if spending > threshold:
        return "TIER_QUALIFIED"
    return "STANDARD"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_tier_qualifier(100.0, 100.0) == "TIER_QUALIFIED", "Exact threshold qualifies"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tier Qualifier Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary qualifies",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in payment settlement workflow
    clean_conv_3 = """def advance_payment_lifecycle(state: str) -> str:
    flow = {"INITIATED": "AUTHORIZED", "AUTHORIZED": "CAPTURED", "CAPTURED": "SETTLED", "SETTLED": "SETTLED"}
    return flow.get(state, "INITIATED")
"""
    mut_conv_3 = """def advance_payment_lifecycle(state: str) -> str:
    # Circular loop between CAPTURED and AUTHORIZED
    flow = {"INITIATED": "AUTHORIZED", "AUTHORIZED": "CAPTURED", "CAPTURED": "AUTHORIZED", "SETTLED": "SETTLED"}
    return flow.get(state, "INITIATED")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_payment_lifecycle(advance_payment_lifecycle("AUTHORIZED"))
    assert res == "SETTLED", "State progression must reach terminal SETTLED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Payment Lifecycle State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to SETTLED",
        observed_behavior="Infinite oscillation between AUTHORIZED and CAPTURED",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def payment_clean_routine_{c_idx}(val: float) -> float:
    # Clean control {c_idx}: verified pricing calculation with boundary protection
    if val < 0.0:
        return 0.0
    return round((val * 1.05) + {c_idx}, 2)
"""
        oracle_c = f"""def run_oracle():
    res = payment_clean_routine_{c_idx}(100.0)
    assert res == 105.0 + {c_idx}, f"Expected {{105.0 + {c_idx}}}, got {{res}}"
    assert payment_clean_routine_{c_idx}(-10.0) == 0.0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Payment Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified payment calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
