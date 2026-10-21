"""Authentication service handling user login and session creation."""
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

        # REPAIRED: using verify_password to check salted SHA-256 hash
        if not verify_password(password, user.password_hash):
            user.failed_attempts += 1
            return None

        token = f"tok_{uuid.uuid4().hex[:12]}"
        session = AuthSession(token=token, username=username, role="standard_user")
        self._active_sessions[token] = session
        return session

    def validate_session(self, token: str) -> Optional[AuthSession]:
        return self._active_sessions.get(token)
