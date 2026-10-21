from shop.checkout import checkout_total


def test_integration_checkout_uses_pricing_discount_and_tax():
    assert checkout_total([40.0, 60.0], discount_rate=0.10, tax_rate=0.10) == 99.0
