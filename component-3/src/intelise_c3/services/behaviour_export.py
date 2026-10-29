"""Zip export of a generated behaviour workspace.

The caller goes through ``BehaviourAppRunner.workspace`` first, so every file is re-hashed against
``behaviour-manifest.json`` and a tampered workspace is never exported. The zip keeps the exact
bytes (and relative layout) the manifest digest covers, so it still runs with ``node server.mjs``
and a tester can verify it.
"""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import zipfile

from intelise_c3.domain.behaviour import BehaviourManifest

MANIFEST_FILE = "behaviour-manifest.json"


def build_archive(run_dir: Path, manifest: BehaviourManifest, folder_name: str) -> bytes:
    """Zip the verified project files plus the manifest under one top-level folder."""
    buffer = io.BytesIO()
    names = [record.relative_path for record in manifest.files] + [MANIFEST_FILE]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            archive.write(run_dir.joinpath(*PurePosixPath(name).parts), f"{folder_name}/{name}")
    return buffer.getvalue()
