import asyncio
import os
import pytest
from starlette.testclient import TestClient

# Ensure test environment variables
os.environ["ENVIRONMENT"] = "testing"
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["DEBUG"] = "False"

from app.main import app
from app.repositories import _in_memory_submission_repo, _in_memory_verification_repo


@pytest.fixture(autouse=True)
def reset_in_memory_repositories():
    """Clears in-memory repositories before and after each test for complete state isolation."""
    asyncio.run(_in_memory_submission_repo.clear())
    asyncio.run(_in_memory_verification_repo.clear())
    yield
    asyncio.run(_in_memory_submission_repo.clear())
    asyncio.run(_in_memory_verification_repo.clear())


@pytest.fixture
def client():
    """Synchronous test client for testing FastAPI endpoints."""
    with TestClient(app) as test_client:
        yield test_client
