"""Pytest suite for AuthService verification."""
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
