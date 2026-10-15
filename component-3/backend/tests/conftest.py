"""Shared pytest fixtures for the Component 3 API."""

from collections.abc import Iterator
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from intelise_c3.core.config import get_settings
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.main import create_app
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "simulated"


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


@pytest.fixture
def generation_context() -> GenerationContext:
    """Build an accepted immutable context from the simulated valid package."""
    payload = json.loads(
        (FIXTURE_DIRECTORY / "valid_input_package.json").read_text(encoding="utf-8")
    )
    package = ProvisionalInputPackage.model_validate(payload)
    return InputValidationService().validate(package)


@pytest.fixture
def design_context(generation_context: GenerationContext) -> DesignContext:
    """Build a normalized design context using the supported PlantUML subset."""
    return DesignUnderstandingService().build(generation_context)
