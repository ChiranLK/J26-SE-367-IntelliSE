def calculate_subtotal(prices: list[float]) -> float:
    """Return the sum of non-negative item prices."""
    if any(price < 0 for price in prices):
        raise ValueError("prices must be non-negative")
    return round(sum(prices), 2)


def apply_discount(subtotal: float, discount_rate: float) -> float:
    """Apply a fractional discount rate to a subtotal."""
    if not 0 <= discount_rate <= 1:
        raise ValueError("discount_rate must be between 0 and 1")
    return round(subtotal * (1 - discount_rate), 2)
