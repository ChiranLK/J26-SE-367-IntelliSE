"""Tests for application initialization and health reporting."""

from fastapi import FastAPI, status
from fastapi.testclient import TestClient


def test_application_initializes_successfully(
    application: FastAPI, client: TestClient
) -> None:
    assert isinstance(application, FastAPI)
    assert application.title == "intelise-component-3"

    response = client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK


def test_health_endpoint_returns_http_200(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK


def test_health_response_matches_expected_structure(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.json() == {
        "service_name": "intelise-component-3",
        "status": "healthy",
        "api_version": "v1",
    }
