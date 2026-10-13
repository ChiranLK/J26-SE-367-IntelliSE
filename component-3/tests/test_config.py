"""Tests for environment-based Component 3 settings."""

import pytest
from pydantic import ValidationError

from intelise_c3.core.config import COMPONENT_ROOT, Settings


def test_configuration_defaults_are_valid(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OLLAMA_TEMPERATURE", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GENERATED_WORKSPACE_ROOT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.service_name == "intelise-component-3"
    assert settings.api_version == "v1"
    assert str(settings.ollama_base_url).rstrip("/") == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen2.5-coder:3b"
    assert settings.ollama_timeout_seconds == 120.0
    assert settings.ollama_temperature == 0.0
    assert settings.ollama_num_ctx == 4096
    assert settings.generated_workspace_root.name == "generated-workspaces"


def test_environment_overrides_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:23456")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.2")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("GENERATED_WORKSPACE_ROOT", "custom-workspaces")

    settings = Settings(_env_file=None)

    assert str(settings.ollama_base_url).rstrip("/") == "http://localhost:23456"
    assert settings.ollama_model == "qwen2.5-coder:7b"
    assert settings.ollama_timeout_seconds == 45.0
    assert settings.ollama_temperature == 0.2
    assert settings.ollama_num_ctx == 8192
    assert settings.generated_workspace_root.name == "custom-workspaces"


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://ollama.com",
        "http://192.168.1.50:11434",
        "http://example.com:11434",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:11434/proxy",
    ),
)
def test_non_local_or_credentialed_ollama_endpoint_is_rejected(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_base_url=endpoint, _env_file=None)


@pytest.mark.parametrize("model", ("gemma4:cloud", "gpt-oss:120b-cloud"))
def test_ollama_cloud_model_identifiers_are_rejected(model: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_model=model, _env_file=None)


def test_generated_workspace_root_cannot_escape_component_directory() -> None:
    with pytest.raises(ValidationError):
        Settings(
            generated_workspace_root=COMPONENT_ROOT.parent / "outside-c3",
            _env_file=None,
        )
