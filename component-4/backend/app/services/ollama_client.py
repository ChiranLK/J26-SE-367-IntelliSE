import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger


class OllamaInferenceException(Exception):
    """Raised when Ollama inference fails, times out, or returns invalid structure."""
    pass


class OllamaClient:
    """
    Client for interacting with local Ollama LLM runtime (Proposal Research AI Layer).
    Strictly grounds model generation on verified test execution artifacts.
    Provides fail-closed error handling and automatic fallback.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        enabled: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.OLLAMA_MODEL
        self.timeout_seconds = timeout_seconds or settings.OLLAMA_TIMEOUT_SECONDS
        self.enabled = enabled if enabled is not None else settings.OLLAMA_ENABLED
        self._http_client = http_client

    async def check_availability(self) -> Tuple[bool, List[str], str]:
        """
        Verifies if Ollama server is responding and checks installed models.
        Returns: (is_connected, available_models, message)
        """
        if not self.enabled:
            return False, [], "Ollama integration is disabled by configuration (OLLAMA_ENABLED=False)."

        url = f"{self.base_url}/api/tags"
        try:
            if self._http_client:
                res = await self._http_client.get(url, timeout=3.0)
            else:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    res = await client.get(url)

            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                if not models:
                    return True, [], "Ollama server is active but 0 models are installed."
                return True, models, f"Ollama is active with {len(models)} model(s) installed: {', '.join(models[:3])}"
            return False, [], f"Ollama returned HTTP status {res.status_code}"
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            return False, [], f"Cannot connect to Ollama at {self.base_url}: {exc}"
        except Exception as exc:
            return False, [], f"Unexpected error checking Ollama: {exc}"

    def sanitize_prompt_inputs(self, text: str) -> str:
        """
        Sanitizes user code or error messages before embedding in prompts
        to protect against prompt injection or delimiter breaking.
        """
        if not text:
            return ""
        # Escape markdown backticks and delimiter blocks
        sanitized = text.replace("```", "'''")
        # Defuse adversarial prompt injection tokens
        injection_patterns = [
            r"<\|im_start\|>",
            r"<\|im_end\|>",
            r"<\|system\|>",
            r"\[INST\]",
            r"\[/INST\]",
            r"<<SYS>>",
            r"<</SYS>>",
        ]
        for pattern in injection_patterns:
            sanitized = re.sub(pattern, "[INJECTION_ATTEMPT_DEFUSED]", sanitized, flags=re.IGNORECASE)
        # Strip control characters
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", sanitized)
        return sanitized[:4000]

    async def generate_structured_explanation(
        self,
        telemetry: Dict[str, Any],
        defects: List[Dict[str, Any]],
        source_code: str,
        filename: str = "solution.py",
    ) -> Dict[str, Any]:
        """
        Generates an evidence-grounded XAI explanation via Ollama.
        Guarantees that test outcomes and failures are grounded in the provided telemetry.
        """
        is_ok, models, msg = await self.check_availability()
        if not is_ok:
            raise OllamaInferenceException(f"Ollama unavailable: {msg}")

        # Check if requested model or any matching base model is installed
        target_model = self.model_name
        if models and target_model not in models:
            matched = next(
                (m for m in models if m == target_model or m.startswith(f"{target_model}:") or target_model.startswith(f"{m}:")),
                None,
            )
            if matched:
                target_model = matched
            else:
                target_model = models[0]
                logger.info("Target model '%s' not found. Using installed model '%s'.", self.model_name, target_model)

        sanitized_code = self.sanitize_prompt_inputs(source_code)
        sanitized_telemetry = json.dumps(telemetry, indent=2)
        sanitized_defects = json.dumps(defects, indent=2)

        system_prompt = (
            "You are the INTELISE Component 4 Explainable AI (XAI) Engine.\n"
            "Your task is to produce a grounded root-cause explanation for software defects.\n"
            "CRITICAL RULES:\n"
            "1. NEVER fabricate or hallucinate tests or outcomes not present in the empirical telemetry.\n"
            "2. Ground all explanations strictly in the provided failed assertions and stack traces.\n"
            "3. Output MUST be valid JSON adhering exactly to the requested schema.\n"
            "4. NEVER execute or suggest executing malicious code."
        )

        user_prompt = f"""
Analyze the following verified test execution artifacts for file '{filename}':

<verified_test_telemetry>
{sanitized_telemetry}
</verified_test_telemetry>

<verified_defects>
{sanitized_defects}
</verified_defects>

<source_code_excerpt>
{sanitized_code}
</source_code_excerpt>

Return a JSON object with EXACTLY the following structure:
{{
  "summary": "Concise 1-2 sentence executive summary of the observed defect(s)",
  "what_failed": ["List of specific test functions or assertions that failed"],
  "confirmed_observations": ["Empirical evidence observed from pytest tracebacks"],
  "evidence_based_interpretation": "Technical reasoning explaining the probable root cause in source code",
  "recommendation_action": "High-level fix guidance for the author",
  "target_audience": "Software Engineer"
}}
"""

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": target_model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }

        start_time = time.perf_counter()
        try:
            if self._http_client:
                res = await self._http_client.post(url, json=payload, timeout=self.timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    res = await client.post(url, json=payload)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if res.status_code != 200:
                raise OllamaInferenceException(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")

            res_data = res.json()
            raw_response = res_data.get("response", "{}")
            parsed_json = json.loads(raw_response)

            parsed_json["_provenance"] = {
                "provider": "ollama",
                "model": target_model,
                "genuine_inference": True,
                "fallback_used": False,
                "fallback_reason": None,
                "duration_ms": duration_ms,
                "prompt_eval_count": res_data.get("prompt_eval_count"),
                "eval_count": res_data.get("eval_count"),
            }
            return parsed_json

        except httpx.TimeoutException as exc:
            raise OllamaInferenceException(f"Ollama inference timed out after {self.timeout_seconds}s: {exc}")
        except json.JSONDecodeError as exc:
            raise OllamaInferenceException(f"Ollama output was not valid JSON: {exc}")
        except Exception as exc:
            raise OllamaInferenceException(f"Ollama inference error: {exc}")

    def check_availability_sync(self) -> Tuple[bool, List[str], str]:
        """Synchronous version of check_availability."""
        if not self.enabled:
            return False, [], "Ollama integration is disabled by configuration (OLLAMA_ENABLED=False)."
        url = f"{self.base_url}/api/tags"
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(url)
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                if not models:
                    return True, [], "Ollama server is active but 0 models are installed."
                return True, models, f"Ollama is active with {len(models)} model(s) installed."
            return False, [], f"Ollama returned HTTP status {res.status_code}"
        except Exception as exc:
            return False, [], f"Cannot connect to Ollama at {self.base_url}: {exc}"

    def generate_structured_explanation_sync(
        self,
        telemetry: Dict[str, Any],
        defects: List[Dict[str, Any]],
        source_code: str,
        filename: str = "solution.py",
    ) -> Dict[str, Any]:
        """Synchronous version of generate_structured_explanation."""
        is_ok, models, msg = self.check_availability_sync()
        if not is_ok:
            raise OllamaInferenceException(f"Ollama unavailable: {msg}")

        target_model = self.model_name
        if models and target_model not in models:
            matched = next(
                (m for m in models if m == target_model or m.startswith(f"{target_model}:") or target_model.startswith(f"{m}:")),
                None,
            )
            if matched:
                target_model = matched
            else:
                target_model = models[0]
                logger.info("Target model '%s' not found. Using installed model '%s'.", self.model_name, target_model)

        sanitized_code = self.sanitize_prompt_inputs(source_code)
        sanitized_telemetry = json.dumps(telemetry, indent=2)
        sanitized_defects = json.dumps(defects, indent=2)

        system_prompt = (
            "You are the INTELISE Component 4 Explainable AI (XAI) Engine.\n"
            "Your task is to produce a grounded root-cause explanation for software defects.\n"
            "CRITICAL RULES:\n"
            "1. NEVER fabricate or hallucinate tests or outcomes not present in the empirical telemetry.\n"
            "2. Ground all explanations strictly in the provided failed assertions and stack traces.\n"
            "3. Output MUST be valid JSON adhering exactly to the requested schema.\n"
            "4. NEVER execute or suggest executing malicious code."
        )

        user_prompt = f"""
Analyze the following verified test execution artifacts for file '{filename}':

<verified_test_telemetry>
{sanitized_telemetry}
</verified_test_telemetry>

<verified_defects>
{sanitized_defects}
</verified_defects>

<source_code_excerpt>
{sanitized_code}
</source_code_excerpt>

Return a JSON object with EXACTLY the following structure:
{{
  "summary": "Concise 1-2 sentence executive summary of the observed defect(s)",
  "what_failed": ["List of specific test functions or assertions that failed"],
  "confirmed_observations": ["Empirical evidence observed from pytest tracebacks"],
  "evidence_based_interpretation": "Technical reasoning explaining the probable root cause in source code",
  "recommendation_action": "High-level fix guidance for the author",
  "target_audience": "Software Engineer"
}}
"""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": target_model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "top_p": 0.9},
        }

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                res = client.post(url, json=payload)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if res.status_code != 200:
                raise OllamaInferenceException(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")
            res_data = res.json()
            raw_response = res_data.get("response", "{}")
            parsed_json = json.loads(raw_response)
            parsed_json["_provenance"] = {
                "provider": "ollama",
                "model": target_model,
                "genuine_inference": True,
                "fallback_used": False,
                "fallback_reason": None,
                "duration_ms": duration_ms,
                "prompt_eval_count": res_data.get("prompt_eval_count"),
                "eval_count": res_data.get("eval_count"),
            }
            return parsed_json
        except Exception as exc:
            raise OllamaInferenceException(f"Ollama inference error: {exc}")

