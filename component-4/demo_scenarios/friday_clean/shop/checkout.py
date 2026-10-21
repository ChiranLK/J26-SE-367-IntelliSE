from shop.pricing import apply_discount, calculate_subtotal


def checkout_total(prices: list[float], discount_rate: float, tax_rate: float) -> float:
    """Combine pricing and tax calculations for the checkout boundary."""
    discounted = apply_discount(calculate_subtotal(prices), discount_rate)
    return round(discounted * (1 + tax_rate), 2)
