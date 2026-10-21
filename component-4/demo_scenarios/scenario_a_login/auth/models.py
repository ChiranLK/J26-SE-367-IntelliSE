"""User and Session data models."""
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
