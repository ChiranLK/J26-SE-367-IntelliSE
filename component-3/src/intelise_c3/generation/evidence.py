"""Canonical hashing helpers for one generation run's reproducibility evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel

from intelise_c3.domain.generation import (
    CanonicalInputHashes,
    GenerationManifest,
    RagRetrievalEvidence,
)
from intelise_c3.domain.llm import LLMInferenceMetadata, LLMInferenceRequest

CANONICALIZATION_VERSION = "C3_CANONICAL_JSON_V1"


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible evidence deterministically for C3 hashing.

    C3 Canonical JSON V1 uses Pydantic JSON-mode values, UTF-8, sorted object
    keys, no insignificant whitespace, preserved array order, and non-ASCII
    characters encoded directly. It is a project convention, not RFC 8785.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def build_input_hashes(
    *,
    generation_context: BaseModel,
    design_context: BaseModel,
    stack_selection_report: BaseModel,
    approval_input: BaseModel,
    prompt_request: LLMInferenceRequest | None,
) -> CanonicalInputHashes:
    prompt_messages = (
        [message.model_dump(mode="json") for message in prompt_request.messages]
        if prompt_request is not None
        else None
    )
    return CanonicalInputHashes(
        generation_context_sha256=canonical_sha256(generation_context),
        design_context_sha256=canonical_sha256(design_context),
        stack_selection_report_sha256=canonical_sha256(stack_selection_report),
        approval_input_sha256=canonical_sha256(approval_input),
        prompt_text_sha256=(
            canonical_sha256(prompt_messages)
            if prompt_messages is not None
            else None
        ),
        prompt_request_sha256=(
            canonical_sha256(prompt_request)
            if prompt_request is not None
            else None
        ),
    )


def evidence_digest_payload(
    *,
    generation_run_id: str,
    input_hashes: CanonicalInputHashes,
    prompt_template_version: str | None,
    generator_version: str,
    template_set_version: str,
    llm_inference: LLMInferenceMetadata | None,
    artifact_digest_sha256: str,
    rag_evidence: RagRetrievalEvidence | None = None,
) -> dict[str, Any]:
    """Return the fields bound by the evidence digest, excluding the digest."""
    model_configuration = None
    if llm_inference is not None:
        model_configuration = {
            "provider": llm_inference.provider,
            "configured_model_identifier": (
                llm_inference.configured_model_identifier
            ),
            "response_model_identifier": llm_inference.response_model_identifier,
            "generation_parameters": (
                llm_inference.generation_parameters.model_dump(mode="json")
            ),
        }
    payload = {
        "evidence_schema_version": "1.0",
        "canonicalization": CANONICALIZATION_VERSION,
        "generation_run_id": generation_run_id,
        "input_hashes": input_hashes.model_dump(mode="json"),
        "prompt_template_version": prompt_template_version,
        "generator_version": generator_version,
        "template_set_version": template_set_version,
        "local_model_configuration": model_configuration,
        "artifact_digest_sha256": artifact_digest_sha256,
    }
    # Preserve verification of historical manifests that predate RAG evidence.
    if rag_evidence is not None:
        payload["rag"] = rag_evidence.model_dump(mode="json")
    return payload


def compute_evidence_digest(**payload_arguments: Any) -> str:
    return canonical_sha256(evidence_digest_payload(**payload_arguments))


def verify_manifest_evidence(manifest: GenerationManifest) -> bool:
    """Check internal hash consistency; this does not establish authenticity."""
    evidence = manifest.run_evidence
    computed = compute_evidence_digest(
        generation_run_id=manifest.generation_run_id,
        input_hashes=evidence.input_hashes,
        prompt_template_version=evidence.prompt_template_version,
        generator_version=evidence.generator_version,
        template_set_version=evidence.template_set_version,
        llm_inference=manifest.llm_inference,
        artifact_digest_sha256=manifest.artifact_digest_sha256,
        rag_evidence=evidence.rag,
    )
    return computed == evidence.evidence_digest_sha256
