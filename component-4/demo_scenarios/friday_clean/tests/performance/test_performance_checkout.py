import time

from shop.checkout import checkout_total


def test_performance_checkout_under_50ms():
    started = time.perf_counter()
    checkout_total([1.0] * 1000, discount_rate=0.10, tax_rate=0.10)
    measured_ms = (time.perf_counter() - started) * 1000
    assert measured_ms < 50.0, f"Measured {measured_ms:.3f}ms; threshold is 50.000ms"
