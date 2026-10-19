"""Verification boundary for accepting a Task 6 generation manifest."""

from hashlib import sha256
from pathlib import Path, PurePosixPath

from fastapi import status
from pydantic import ValidationError

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.generation.evidence import verify_manifest_evidence
from intelise_c3.generation.evidence import canonical_sha256


class ManifestVerificationService:
    """Verify manifest integrity and its files without executing any artifact."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()

    def verify(
        self,
        manifest: GenerationManifest,
        workspace_relative_path: str,
    ) -> Path:
        if not verify_manifest_evidence(manifest):
            self._fail(
                "INVALID_EVIDENCE_DIGEST",
                "manifest.run_evidence.evidence_digest_sha256",
                "The manifest evidence digest does not match its bound evidence.",
            )

        # A full generation creates every record in its own run. A scoped
        # regeneration deliberately carries forward unchanged file/link
        # records with their original creation-run provenance; only patched
        # records receive the new run ID. Historical manifests omit this
        # additive field and therefore remain valid.
        permits_historical_creation_runs = (
            manifest.generation_mode == "SCOPED_REGENERATION"
        )
        mismatched_file_ids = tuple(
            record.file_id
            for record in manifest.files
            if record.created_in_generation_run_id is not None
            and record.created_in_generation_run_id != manifest.generation_run_id
            and not permits_historical_creation_runs
        )
        if mismatched_file_ids:
            self._fail(
                "INVALID_FILE_CREATION_RUN_EVIDENCE",
                "manifest.files.created_in_generation_run_id",
                "File creation-run evidence must match the full-generation run.",
            )
        mismatched_link_ids = tuple(
            link.link_id
            for link in manifest.traceability.links
            if link.created_in_generation_run_id is not None
            and link.created_in_generation_run_id != manifest.generation_run_id
            and not permits_historical_creation_runs
        )
        if mismatched_link_ids:
            self._fail(
                "INVALID_LINK_CREATION_RUN_EVIDENCE",
                "manifest.traceability.links.created_in_generation_run_id",
                "Link creation-run evidence must match the full-generation run.",
            )

        workspace = self._resolve_workspace(workspace_relative_path)
        if not workspace.is_dir():
            self._fail(
                "GENERATION_WORKSPACE_NOT_FOUND",
                "workspace_relative_path",
                "The generation workspace does not exist.",
            )
        manifest_path = workspace / "artifact-manifest.json"
        try:
            stored_manifest = GenerationManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="INVALID_STORED_MANIFEST",
                        field="workspace_relative_path",
                        message="The workspace manifest is missing or invalid.",
                    )
                ],
                status_code=status.HTTP_409_CONFLICT,
            ) from exception
        if canonical_sha256(stored_manifest) != canonical_sha256(manifest):
            self._fail(
                "MANIFEST_PAYLOAD_MISMATCH",
                "manifest",
                "The supplied manifest does not match the workspace manifest.",
            )

        seen_paths: set[str] = set()
        seen_file_ids: set[str] = set()
        aggregate = sha256()
        for record in sorted(manifest.files, key=lambda item: item.relative_path):
            self._validate_artifact_identity(record.relative_path)
            if record.relative_path.casefold() in seen_paths or record.file_id in seen_file_ids:
                self._fail(
                    "DUPLICATE_ARTIFACT_IDENTITY",
                    "manifest.files",
                    "Manifest file paths and file IDs must be unique.",
                )
            seen_paths.add(record.relative_path.casefold())
            seen_file_ids.add(record.file_id)
            candidate = workspace.joinpath(*PurePosixPath(record.relative_path).parts)
            resolved_candidate = candidate.resolve()
            has_symlink_parent = any(
                parent.is_symlink()
                for parent in candidate.parents
                if parent != workspace and parent.is_relative_to(workspace)
            )
            if (
                not resolved_candidate.is_relative_to(workspace)
                or candidate.is_symlink()
                or has_symlink_parent
            ):
                self._fail(
                    "UNSAFE_ARTIFACT_PATH",
                    "manifest.files.relative_path",
                    "A manifest artifact escapes the verified workspace or is a symlink.",
                )
            if not candidate.is_file():
                self._fail(
                    "MISSING_GENERATED_ARTIFACT",
                    record.relative_path,
                    "A manifest file is missing from the generation workspace.",
                )
            content = candidate.read_bytes()
            if len(content) != record.size_bytes or sha256(content).hexdigest() != record.sha256:
                self._fail(
                    "ARTIFACT_HASH_MISMATCH",
                    record.relative_path,
                    "A generated artifact does not match its recorded size or SHA-256.",
                )
            aggregate.update(record.relative_path.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(record.sha256.encode("ascii"))
            aggregate.update(b"\n")

        if aggregate.hexdigest() != manifest.artifact_digest_sha256:
            self._fail(
                "ARTIFACT_DIGEST_MISMATCH",
                "manifest.artifact_digest_sha256",
                "The aggregate artifact digest does not match the verified files.",
            )
        return workspace

    def _resolve_workspace(self, relative_path: str) -> Path:
        path = PurePosixPath(relative_path)
        if (
            not relative_path
            or "\\" in relative_path
            or path.is_absolute()
            or ".." in path.parts
            or ":" in path.parts[0]
            or path.as_posix() != relative_path
        ):
            self._fail(
                "UNSAFE_WORKSPACE_PATH",
                "workspace_relative_path",
                "Workspace path must be a safe relative POSIX path.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        workspace = self._workspace_root.joinpath(*path.parts).resolve()
        if not workspace.is_relative_to(self._workspace_root):
            self._fail(
                "UNSAFE_WORKSPACE_PATH",
                "workspace_relative_path",
                "Workspace path escapes the configured generated-workspace root.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        return workspace

    @staticmethod
    def _validate_artifact_identity(relative_path: str) -> None:
        path = PurePosixPath(relative_path)
        if (
            not relative_path
            or "\\" in relative_path
            or path.is_absolute()
            or ".." in path.parts
            or ":" in path.parts[0]
            or path.as_posix() != relative_path
        ):
            ManifestVerificationService._fail(
                "UNSAFE_ARTIFACT_PATH",
                "manifest.files.relative_path",
                "Manifest contains an unsafe artifact path.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    @staticmethod
    def _fail(
        code: str,
        field: str,
        message: str,
        status_code: int = status.HTTP_409_CONFLICT,
    ) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status_code,
        )
