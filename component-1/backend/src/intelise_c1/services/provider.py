"""Anthropic Messages adapter; no retries, fallback results, or sensitive logs."""
import asyncio
import json

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from intelise_c1.api.extraction_schemas import ExtractionOutput
from intelise_c1.core.config import Settings
from intelise_c1.services.extraction import InvalidExtraction, SYSTEM_PROMPT


class ProviderUnavailable(Exception):
    pass


class ProviderTimeout(Exception):
    pass


class TextBlock(BaseModel):
    model_config = ConfigDict(strict=True)

    type: str
    text: str


class ProviderMessage(BaseModel):
    """Validate the envelope too; an empty/malformed block is never a success.

    Additional envelope metadata (usage, model, IDs) is intentionally ignored.
    """

    model_config = ConfigDict(strict=True)

    stop_reason: str
    content: list[TextBlock]


def provider_schema() -> dict:
    # Anthropic's constrained grammar supports only a subset of JSON Schema.
    # Enforce all size/range constraints locally after receiving the result.
    def clean(value):
        if isinstance(value, dict):
            constraints = {"minLength", "maxLength", "minItems", "maxItems", "minimum", "exclusiveMinimum"}
            result = {key: clean(item) for key, item in value.items() if key not in constraints}
            limits = {key: item for key, item in value.items() if key in constraints}
            if limits:
                result["description"] = result.get("description", "") + " Local validation limits: " + json.dumps(limits)
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(ExtractionOutput.model_json_schema())


class AnthropicProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_identifier = settings.llm_model

    async def extract(self, discussion: str) -> ExtractionOutput:
        key = self.settings.anthropic_api_key
        if key is None or not key.get_secret_value().strip() or not self.model_identifier.strip():
            raise ProviderUnavailable()
        payload = {
            "model": self.model_identifier,
            "max_tokens": self.settings.llm_max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": json.dumps({"discussion_text": discussion}, ensure_ascii=False)}],
            "output_config": {"format": {"type": "json_schema", "schema": provider_schema()}},
        }
        try:
            async with asyncio.timeout(self.settings.llm_timeout_seconds):
                async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                    async with client.stream(
                        "POST", "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": key.get_secret_value(), "anthropic-version": "2023-06-01"},
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            raise ProviderUnavailable()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.settings.llm_response_max_bytes:
                                raise InvalidExtraction()
            message = ProviderMessage.model_validate_json(body)
            if message.stop_reason != "end_turn":
                raise InvalidExtraction()
            blocks = message.content
            if len(blocks) != 1 or blocks[0].type != "text":
                raise InvalidExtraction()
            return ExtractionOutput.model_validate_json(blocks[0].text)
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderTimeout() from None
        except httpx.HTTPError:
            raise ProviderUnavailable() from None
        except (ValueError, ValidationError):
            raise InvalidExtraction() from None
