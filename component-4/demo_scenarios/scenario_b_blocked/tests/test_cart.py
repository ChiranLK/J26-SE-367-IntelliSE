"""Pytest suite for ShoppingCart."""
import pytest
from ecommerce.cart import ShoppingCart

def test_cart_subtotal():
    cart = ShoppingCart()
    cart.add_item("Widget", 20.0, 2)
    assert cart.calculate_total(0.0) == 40.0

def test_cart_discount_calculation():
    cart = ShoppingCart()
    cart.add_item("Gadget", 100.0, 1)
    # 20% discount on $100 should be $80, but defective code returns $120
    assert cart.calculate_total(20.0) == 80.0
