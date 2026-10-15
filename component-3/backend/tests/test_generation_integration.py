"""Opt-in real local-model experiment for one generated business module."""

import asyncio
import os
from pathlib import Path

import pytest

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.core.config import Settings
from intelise_c3.domain.generation import ArtifactOrigin
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_GENERATION_INTEGRATION") != "1",
    reason=(
        "Set RUN_OLLAMA_GENERATION_INTEGRATION=1 to generate with local Ollama."
    ),
)
def test_real_local_model_generates_task_service(tmp_path: Path) -> None:
    settings = Settings()
    request = build_simulated_request(GenerationMode.LOCAL_LLM)
    result = asyncio.run(
        CodeGenerationService(
            tmp_path / "generated-workspaces",
            OllamaLLMClient(settings),
        ).generate(request)
    )
    service_record = next(
        item
        for item in result.manifest.files
        if item.relative_path == "backend/src/services/taskService.js"
    )
    workspace = tmp_path / "generated-workspaces" / Path(
        result.workspace_relative_path
    )
    content = (workspace / Path(service_record.relative_path)).read_text(
        encoding="utf-8"
    )

    assert service_record.origin is ArtifactOrigin.LOCAL_LLM
    assert "createTaskService" in content
    assert result.manifest.llm_inference is not None
    assert result.manifest.execution_status == "NOT_EXECUTED"
