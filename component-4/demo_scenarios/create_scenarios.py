"""
Script to create the 3 Supervisor Demonstration Scenarios for INTELISE Component 4.
Generates both uncompressed project folders and safe .zip archives.
"""
import os
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def create_scenario_a():
    """Scenario A: Multi-file Python login project with genuine defect."""
    scen_dir = os.path.join(BASE_DIR, "scenario_a_login")
    os.makedirs(os.path.join(scen_dir, "auth"), exist_ok=True)
    os.makedirs(os.path.join(scen_dir, "tests"), exist_ok=True)

    # auth/__init__.py
    with open(os.path.join(scen_dir, "auth", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Authentication package."""\n')

    # auth/models.py
    with open(os.path.join(scen_dir, "auth", "models.py"), "w", encoding="utf-8") as f:
        f.write('''"""User and Session data models."""
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    username: str
    password_hash: str
    email: str
    is_active: bool = True
    failed_attempts: int = 0

@dataclass
class AuthSession:
    token: str
    username: str
    role: str
''')

    # auth/hasher.py
    with open(os.path.join(scen_dir, "auth", "hasher.py"), "w", encoding="utf-8") as f:
        f.write('''"""Password hashing utility using SHA-256 with salt."""
import hashlib

SALT = "intelise_demo_salt_2026"

def hash_password(password: str) -> str:
    combined = f"{SALT}:{password}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password
''')

    # auth/service.py - DEFECTIVE VERSION
    # Line 28 has the defect: comparing hashed password directly with plain text password!
    service_defective = '''"""Authentication service handling user login and session creation."""
import uuid
from typing import Optional, Dict
from auth.models import User, AuthSession
from auth.hasher import hash_password, verify_password

class AuthService:
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._active_sessions: Dict[str, AuthSession] = {}

    def register_user(self, username: str, password: str, email: str) -> User:
        user = User(
            username=username,
            password_hash=hash_password(password),
            email=email
        )
        self._users[username] = user
        return user

    def authenticate(self, username: str, password: str) -> Optional[AuthSession]:
        user = self._users.get(username)
        if not user or not user.is_active:
            return None

        # DEFECT on line 28: comparing stored hash directly with raw plain password instead of verify_password
        if user.password_hash != password:
            user.failed_attempts += 1
            return None

        token = f"tok_{uuid.uuid4().hex[:12]}"
        session = AuthSession(token=token, username=username, role="standard_user")
        self._active_sessions[token] = session
        return session

    def validate_session(self, token: str) -> Optional[AuthSession]:
        return self._active_sessions.get(token)
'''
    with open(os.path.join(scen_dir, "auth", "service.py"), "w", encoding="utf-8") as f:
        f.write(service_defective)

    # tests/__init__.py
    with open(os.path.join(scen_dir, "tests", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Test suite for authentication module."""\n')

    # tests/test_auth.py
    with open(os.path.join(scen_dir, "tests", "test_auth.py"), "w", encoding="utf-8") as f:
        f.write('''"""Pytest suite for AuthService verification."""
import pytest
from auth.service import AuthService
from auth.hasher import hash_password

@pytest.fixture
def auth_service():
    service = AuthService()
    service.register_user("alice", "Password123!", "alice@example.com")
    service.register_user("bob", "SecurePass456!", "bob@example.com")
    return service

def test_login_success(auth_service):
    """Verifies that a registered user can successfully authenticate with valid credentials."""
    session = auth_service.authenticate("alice", "Password123!")
    assert session is not None, "Authentication failed for valid user credentials"
    assert session.username == "alice"
    assert session.token.startswith("tok_")

def test_login_invalid_password(auth_service):
    """Verifies that authentication fails when given an incorrect password."""
    session = auth_service.authenticate("alice", "WrongPassword!")
    assert session is None

def test_login_unknown_user(auth_service):
    """Verifies that authentication fails for an unregistered username."""
    session = auth_service.authenticate("unknown_user", "AnyPassword")
    assert session is None
''')

    # Create ZIP archive for defective version
    zip_path_defective = os.path.join(BASE_DIR, "demo_scenario_a_login_defective.zip")
    with zipfile.ZipFile(zip_path_defective, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(scen_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, scen_dir)
                zf.write(full_path, rel_path)

    # Also prepare the fixed code for auth/service.py
    service_fixed = service_defective.replace(
        "        # DEFECT on line 28: comparing stored hash directly with raw plain password instead of verify_password\n        if user.password_hash != password:",
        "        # REPAIRED: using verify_password to check salted SHA-256 hash\n        if not verify_password(password, user.password_hash):"
    )
    with open(os.path.join(BASE_DIR, "scenario_a_login_service_repaired.py"), "w", encoding="utf-8") as f:
        f.write(service_fixed)

    print(f"Created Scenario A at {zip_path_defective}")


def create_scenario_b():
    """Scenario B: Project with persistent regression / blocked delivery governance."""
    scen_dir = os.path.join(BASE_DIR, "scenario_b_blocked")
    os.makedirs(os.path.join(scen_dir, "ecommerce"), exist_ok=True)
    os.makedirs(os.path.join(scen_dir, "tests"), exist_ok=True)

    with open(os.path.join(scen_dir, "ecommerce", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Ecommerce core package."""\n')

    with open(os.path.join(scen_dir, "ecommerce", "cart.py"), "w", encoding="utf-8") as f:
        f.write('''"""Shopping cart and pricing logic with critical calculation defect."""
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
''')

    with open(os.path.join(scen_dir, "tests", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Ecommerce tests."""\n')

    with open(os.path.join(scen_dir, "tests", "test_cart.py"), "w", encoding="utf-8") as f:
        f.write('''"""Pytest suite for ShoppingCart."""
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
''')

    zip_path = os.path.join(BASE_DIR, "demo_scenario_b_blocked_governance.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(scen_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, scen_dir)
                zf.write(full_path, rel_path)

    print(f"Created Scenario B at {zip_path}")


def create_scenario_c():
    """Scenario C: Clean verified project with 100% test pass, reaching Post-Delivery XAI."""
    scen_dir = os.path.join(BASE_DIR, "scenario_c_clean")
    os.makedirs(os.path.join(scen_dir, "analytics"), exist_ok=True)
    os.makedirs(os.path.join(scen_dir, "tests"), exist_ok=True)

    with open(os.path.join(scen_dir, "analytics", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Analytics calculations package."""\n')

    with open(os.path.join(scen_dir, "analytics", "statistics.py"), "w", encoding="utf-8") as f:
        f.write('''"""Statistical metrics calculation module."""
from typing import List, Optional

def compute_mean(data: List[float]) -> Optional[float]:
    if not data:
        return None
    return sum(data) / len(data)

def compute_median(data: List[float]) -> Optional[float]:
    if not data:
        return None
    sorted_data = sorted(data)
    n = len(sorted_data)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_data[mid])
    return (sorted_data[mid - 1] + sorted_data[mid]) / 2.0

def compute_variance(data: List[float]) -> Optional[float]:
    if not data or len(data) < 2:
        return 0.0
    mean_val = compute_mean(data)
    return sum((x - mean_val) ** 2 for x in data) / (len(data) - 1)
''')

    with open(os.path.join(scen_dir, "tests", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Test suite for analytics package."""\n')

    with open(os.path.join(scen_dir, "tests", "test_statistics.py"), "w", encoding="utf-8") as f:
        f.write('''"""Pytest suite for statistics module."""
from analytics.statistics import compute_mean, compute_median, compute_variance

def test_mean_calculation():
    assert compute_mean([10.0, 20.0, 30.0]) == 20.0
    assert compute_mean([]) is None

def test_median_odd_and_even():
    assert compute_median([3.0, 1.0, 2.0]) == 2.0
    assert compute_median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert compute_median([]) is None

def test_variance_calculation():
    assert compute_variance([2.0, 4.0, 6.0]) == 4.0
    assert compute_variance([5.0]) == 0.0
''')

    zip_path = os.path.join(BASE_DIR, "demo_scenario_c_clean_delivery_xai.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(scen_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, scen_dir)
                zf.write(full_path, rel_path)

    print(f"Created Scenario C at {zip_path}")


if __name__ == "__main__":
    create_scenario_a()
    create_scenario_b()
    create_scenario_c()
    print("All 3 demo scenarios created successfully.")
