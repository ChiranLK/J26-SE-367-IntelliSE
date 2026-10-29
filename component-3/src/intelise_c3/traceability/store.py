"""Append-only SQLite persistence for versioned graph snapshots."""

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.domain.traceability import TraceGraphBuild, TraceGraphSnapshot


class SQLiteTraceabilityStore:
    """Persist immutable snapshots while retaining the verified source manifest."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def next_version(self, graph_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(graph_version), 0) FROM graph_snapshots WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
        return int(row[0]) + 1

    def append(
        self,
        build: TraceGraphBuild,
        manifest: GenerationManifest,
        *,
        expected_version: int | None = None,
    ) -> TraceGraphSnapshot:
        version = expected_version or self.next_version(build.graph_id)
        snapshot = TraceGraphSnapshot(
            **build.model_dump(),
            snapshot_id=str(uuid4()),
            graph_version=version,
            persisted_at_utc=datetime.now(UTC).isoformat(),
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT COALESCE(MAX(graph_version), 0) FROM graph_snapshots WHERE graph_id = ?",
                    (build.graph_id,),
                ).fetchone()[0]
                if version != int(current) + 1:
                    raise ApplicationError(
                        [
                            ErrorDetail(
                                code="GRAPH_VERSION_CONFLICT",
                                field="graph_version",
                                message="The graph changed concurrently; retry from the latest version.",
                            )
                        ],
                        status_code=status.HTTP_409_CONFLICT,
                    )
                connection.execute(
                    """
                    INSERT INTO graph_snapshots (
                        graph_id, graph_version, snapshot_id, generation_run_id,
                        artifact_digest_sha256, graph_content_digest_sha256,
                        snapshot_json, manifest_json, persisted_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.graph_id,
                        snapshot.graph_version,
                        snapshot.snapshot_id,
                        snapshot.generation_run_id,
                        snapshot.artifact_digest_sha256,
                        snapshot.graph_content_digest_sha256,
                        json.dumps(snapshot.model_dump(mode="json"), separators=(",", ":")),
                        json.dumps(manifest.model_dump(mode="json"), separators=(",", ":")),
                        snapshot.persisted_at_utc,
                    ),
                )
        except ApplicationError:
            raise
        except sqlite3.Error as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="TRACEABILITY_STORE_ERROR",
                        field="traceability_store",
                        message="The local traceability snapshot could not be persisted.",
                    )
                ],
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exception
        return snapshot

    def get(self, graph_id: str, version: int) -> TraceGraphSnapshot:
        row = self._get_row(graph_id, version)
        return TraceGraphSnapshot.model_validate(json.loads(row[0]))

    def find_by_run_id(
        self, generation_run_id: str
    ) -> tuple[str, int, GenerationManifest] | None:
        """Return the newest (graph_id, version, manifest) persisted for a run, if any."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT graph_id, graph_version, manifest_json FROM graph_snapshots
                WHERE generation_run_id = ?
                ORDER BY graph_version DESC LIMIT 1
                """,
                (generation_run_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            row["graph_id"],
            int(row["graph_version"]),
            GenerationManifest.model_validate_json(row["manifest_json"]),
        )

    def get_manifest(self, graph_id: str, version: int) -> GenerationManifest:
        row = self._get_row(graph_id, version)
        return GenerationManifest.model_validate(json.loads(row[1]))

    def latest(self, graph_id: str) -> TraceGraphSnapshot:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json FROM graph_snapshots
                WHERE graph_id = ? ORDER BY graph_version DESC LIMIT 1
                """,
                (graph_id,),
            ).fetchone()
        if row is None:
            self._not_found(graph_id, None)
        return TraceGraphSnapshot.model_validate(json.loads(row[0]))

    def _get_row(self, graph_id: str, version: int) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json, manifest_json FROM graph_snapshots
                WHERE graph_id = ? AND graph_version = ?
                """,
                (graph_id, version),
            ).fetchone()
        if row is None:
            self._not_found(graph_id, version)
        return row

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS graph_snapshots (
                        graph_id TEXT NOT NULL,
                        graph_version INTEGER NOT NULL,
                        snapshot_id TEXT NOT NULL UNIQUE,
                        generation_run_id TEXT NOT NULL,
                        artifact_digest_sha256 TEXT NOT NULL,
                        graph_content_digest_sha256 TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        persisted_at_utc TEXT NOT NULL,
                        PRIMARY KEY (graph_id, graph_version)
                    )
                    """
                )
        except sqlite3.Error as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="TRACEABILITY_STORE_ERROR",
                        field="traceability_store",
                        message="The local traceability store could not be initialized.",
                    )
                ],
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exception

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _not_found(graph_id: str, version: int | None) -> None:
        suffix = "latest version" if version is None else f"version {version}"
        raise ApplicationError(
            [
                ErrorDetail(
                    code="GRAPH_SNAPSHOT_NOT_FOUND",
                    field="graph_id",
                    message=f"Graph '{graph_id}' {suffix} was not found.",
                )
            ],
            status_code=status.HTTP_404_NOT_FOUND,
        )
