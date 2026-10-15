"""Verify and copy one generated workspace for an isolated Docker preview.

This script never executes generated JavaScript. It verifies the manifest,
evidence digest, artifact digest, and file hashes before copying bytes into a
new execution directory. Existing execution evidence is never overwritten.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from intelise_c3.core.config import get_settings
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.traceability.verification import ManifestVerificationService

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
EXECUTIONS_ROOT = Path(__file__).resolve().parent / "executions"
SAFE_EXECUTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify and copy a generated workspace for isolated preview."
    )
    parser.add_argument(
        "workspace_relative_path",
        help=(
            "Workspace path relative to GENERATED_WORKSPACE_ROOT "
            "(for example template-baseline/<run-id>)."
        ),
    )
    parser.add_argument(
        "--execution-id",
        help=(
            "New folder name under runtime-preview/executions/. Defaults to the "
            "generation run ID. Existing folders are never replaced."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    workspace_relative = args.workspace_relative_path.replace("\\", "/")
    source = settings.generated_workspace_root.joinpath(*workspace_relative.split("/"))
    manifest_path = source / "artifact-manifest.json"
    if not manifest_path.is_file():
        return _fail(f"manifest missing at {manifest_path}")

    try:
        manifest = GenerationManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as error:
        return _fail(f"invalid manifest: {error}")

    verifier = ManifestVerificationService(settings.generated_workspace_root)
    verifier.verify(manifest, workspace_relative)

    execution_id = args.execution_id or manifest.generation_run_id
    if not SAFE_EXECUTION_ID.fullmatch(execution_id):
        return _fail(
            "execution ID must contain only letters, digits, dot, underscore, or hyphen"
        )

    execution_root = EXECUTIONS_ROOT / execution_id
    if execution_root.exists():
        return _fail(
            f"execution evidence already exists at {execution_root}; choose a new --execution-id"
        )

    EXECUTIONS_ROOT.mkdir(parents=True, exist_ok=True)
    staging_root = EXECUTIONS_ROOT / f".{execution_id}.pending-{uuid4().hex}"
    target = staging_root / "workspace"
    try:
        target.mkdir(parents=True, exist_ok=False)
        allowed = {item.relative_path for item in manifest.files} | {
            "artifact-manifest.json"
        }
        for relative in sorted(allowed):
            src = source / Path(*relative.split("/"))
            dst = target / Path(*relative.split("/"))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        meta = {
            "generation_run_id": manifest.generation_run_id,
            "generation_mode": manifest.generation_mode,
            "artifact_digest_sha256": manifest.artifact_digest_sha256,
            "evidence_digest_sha256": manifest.run_evidence.evidence_digest_sha256,
            "workspace_relative_path": workspace_relative,
            "execution_directory": str(
                (execution_root / "workspace").relative_to(COMPONENT_ROOT)
            ).replace("\\", "/"),
            "file_count": len(manifest.files),
            "local_llm_files": [
                {"relative_path": item.relative_path, "sha256": item.sha256}
                for item in manifest.files
                if item.origin == "LOCAL_LLM"
            ],
            "verification": "MANIFEST_EVIDENCE_ARTIFACT_AND_FILE_HASHES_VERIFIED",
        }
        (staging_root / "meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        staging_root.replace(execution_root)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise

    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
