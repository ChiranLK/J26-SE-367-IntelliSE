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
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.OLLAMA_TIMEOUT_SECONDS
        )
        self.post_delivery_timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.OLLAMA_READ_TIMEOUT_SECONDS
        )
        self.connect_timeout_seconds = settings.OLLAMA_CONNECT_TIMEOUT_SECONDS
        self.max_output_tokens = settings.OLLAMA_MAX_OUTPUT_TOKENS
        self.keep_alive = settings.OLLAMA_KEEP_ALIVE
        self.enabled = enabled if enabled is not None else settings.OLLAMA_ENABLED
        self._http_client = http_client

    def _inference_timeout(self) -> httpx.Timeout:
        """Use a short connection deadline without cutting off bounded local generation."""
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.post_delivery_timeout_seconds,
            write=10.0,
            pool=self.connect_timeout_seconds,
        )

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

    def generate_post_delivery_understanding_sync(
        self,
        source_code: str,
        filename: str,
        structural_facts: Dict[str, Any],
        verified_tests: List[str],
        evidence_bundle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate software-understanding prose only after the caller enforces delivery gates."""
        is_ok, models, msg = self.check_availability_sync()
        if not is_ok:
            raise OllamaInferenceException(f"Ollama unavailable: {msg}")

        target_model = self.model_name
        if models and target_model not in models:
            target_model = next(
                (m for m in models if m.startswith(f"{target_model}:") or target_model.startswith(f"{m}:")),
                models[0],
            )

        system_prompt = (
            "You are the INTELISE post-delivery software-understanding assistant. "
            "Explain what verified, delivered software does; do not discuss defects or repair. "
            "Use only supplied source, AST facts, and passed-test names. Return valid JSON only."
        )
        bounded_evidence = evidence_bundle or {
            "primary_file": filename,
            "ast_facts": structural_facts,
            "passed_tests": verified_tests,
            "source_excerpt": self.sanitize_prompt_inputs(source_code),
        }
        serialized_evidence = json.dumps(bounded_evidence, indent=2, default=str)[:24_000]
        user_prompt = f"""
<verified_delivered_evidence>
{serialized_evidence}
</verified_delivered_evidence>

Return exactly this JSON shape:
{{
  "software_overview": "Comprehensive multi-paragraph explanation (100-150 words) detailing the real-world domain, core responsibilities, supported capabilities, inputs/outputs, and limitations.",
  "architecture_explanation": "Detailed architectural explanation (80-120 words) detailing module responsibilities, decomposition, and how modules collaborate.",
  "api_and_data_flow": "Detailed explanation (80-120 words) tracing data flow from input to validation to calculation to output across functions. State clearly that interfaces are Python callables (no HTTP API).",
  "setup_and_usage": "Clear setup and practical invocation instructions (50-80 words) using real modules and functions.",
  "limitations_and_scope": "Detailed explanation (60-100 words) detailing verified capabilities vs untested assumptions and operational boundaries.",
  "beginner_overview": "Accessible, non-technical explanation (60-100 words) for a general audience.",
  "beginner_what_it_does": "Clear plain-English description (50-80 words) of everyday functionality without technical jargon.",
  "beginner_how_to_use": "Step-by-step practical guide (40-70 words) on how someone uses this software.",
  "beginner_realistic_example": "A concrete scenario (40-60 words) with sample numbers and calculated outcome.",
  "beginner_test_confidence": "Clear statement (30-50 words) on what passing tests prove and do not prove."
}}

Grounding rules:
- Cite relevant evidence inline as [source: path.py], [function: name], or [test: identifier].
- Never invent APIs, databases, frameworks, functions, signatures, dependencies, measurements, or intentions.
- If a requested fact is unavailable, write: "Not established by the available evidence."
- Passing tests establish only the behavior exercised by those tests, not complete correctness.
"""
        payload = {
            "model": target_model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": self.max_output_tokens,
            },
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self._inference_timeout()) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
            if response.status_code != 200:
                raise OllamaInferenceException(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
            body = response.json()
            raw_text = body.get("response", "{}")
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                if body.get("done_reason") == "length":
                    raise OllamaInferenceException(
                        f"Ollama post-delivery response reached the {self.max_output_tokens}-token output bound and produced truncated JSON"
                    ) from exc
                raise OllamaInferenceException(f"Ollama post-delivery JSON decode error: {exc}") from exc

            required = {
                "software_overview", "architecture_explanation", "api_and_data_flow",
                "setup_and_usage", "limitations_and_scope",
            }
            if not required.issubset(parsed) or not all(isinstance(parsed.get(key), str) and parsed[key].strip() for key in required):
                raise OllamaInferenceException("Ollama post-delivery response did not satisfy the required schema")
            parsed["_provenance"] = {
                "provider": "ollama",
                "model": target_model,
                "genuine_inference": True,
                "fallback_used": False,
                "fallback_reason": None,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompt_eval_count": body.get("prompt_eval_count"),
                "eval_count": body.get("eval_count"),
            }
            logger.info(
                "Post-delivery Ollama inference completed model=%s duration_ms=%.2f "
                "prompt_chars=%d prompt_tokens=%s output_tokens=%s",
                target_model,
                parsed["_provenance"]["duration_ms"],
                len(system_prompt) + len(user_prompt),
                body.get("prompt_eval_count"),
                body.get("eval_count"),
            )
            return parsed
        except OllamaInferenceException:
            raise
        except httpx.ConnectTimeout as exc:
            raise OllamaInferenceException(
                f"Ollama post-delivery connection timed out after {self.connect_timeout_seconds}s: {exc}"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise OllamaInferenceException(
                "Ollama post-delivery generation timed out after "
                f"{self.post_delivery_timeout_seconds}s: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaInferenceException(f"Ollama post-delivery HTTP timeout: {exc}") from exc
        except Exception as exc:
            raise OllamaInferenceException(f"Ollama post-delivery inference error: {exc}") from exc
