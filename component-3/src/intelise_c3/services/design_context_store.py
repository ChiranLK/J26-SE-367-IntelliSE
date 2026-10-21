"""Content-addressed persistence of the DesignContext bound to a generation run.

A manifest records only ``design_context_sha256``. Scoped regeneration and the C4
intake endpoint need the full ``DesignContext`` again, so generation saves it here
under that digest. Loading recomputes the digest, so a tampered or substituted
file is rejected instead of trusted.
"""

import json
import os
from pathlib import Path
import re

from fastapi import status
from pydantic import ValidationError

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.generation.evidence import canonical_sha256

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DesignContextStore:
    """Write-once store keyed by the canonical SHA-256 of the DesignContext."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @classmethod
    def from_settings(cls, settings) -> "DesignContextStore":
        return cls(settings.traceability_store_path.parent / "design-contexts")

    def save(self, design_context: DesignContext) -> str:
        digest = canonical_sha256(design_context)
        target = self._directory / f"{digest}.json"
        if target.exists():
            return digest
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            pending = target.with_suffix(f".json.{os.getpid()}.pending")
            pending.write_text(
                json.dumps(design_context.model_dump(mode="json"), separators=(",", ":")),
                encoding="utf-8",
            )
            pending.replace(target)
        except OSError as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="DESIGN_CONTEXT_STORE_ERROR",
                        field="design_context",
                        message="The design context could not be persisted.",
                    )
                ],
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exception
        return digest

    def load(self, expected_sha256: str) -> DesignContext:
        """Return the stored context only if it still hashes to ``expected_sha256``."""
        if not _SHA256.fullmatch(expected_sha256):
            self._fail("DESIGN_CONTEXT_DIGEST_MISMATCH", "Invalid design context digest.")
        path = self._directory / f"{expected_sha256}.json"
        try:
            context = DesignContext.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._fail(
                "DESIGN_CONTEXT_NOT_PERSISTED",
                "No design context was persisted for this generation run; regenerate "
                "the application so its design context is stored.",
            )
        except (OSError, ValidationError, ValueError):
            self._fail(
                "DESIGN_CONTEXT_DIGEST_MISMATCH",
                "The persisted design context is unreadable or invalid.",
            )
        if canonical_sha256(context) != expected_sha256:
            self._fail(
                "DESIGN_CONTEXT_DIGEST_MISMATCH",
                "The persisted design context does not match the run's recorded digest.",
            )
        return context

    @staticmethod
    def _fail(code: str, message: str) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field="design_context", message=message)],
            status_code=status.HTTP_409_CONFLICT,
        )
