"""Token-efficient, bounded OpenRouter generation for unsupported/custom modules only.

* One bounded call per affected module (never per file or per class graph).
* The prompt carries only the module's requirement slice, its UML classes, the
  selected stack, matched rule IDs, the interface contract, at most 3-5 RAG
  chunks and, on repair, the current module plus exact validator findings.
* Requests are hashed and cached; the cache key binds requirement versions,
  UML version, stack, module, KB digest, rule-set digest, prompt version,
  provider/model and the retrieved-context digest.
* At most two attempts; afterwards the attempts are preserved and the module is
  HUMAN_REVIEW_REQUIRED. Provider failures (timeout, 429, malformed output,
  unavailable model) are recorded as operational evidence; there is no fallback.
* Output is untrusted until it passes the JS safety policy and interface check.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.generation.js_safety import inspect_javascript_safety
from intelise_c3.hybrid.frontend_policy import check_bundle
from intelise_c3.llm.client import LLMClient
from intelise_c3.rag.best_practices import estimate_tokens

PROMPT_VERSION = "c3-hybrid-module-v2"
MAX_ATTEMPTS = 2
MAX_OUTPUT_CHARS = 20000
MAX_BUNDLE_CHARS = 90000
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


@dataclass(frozen=True)
class InterfaceMethod:
    name: str
    parameters: tuple[str, ...]


@dataclass(frozen=True)
class BoundedModuleContext:
    module_id: str
    target_path: str
    class_name: str
    methods: tuple[InterfaceMethod, ...]
    requirement_slices: tuple[dict[str, Any], ...]
    uml_slice: str
    uml_version: str
    stack_id: str
    rule_ids: tuple[str, ...]
    kb_digest: str
    rule_set_digest: str
    rag_prompt: str
    rag_digest: str
    current_source: str | None = None
    validator_findings: tuple[str, ...] = ()
    c4_evidence: str | None = None
    contract_notes: str = ""
    #: "class" -> `export class <class_name>`; "function" -> `export function <class_name>(...)` (class_name is the function name).
    kind: str = "class"
    #: Version of the behaviour check (benchmark cases) that gates acceptance; part of the cache key.
    check_version: str = ""
    #: kind == "bundle": the model writes exactly these files in one call; trusted_paths may be imported but not written.
    bundle_paths: tuple[str, ...] = ()
    trusted_paths: tuple[str, ...] = ()
    #: Per-call context budget override (bundle repairs carry the previous files back, which is large).
    max_input_tokens: int | None = None


@dataclass
class GatewayResult:
    module_id: str
    status: str  # ACCEPTED | HUMAN_REVIEW_REQUIRED | BUDGET_EXCEEDED | PROVIDER_ERROR
    content: str | None
    cache_key: str
    cache_hit: bool
    ledger: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    #: Raw (truncated) model outputs per attempt, preserved for human review when nothing is accepted.
    outputs: list[str] = field(default_factory=list)
    response_model: str | None = None


def build_prompt(context: BoundedModuleContext, findings: tuple[str, ...] = (), previous: str | None = None) -> LLMInferenceRequest:
    signature = "\n".join(
        f"  {method.name}({', '.join(method.parameters)})" for method in context.methods
    )
    if context.kind == "bundle":
        contract = "FILES TO WRITE (exactly these, nothing else):\n" + "\n".join(f"- {path}" for path in context.bundle_paths)
    elif context.kind == "function":
        parameters = ", ".join(context.methods[0].parameters) if context.methods else ""
        contract = f"INTERFACE CONTRACT: export function {context.class_name}({parameters})"
    else:
        contract = f"INTERFACE CONTRACT: export class {context.class_name} {{\n{signature}\n}}"
    system = (
        "You implement exactly one JavaScript ES module for a generated application. "
        "Authority order: approved requirements > released UML > Knowledge Base facts > rules > "
        "retrieved guidance > your suggestions. Never invent domain policy values, never add network, "
        "file-system, process, eval or timer access, and avoid computed member access such as obj[key] "
        "or arr[i] (use for...of, map, reduce, Object.entries, Map or Set). Respond with JSON only: "
        '{"path": "<target path>", "content": "<module source>"}.'
    )
    if context.kind == "bundle":
        system = (
            "You write a set of React 18 (JSX, no TypeScript) source files for a generated web application. "
            "Authority order: approved requirements > released UML and UI specification > Knowledge Base facts > rules > "
            "retrieved guidance > your suggestions. Never invent domain policy values. Import only 'react' and the project "
            "files you are told you may import. Never call fetch/XMLHttpRequest/WebSocket yourself (a trusted API client exists), "
            "never use eval, dangerouslySetInnerHTML, innerHTML, localStorage, cookies or navigation. Keep the code compact. "
            'Respond with JSON only: {"files": [{"path": "<path>", "content": "<file source>"}, ...]} containing exactly the requested files.'
        )
    parts = [
        f"TARGET: {'the files listed below' if context.kind == 'bundle' else context.target_path}",
        f"STACK: {context.stack_id}",
        f"RULE_IDS: {', '.join(context.rule_ids) or 'NONE (module is outside the deterministic rule base)'}",
        "REQUIREMENTS:",
        *[f"- {r['requirement_id']} v{r['requirement_version']}: {r['statement']}" for r in context.requirement_slices],
        f"UML ({context.uml_version}, only the affected classes):\n{context.uml_slice}",
        contract,
    ]
    if context.contract_notes:
        parts.append(f"CONTRACT NOTES (Knowledge Base facts and injected dependencies):\n{context.contract_notes}")
    if context.rag_prompt:
        parts.append(context.rag_prompt)
    if previous is not None or context.current_source is not None:
        label = "CURRENT_FILES" if context.kind == "bundle" else "CURRENT_MODULE"
        parts.append(f"{label}:\n{previous if previous is not None else context.current_source}")
    all_findings = tuple(context.validator_findings) + tuple(findings)
    if all_findings:
        parts.append("VALIDATOR_FINDINGS (fix exactly these):\n" + "\n".join(f"- {f}" for f in all_findings))
    if context.c4_evidence:
        parts.append(f"C4_DEFECT_EVIDENCE: {context.c4_evidence}")
    return LLMInferenceRequest(
        messages=(LLMMessage(role="system", content=system), LLMMessage(role="user", content="\n".join(parts))),
        prompt_template_version=PROMPT_VERSION,
    )


def cache_key(context: BoundedModuleContext, provider: str, model: str) -> str:
    return canonical_sha256({
        "requirements": [(r["requirement_id"], r["requirement_version"]) for r in context.requirement_slices],
        "uml_version": context.uml_version,
        "stack": context.stack_id,
        "module": context.module_id,
        "kb": context.kb_digest,
        "rules": context.rule_set_digest,
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "model": model,
        "rag": context.rag_digest,
        "repair": [context.current_source, list(context.validator_findings), context.c4_evidence],
        "notes": context.contract_notes,
        "kind": context.kind,
        "check": context.check_version,
        "bundle": list(context.bundle_paths),
    })


def validate_output(text: str, context: BoundedModuleContext) -> tuple[str | None, list[str]]:
    """Return (content, findings). Content is None unless every check passes."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, ["MALFORMED_OUTPUT: response is not the required JSON object"]
    if context.kind == "bundle":
        return _validate_bundle(payload, context)
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        return None, ["MALFORMED_OUTPUT: JSON must contain string fields path and content"]
    if payload.get("path") != context.target_path:
        return None, [f"WRONG_PATH: expected {context.target_path}"]
    content = payload["content"].replace("\r\n", "\n").strip() + "\n"
    findings: list[str] = []
    if len(content) > MAX_OUTPUT_CHARS:
        findings.append(f"OUTPUT_TOO_LARGE: more than {MAX_OUTPUT_CHARS} characters")
    report = inspect_javascript_safety(content)
    if not report.accepted:
        findings.append(f"UNSAFE_OR_UNINSPECTABLE: {report.describe()}")
    if context.kind == "function":
        if not re.search(rf"export\s+(?:async\s+)?function\s+{re.escape(context.class_name)}\s*\(", content):
            findings.append(f"INTERFACE_VIOLATION: missing 'export function {context.class_name}('")
    else:
        if not re.search(rf"export\s+class\s+{re.escape(context.class_name)}\b", content):
            findings.append(f"INTERFACE_VIOLATION: missing 'export class {context.class_name}'")
        for method in context.methods:
            if not re.search(rf"^\s+(?:async\s+)?{re.escape(method.name)}\s*\(", content, re.MULTILINE):
                findings.append(f"INTERFACE_VIOLATION: missing method {method.name}()")
    if re.search(r"^\s*import\s", content, re.MULTILINE):
        findings.append("FORBIDDEN_IMPORT: custom modules must be dependency-free")
    return (None if findings else content), findings


def _validate_bundle(payload: Any, context: BoundedModuleContext) -> tuple[str | None, list[str]]:
    entries = payload.get("files") if isinstance(payload, dict) else None
    if isinstance(entries, dict):
        entries = [{"path": key, "content": value} for key, value in entries.items()]
    if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get("path"), str) and isinstance(e.get("content"), str) for e in entries):
        return None, ['MALFORMED_OUTPUT: JSON must be {"files": [{"path": "...", "content": "..."}, ...]}']
    files: dict[str, str] = {}
    for entry in entries:
        if entry["path"] in files:
            return None, [f"MALFORMED_OUTPUT: duplicate file {entry['path']}"]
        files[entry["path"]] = entry["content"].replace("\r\n", "\n").strip("\n") + "\n"
    findings = check_bundle(files, frozenset(context.bundle_paths), frozenset(context.trusted_paths))
    if sum(len(v) for v in files.values()) > MAX_BUNDLE_CHARS:
        findings.append(f"OUTPUT_TOO_LARGE: more than {MAX_BUNDLE_CHARS} characters in total")
    return (None if findings else json.dumps(files, sort_keys=True)), findings


class OpenRouterModuleGateway:
    def __init__(
        self,
        client: LLMClient | None,
        *,
        provider: str,
        model: str,
        cache_dir: Path,
        max_input_tokens: int = 3000,
        max_attempts: int = MAX_ATTEMPTS,
        retry_delay: float = 3.0,
    ) -> None:
        self._retry_delay = retry_delay
        self._client = client
        self._provider = provider
        self._model = model
        self._cache_dir = Path(cache_dir)
        self._max_input_tokens = max_input_tokens
        self._max_attempts = min(max_attempts, MAX_ATTEMPTS)

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, key: str, record: dict[str, Any]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        pending = self._cache_path(key).with_suffix(".pending")
        pending.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(pending, self._cache_path(key))

    def _ledger(self, *, attempt: int, request: LLMInferenceRequest, **values: Any) -> dict[str, Any]:
        prompt_text = "\n".join(message.content for message in request.messages)
        return {
            "provider": self._provider,
            "requested_model": self._model,
            "response_model": None,
            "upstream_provider": None,
            "prompt_version": PROMPT_VERSION,
            "request_sha256": canonical_sha256(request),
            "estimated_input_tokens": estimate_tokens(prompt_text),
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "cost_note": "Provider cost is not returned by the C3 client; token counts are the cost proxy.",
            "latency_ms": None,
            "attempt": attempt,
            "cache_hit": False,
            "validation_result": None,
            "accepted": False,
            "error_code": None,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **values,
        }

    async def generate(
        self,
        context: BoundedModuleContext,
        *,
        use_cache: bool = True,
        behaviour_check: Callable[[str], Awaitable[list[str]]] | None = None,
        max_attempts: int | None = None,
        write_cache: bool = True,
    ) -> GatewayResult:
        """One bounded call per module, at most two attempts.

        ``behaviour_check`` (optional) runs the candidate in a sandbox after static validation and returns exact
        failure findings; they feed the second attempt, and nothing is cached or accepted unless it returns [].
        """
        key = cache_key(context, self._provider, self._model)
        cached = self._read_cache(key) if use_cache else None
        if cached is not None:
            request = build_prompt(context)
            entry = self._ledger(attempt=0, request=request, cache_hit=True, accepted=True,
                                 validation_result="ACCEPTED_FROM_CACHE", response_model=cached.get("response_model"))
            return GatewayResult(context.module_id, "ACCEPTED", cached["content"], key, True, [entry])
        result = GatewayResult(context.module_id, "HUMAN_REVIEW_REQUIRED", None, key, False)
        if self._client is None:
            result.status = "PROVIDER_ERROR"
            result.reasons.append(
                f"{self._provider.upper()}_UNAVAILABLE: the {self._provider} provider is not selected, its experiment gate is off or no key is configured."
            )
            return result
        findings: tuple[str, ...] = ()
        previous: str | None = None
        attempts = min(max_attempts, self._max_attempts) if max_attempts is not None else self._max_attempts
        for attempt in range(1, attempts + 1):
            request = build_prompt(context, findings, previous)
            estimated = estimate_tokens("\n".join(m.content for m in request.messages))
            budget = context.max_input_tokens or self._max_input_tokens
            if estimated > budget:
                result.status = "BUDGET_EXCEEDED"
                result.reasons.append(f"INPUT_TOKEN_BUDGET_EXCEEDED: ~{estimated} > {budget}; no call was made.")
                result.ledger.append(self._ledger(attempt=attempt, request=request, validation_result="NOT_CALLED_BUDGET"))
                return result
            try:
                response = await self._client.generate(request)
            except ApplicationError as error:
                code = error.errors[0].code
                result.ledger.append(self._ledger(attempt=attempt, request=request, error_code=code,
                                                  error_message=error.errors[0].message[:400],
                                                  validation_result="PROVIDER_ERROR"))
                retryable = code in {"OPENROUTER_EMPTY_CONTENT", "OPENROUTER_OUTPUT_TRUNCATED", "OPENROUTER_INVALID_RESPONSE",
                                     "TEAMSOCLO_INVALID_RESPONSE"}
                if not retryable:
                    result.status = "PROVIDER_ERROR"
                    result.reasons.append(f"{code}: {error.errors[0].message}")
                    return result
                findings = (f"PREVIOUS_ATTEMPT_PROVIDER_ERROR: {code}",)
                await asyncio.sleep(self._retry_delay)  # a transient gateway fault often clears within seconds
                continue
            meta = response.metadata
            usage = meta.response
            result.outputs.append(response.output_text[:MAX_BUNDLE_CHARS if context.kind == "bundle" else MAX_OUTPUT_CHARS])
            content, problems = validate_output(response.output_text, context)
            if content is not None and behaviour_check is not None:
                behaviour_problems = await behaviour_check(content)
                if behaviour_problems:
                    content, problems = None, behaviour_problems
            entry = self._ledger(
                attempt=attempt, request=request,
                response_model=meta.response_model_identifier,
                upstream_provider=getattr(usage, "upstream_provider", None),
                # OpenRouter reports prompt/completion tokens, TeamSocLo input/output tokens.
                prompt_tokens=getattr(usage, "prompt_tokens", None) if getattr(usage, "prompt_tokens", None) is not None else getattr(usage, "input_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None) if getattr(usage, "completion_tokens", None) is not None else getattr(usage, "output_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
                latency_ms=meta.client_inference_latency_ms,
                validation_result="ACCEPTED" if content else "; ".join(problems),
                accepted=content is not None,
            )
            result.ledger.append(entry)
            if content is not None:
                result.status, result.content = "ACCEPTED", content
                result.response_model = meta.response_model_identifier
                if write_cache:
                    self.remember(context, content, meta.response_model_identifier)
                return result
            findings = tuple(problems)
            previous = response.output_text[:MAX_BUNDLE_CHARS if context.kind == "bundle" else MAX_OUTPUT_CHARS]
        result.reasons.append(f"RETRY_LIMIT_REACHED: {attempts} attempts rejected; attempts preserved for human review.")
        return result

    def remember(self, context: BoundedModuleContext, content: str, response_model: str | None) -> None:
        """Cache an accepted result (callers that gate acceptance elsewhere call this only after the gate passes)."""
        self._write_cache(cache_key(context, self._provider, self._model),
                          {"content": content, "response_model": response_model, "module_id": context.module_id,
                           "prompt_version": PROMPT_VERSION})
