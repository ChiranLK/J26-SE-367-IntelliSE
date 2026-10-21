"""Deletion API safety without real storage; real MongoDB checked separately."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from bson import ObjectId
from pymongo.errors import OperationFailure

from test_projects import client  # noqa: F401

ROOT = '/api/v1/component-1/projects'
ID = '507f1f77bcf86cd799439011'


def test_delete_success_and_unknown_project(client):
    method = AsyncMock(return_value=True)
    client.app.state.projects = SimpleNamespace(delete=method)
    response = client.delete(f'{ROOT}/{ID}')
    assert response.status_code == 204 and response.content == b''
    method.assert_awaited_once_with(ObjectId(ID))
    method.return_value = False
    assert client.delete(f'{ROOT}/{ID}').status_code == 404


def test_invalid_id_no_database_call(client):
    method = AsyncMock()
    client.app.state.projects = SimpleNamespace(delete=method)
    assert client.delete(f'{ROOT}/bad').status_code == 422
    method.assert_not_awaited()


def test_database_failures_sanitized_and_health_available(client, caplog):
    assert client.delete(f'{ROOT}/{ID}').status_code == 503
    client.app.state.projects = SimpleNamespace(delete=AsyncMock(side_effect=OperationFailure('private source credentials')))
    response = client.delete(f'{ROOT}/{ID}')
    assert response.status_code == 503
    assert 'private source credentials' not in response.text + caplog.text
    assert client.get('/api/v1/component-1/health').status_code == 200


def test_delete_preflight_allowed(client):
    response = client.options(f'{ROOT}/{ID}', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'DELETE'})
    assert response.status_code == 200
    assert 'DELETE' in response.headers['access-control-allow-methods']
