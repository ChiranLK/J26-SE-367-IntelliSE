from shop.pricing import apply_discount, calculate_subtotal


def test_unit_calculate_subtotal():
    assert calculate_subtotal([40.0, 60.0]) == 100.0


def test_unit_apply_discount():
    assert apply_discount(100.0, 0.10) == 90.0
