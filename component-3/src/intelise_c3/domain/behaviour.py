"""Evidence records for behaviour-driven (non-CRUD) generation runs, Stage 0."""

from __future__ import annotations

from typing import Literal

from intelise_c3.domain.generation import ArtifactOrigin, RagRetrievalEvidence
from intelise_c3.domain.generation_context import DomainModel


class BehaviourFinding(DomainModel):
    code: str
    message: str


class BehaviourAttempt(DomainModel):
    """One model call for one class unit, with the validator's verdict."""

    unit: str
    attempt: int
    temperature: float
    configured_model_identifier: str
    response_model_identifier: str
    prompt_template_version: str
    prompt_text_sha256: str
    prompt_request_sha256: str
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    client_inference_latency_ms: float
    verdict: Literal["ACCEPTED", "REJECTED"]
    syntax_check: str
    findings: tuple[BehaviourFinding, ...] = ()


class BehaviourProbeEvidence(DomainModel):
    status: str
    plan: tuple[dict, ...]
    steps: tuple[dict, ...]
    findings: tuple[BehaviourFinding, ...] = ()
    warnings: tuple[BehaviourFinding, ...] = ()
    note: str = (
        "Sandboxed smoke probe with fixed sample inputs and no expected answers: it shows no crash, "
        "no undefined/NaN state, a visible effect, and (metamorphic check) that inputs given before the "
        "first computation influence it. It is not a correctness test."
    )


class BehaviourFileRecord(DomainModel):
    relative_path: str
    origin: ArtifactOrigin
    sha256: str
    size_bytes: int
    generated_by_unit: tuple[str, ...] = ()


class BehaviourManifest(DomainModel):
    manifest_schema_version: Literal["c3-behaviour-manifest-0"] = "c3-behaviour-manifest-0"
    generation_run_id: str
    generated_at_utc: str
    generation_mode: Literal["LOCAL_LLM", "EXPERIMENTAL_CLAUDE", "EXPERIMENTAL_OPENROUTER"] = "LOCAL_LLM"
    application_profile: Literal["CUSTOM_NON_CRUD_BEHAVIOUR"] = "CUSTOM_NON_CRUD_BEHAVIOUR"
    generator_version: str
    template_set_version: str
    spec_policy_version: str
    validator_version: str
    prompt_template_version: str
    project_id: str
    srs_version: str
    uml_version: str
    requirement_ids: tuple[str, ...]
    uml_ids: tuple[str, ...]
    design_anchor_ids: tuple[str, ...]
    facade_class: str
    facade_rule: str
    selected_stack_id: str
    implemented_stack: str
    stack_approval_reference: str
    llm_provider: Literal["ollama-local", "teamsoclo-claude", "openrouter"] = "ollama-local"
    attempts: tuple[BehaviourAttempt, ...]
    probe: BehaviourProbeEvidence
    files: tuple[BehaviourFileRecord, ...]
    artifact_digest_sha256: str
    spec_diagnostics: tuple[str, ...] = ()
    trust_boundary: str = (
        "Stage 0 behaviour generator: structure and UI are deterministic from the accepted C2 class "
        "diagram; method bodies are written by the recorded model (llm_provider) and only statically "
        "validated and "
        "smoke-probed. Not linked into the living traceability graph yet; no independent (C4) testing."
    )
    rag_evidence: RagRetrievalEvidence | None = None


class BehaviourGenerationResult(DomainModel):
    workspace_relative_path: str
    manifest_relative_path: str
    manifest: BehaviourManifest


class BehaviourAppSession(DomainModel):
    workspace_relative_path: str
    generation_run_id: str
    status: Literal["RUNNING", "STOPPED", "FAILED"]
    url: str | None = None
    port: int | None = None
    pid: int | None = None
    sandbox: str = "node --permission (read-only inside the workspace; no writes, child processes or workers)"
    detail: str | None = None
