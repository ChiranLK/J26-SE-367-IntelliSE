"""Shopping cart and pricing logic with critical calculation defect."""
from typing import List, Dict

class ShoppingCart:
    def __init__(self):
        self.items: List[Dict[str, float]] = []

    def add_item(self, name: str, price: float, quantity: int = 1):
        self.items.append({"name": name, "price": price, "quantity": quantity})

    def calculate_total(self, discount_pct: float = 0.0) -> float:
        subtotal = sum(item["price"] * item["quantity"] for item in self.items)
        # DEFECT: inverted discount logic adding discount instead of subtracting
        discount = subtotal * (discount_pct / 100.0)
        return subtotal + discount  # CRITICAL DEFECT
