"""Shared pytest fixtures for the Component 3 API."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from intelise_c3.core.config import get_settings
from intelise_c3.main import create_app


@pytest.fixture
def application() -> Iterator[FastAPI]:
    """Create an isolated application instance for each test."""
    get_settings.cache_clear()
    test_application = create_app()
    yield test_application
    get_settings.cache_clear()


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    """Provide an HTTP client for the isolated application."""
    with TestClient(application) as test_client:
        yield test_client
