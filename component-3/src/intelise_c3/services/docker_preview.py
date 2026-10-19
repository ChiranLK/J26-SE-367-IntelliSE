"""Isolated Docker browser preview for verified dynamic CRUD workspaces.

Generated JavaScript is never executed on the host. The host only orchestrates
``docker build`` / ``docker run`` with published loopback ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import json
import shutil
import socket
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from fastapi import status

from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.generation.crud_templates import is_dynamic_crud_manifest
from intelise_c3.traceability.verification import ManifestVerificationService

HARNESS_ROOT = COMPONENT_ROOT / "docker-validation"
PREVIEW_ROOT = COMPONENT_ROOT / "runtime" / "preview"
DEFAULT_NODE_IMAGE = (
    "node:24-bookworm-slim@sha256:"
    "a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5"
)
BUILD_TIMEOUT_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 120
PREVIEW_MEMORY = "512m"
PREVIEW_CPUS = "0.50"


class PreviewStatus(StrEnum):
    IDLE = "IDLE"
    BUILDING = "BUILDING"
    BUILT = "BUILT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass
class PreviewSession:
    preview_id: str
    generation_run_id: str
    workspace_relative_path: str
    artifact_digest_sha256: str
    status: PreviewStatus = PreviewStatus.IDLE
    image_tag: str | None = None
    container_name: str | None = None
    ui_port: int | None = None
    api_port: int | None = None
    ui_url: str | None = None
    api_url: str | None = None
    context_root: Path | None = None
    last_error: str | None = None
    updated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    isolation_claim: str = (
        "GENERATED_JS_EXECUTES_ONLY_INSIDE_DISPOSABLE_DOCKER_CONTAINER_NOT_ON_HOST"
    )

    def touch(self) -> None:
        self.updated_at_utc = datetime.now(UTC).isoformat()


class DockerPreviewService:
    """Manage one preview session per verified dynamic CRUD generation run."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._verifier = ManifestVerificationService(settings.generated_workspace_root)
        self._sessions: dict[str, PreviewSession] = {}

    def status(self, preview_id: str) -> PreviewSession:
        session = self._sessions.get(preview_id)
        if session is None:
            self._fail(
                "PREVIEW_NOT_FOUND",
                "preview_id",
                "No preview session exists for that identifier.",
                status.HTTP_404_NOT_FOUND,
            )
        if session.status is PreviewStatus.RUNNING and session.container_name:
            if not self._container_running(session.container_name):
                session.status = PreviewStatus.STOPPED
                session.touch()
        return session

    def build(self, manifest: GenerationManifest, workspace_relative_path: str) -> PreviewSession:
        self._require_docker()
        self._validate_preview_target(manifest, workspace_relative_path)
        preview_id = manifest.generation_run_id
        existing = self._sessions.get(preview_id)
        if existing and existing.status is PreviewStatus.RUNNING:
            self.stop(preview_id)

        session = PreviewSession(
            preview_id=preview_id,
            generation_run_id=manifest.generation_run_id,
            workspace_relative_path=workspace_relative_path,
            artifact_digest_sha256=manifest.artifact_digest_sha256,
            status=PreviewStatus.BUILDING,
        )
        self._sessions[preview_id] = session
        try:
            ui_port, api_port = self._allocate_port_pair()
            session.ui_port = ui_port
            session.api_port = api_port
            session.ui_url = f"http://127.0.0.1:{ui_port}/"
            session.api_url = f"http://127.0.0.1:{api_port}/"
            context_root, app_path = self._prepare_context(
                manifest,
                workspace_relative_path,
                ui_port=ui_port,
                api_port=api_port,
            )
            session.context_root = context_root
            tag = f"intelise-c3-preview:{manifest.artifact_digest_sha256[:12]}"
            session.image_tag = tag
            cors_origin = f"http://127.0.0.1:{ui_port}"
            build_command = (
                "docker",
                "build",
                "--pull",
                "--progress",
                "plain",
                "--target",
                "preview",
                "--memory",
                "1g",
                "--shm-size",
                "128m",
                "--ulimit",
                "nofile=1024:1024",
                "--build-arg",
                f"APP_PATH={app_path}",
                "--build-arg",
                f"NODE_IMAGE={DEFAULT_NODE_IMAGE}",
                "--build-arg",
                f"VITE_API_BASE_URL=http://127.0.0.1:{api_port}",
                "--build-arg",
                f"CORS_ALLOWED_ORIGIN={cors_origin}",
                "--tag",
                tag,
                "--file",
                str(context_root / "harness" / "Dockerfile"),
                str(context_root),
            )
            result = self._run(build_command, timeout=BUILD_TIMEOUT_SECONDS)
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout or "docker build failed")
            session.status = PreviewStatus.BUILT
            session.last_error = None
        except Exception as exception:  # noqa: BLE001 — surface as preview failure
            session.status = PreviewStatus.FAILED
            session.last_error = str(exception)
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="PREVIEW_BUILD_FAILED",
                        field="preview",
                        message=str(exception),
                    )
                ],
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exception
        finally:
            session.touch()
        return session

    def start(self, preview_id: str) -> PreviewSession:
        self._require_docker()
        session = self.status(preview_id)
        if session.status not in {PreviewStatus.BUILT, PreviewStatus.STOPPED}:
            self._fail(
                "PREVIEW_INVALID_STATE",
                "preview_id",
                f"Preview must be BUILT or STOPPED before start (current: {session.status}).",
                status.HTTP_409_CONFLICT,
            )
        if not session.image_tag or session.ui_port is None or session.api_port is None:
            self._fail(
                "PREVIEW_NOT_BUILT",
                "preview_id",
                "Build the preview image before starting it.",
                status.HTTP_409_CONFLICT,
            )
        session.status = PreviewStatus.STARTING
        session.touch()
        container = f"intelise-c3-preview-{session.preview_id[:12]}"
        session.container_name = container
        self._remove_container(container)
        run_command = (
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{session.ui_port}:8080",
            "--publish",
            f"127.0.0.1:{session.api_port}:3001",
            "--memory",
            PREVIEW_MEMORY,
            "--cpus",
            PREVIEW_CPUS,
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "1000:1000",
            "--restart",
            "no",
            session.image_tag,
        )
        result = self._run(run_command, timeout=COMMAND_TIMEOUT_SECONDS)
        if result.returncode != 0:
            session.status = PreviewStatus.FAILED
            session.last_error = result.stderr or result.stdout or "docker run failed"
            session.touch()
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="PREVIEW_START_FAILED",
                        field="preview",
                        message=session.last_error,
                    )
                ],
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        session.status = PreviewStatus.RUNNING
        session.last_error = None
        session.touch()
        return session

    def stop(self, preview_id: str) -> PreviewSession:
        session = self.status(preview_id)
        if session.container_name:
            self._remove_container(session.container_name)
        session.status = PreviewStatus.STOPPED
        session.touch()
        return session

    def to_payload(self, session: PreviewSession) -> dict[str, Any]:
        return {
            "preview_id": session.preview_id,
            "generation_run_id": session.generation_run_id,
            "workspace_relative_path": session.workspace_relative_path,
            "artifact_digest_sha256": session.artifact_digest_sha256,
            "status": session.status.value,
            "image_tag": session.image_tag,
            "container_name": session.container_name,
            "ui_port": session.ui_port,
            "api_port": session.api_port,
            "ui_url": session.ui_url,
            "api_url": session.api_url,
            "last_error": session.last_error,
            "updated_at_utc": session.updated_at_utc,
            "execution_claim": session.isolation_claim,
            "runtime_db_claim": "IN_MEMORY",
            "browser_verification_claim": False,
        }

    def _validate_preview_target(
        self,
        manifest: GenerationManifest,
        workspace_relative_path: str,
    ) -> None:
        if not is_dynamic_crud_manifest(manifest):
            self._fail(
                "PREVIEW_REQUIRES_DYNAMIC_CRUD",
                "manifest",
                "Browser preview is supported only for verified dynamic CRUD manifests.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        self._verifier.verify(manifest, workspace_relative_path)

    def _prepare_context(
        self,
        manifest: GenerationManifest,
        workspace_relative_path: str,
        *,
        ui_port: int,
        api_port: int,
    ) -> tuple[Path, str]:
        PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
        context_root = PREVIEW_ROOT / manifest.generation_run_id
        if context_root.exists():
            shutil.rmtree(context_root)
        context_root.mkdir(parents=True)
        shutil.copytree(HARNESS_ROOT, context_root / "harness")
        shutil.copy2(HARNESS_ROOT / "context.dockerignore", context_root / ".dockerignore")
        source = self._settings.generated_workspace_root / PurePosixPath(
            workspace_relative_path
        )
        app_path = PurePosixPath("app", manifest.generation_run_id)
        destination = context_root / app_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        metadata = {
            "generation_run_id": manifest.generation_run_id,
            "artifact_digest_sha256": manifest.artifact_digest_sha256,
            "source_workspace_relative_path": workspace_relative_path,
            "docker_app_path": app_path.as_posix(),
            "ui_port": ui_port,
            "api_port": api_port,
            "prepared_at_utc": datetime.now(UTC).isoformat(),
        }
        (context_root / "preview-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )
        return context_root, app_path.as_posix()

    @staticmethod
    def _allocate_port_pair() -> tuple[int, int]:
        first = DockerPreviewService._pick_loopback_port()
        second = DockerPreviewService._pick_loopback_port()
        while second == first:
            second = DockerPreviewService._pick_loopback_port()
        return first, second

    @staticmethod
    def _pick_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _require_docker() -> None:
        if shutil.which("docker") is None:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="DOCKER_UNAVAILABLE",
                        field="docker",
                        message="Docker CLI is not available on PATH.",
                    )
                ],
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @staticmethod
    def _run(command: tuple[str, ...], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    @staticmethod
    def _container_running(name: str) -> bool:
        result = subprocess.run(
            ("docker", "inspect", "-f", "{{.State.Running}}", name),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    @staticmethod
    def _remove_container(name: str) -> None:
        subprocess.run(
            ("docker", "rm", "-f", name),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    @staticmethod
    def _fail(code: str, field: str, message: str, status_code: int) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status_code,
        )
