"""Tests for environment-based Component 3 settings."""

from intelise_c3.core.config import Settings


def test_configuration_defaults_are_valid(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.service_name == "intelise-component-3"
    assert settings.api_version == "v1"
    assert str(settings.ollama_base_url).rstrip("/") == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen2.5-coder:3b"


def test_environment_overrides_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:23456")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    settings = Settings(_env_file=None)

    assert str(settings.ollama_base_url).rstrip("/") == "http://localhost:23456"
    assert settings.ollama_model == "qwen2.5-coder:7b"
