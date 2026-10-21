"""Password hashing utility using SHA-256 with salt."""
import hashlib

SALT = "intelise_demo_salt_2026"

def hash_password(password: str) -> str:
    combined = f"{SALT}:{password}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password
