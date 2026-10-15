"""Local-only LLM integration for Component 3."""

from intelise_c3.llm.client import LLMClient
from intelise_c3.llm.ollama import OllamaLLMClient

__all__ = ["LLMClient", "OllamaLLMClient"]
