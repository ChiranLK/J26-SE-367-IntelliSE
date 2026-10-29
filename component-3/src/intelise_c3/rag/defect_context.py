"""Standalone defect-context retrieval (RAG A).

This module is intentionally not imported by generation or regeneration.  It
indexes verified generated source and retrieves only code chunks justified by
the existing living-traceability queries.

The provisional C4 contract has no module ID or per-module digest and makes
``explanation`` optional.  Until that contract is completed, the module path is
read from ``DefectLocation.relative_path``, the report's whole-application
digest is checked against the graph/manifest, and the verified manifest file
SHA-256 is used as the module digest for stale-chunk filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Callable, Protocol

import chromadb
from fastapi import status

from intelise_c3.contracts.defect_report import DefectReport
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GeneratedFileRecord, GenerationManifest
from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    GraphNodeType,
    TraceGraphNode,
    TraceGraphSnapshot,
)
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.rag.chroma_store import (
    DEFAULT_MODEL,
    _default_embedding_function,
    _slug,
)
from intelise_c3.traceability.queries import chain, impact_set, requirements_for_module
from intelise_c3.traceability.verification import ManifestVerificationService

DEFECT_CONTEXT_COLLECTION_PREFIX = "defect_context"
SUPPORTED_SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx"})


@dataclass(frozen=True)
class DefectContextChunk:
    chunk_id: str
    module_id: str
    source_module: str
    symbol: str
    chunk_kind: str
    content: str
    requirement_id: str
    uml_id: str
    artifact_digest: str
    version: str
    layer: str


@dataclass(frozen=True)
class RetrievedDefectContext:
    chunk_id: str
    source_module: str
    module_id: str
    symbol: str
    requirement_id: str
    uml_id: str
    artifact_digest: str
    version: str
    layer: str
    content: str
    similarity_score: float


class DefectContextStore(Protocol):
    def upsert(self, chunks: tuple[DefectContextChunk, ...]) -> None: ...

    def query(
        self,
        text: str,
        module_ids: tuple[str, ...],
    ) -> list[tuple[DefectContextChunk, float]]: ...


@dataclass(frozen=True)
class DefectContextGraph:
    snapshot: TraceGraphSnapshot
    manifest: GenerationManifest
    workspace_root: Path
    workspace_relative_path: str
    store: DefectContextStore
    top_k: int = 4


class ChromaDefectContextStore:
    """Separate Chroma collection for versioned generated-code chunks."""

    def __init__(
        self,
        persist_dir: str | Path,
        model_name: str = DEFAULT_MODEL,
        embedding_function: Callable | None = None,
    ) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        embedding = embedding_function or _default_embedding_function(model_name)
        self._collection = self._client.get_or_create_collection(
            name=f"{DEFECT_CONTEXT_COLLECTION_PREFIX}__{_slug(model_name)}",
            embedding_function=embedding,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection_name(self) -> str:
        return self._collection.name

    def upsert(self, chunks: tuple[DefectContextChunk, ...]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[item.chunk_id for item in chunks],
            documents=[item.content for item in chunks],
            metadatas=[
                {
                    "module_id": item.module_id,
                    "source_module": item.source_module,
                    "symbol": item.symbol,
                    "chunk_kind": item.chunk_kind,
                    "requirement_id": item.requirement_id,
                    "uml_id": item.uml_id,
                    "artifact_digest": item.artifact_digest,
                    "version": item.version,
                    "layer": item.layer,
                }
                for item in chunks
            ],
        )

    def query(
        self,
        text: str,
        module_ids: tuple[str, ...],
    ) -> list[tuple[DefectContextChunk, float]]:
        identifiers = tuple(sorted(set(module_ids)))
        if not identifiers or self._collection.count() == 0:
            return []
        where = {"module_id": {"$in": list(identifiers)}}
        matching_ids = self._collection.get(where=where)["ids"]
        if not matching_ids:
            return []
        result = self._collection.query(
            query_texts=[text],
            n_results=len(matching_ids),
            where=where,
        )
        ranked: list[tuple[DefectContextChunk, float]] = []
        for chunk_id, document, metadata, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            chunk = DefectContextChunk(
                chunk_id=chunk_id,
                module_id=str(metadata["module_id"]),
                source_module=str(metadata["source_module"]),
                symbol=str(metadata["symbol"]),
                chunk_kind=str(metadata["chunk_kind"]),
                content=document,
                requirement_id=str(metadata["requirement_id"]),
                uml_id=str(metadata["uml_id"]),
                artifact_digest=str(metadata["artifact_digest"]),
                version=str(metadata["version"]),
                layer=str(metadata["layer"]),
            )
            ranked.append((chunk, round(1.0 - float(distance), 4)))
        ranked.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return ranked


def index_defect_context(graph: DefectContextGraph) -> tuple[DefectContextChunk, ...]:
    """Verify and index real generated source without executing it."""
    workspace = _verify_graph_input(graph)
    chunks: list[DefectContextChunk] = []
    module_nodes = _module_nodes(graph.snapshot)
    records = {item.file_id: item for item in graph.manifest.files}

    for module_id, node in sorted(module_nodes.items()):
        record = records.get(node.source_identity)
        if record is None or PurePosixPath(record.relative_path).suffix not in SUPPORTED_SOURCE_SUFFIXES:
            continue
        requirement_ids = requirements_for_module(
            graph.snapshot, module_id, graph.manifest
        )
        if not requirement_ids:
            continue
        path = workspace.joinpath(*PurePosixPath(record.relative_path).parts)
        source = path.read_text(encoding="utf-8")
        symbols = _source_chunks(source)
        for requirement_id in requirement_ids:
            trace = chain(graph.snapshot, requirement_id)
            uml_ids = tuple(
                sorted(
                    node.source_identity
                    for node in trace.uml_nodes
                    if node.node_type is GraphNodeType.UML_ELEMENT
                )
            )
            if not uml_ids:
                continue
            for uml_id in uml_ids:
                for symbol, kind, content in symbols:
                    chunk_id = "RAGA-" + canonical_sha256(
                        {
                            "generation_run_id": graph.manifest.generation_run_id,
                            "module_id": module_id,
                            "symbol": symbol,
                            "kind": kind,
                            "requirement_id": requirement_id,
                            "uml_id": uml_id,
                        }
                    )[:24].upper()
                    chunks.append(
                        DefectContextChunk(
                            chunk_id=chunk_id,
                            module_id=module_id,
                            source_module=record.relative_path,
                            symbol=symbol,
                            chunk_kind=kind,
                            content=content,
                            requirement_id=requirement_id,
                            uml_id=uml_id,
                            artifact_digest=record.sha256,
                            version=(
                                f"{graph.manifest.generation_run_id}:"
                                f"graph-{graph.snapshot.graph_version}"
                            ),
                            layer=_layer(record),
                        )
                    )
    ordered = tuple(sorted(chunks, key=lambda item: item.chunk_id))
    graph.store.upsert(ordered)
    return ordered


def get_defect_context(
    defect_report: DefectReport,
    graph: DefectContextGraph,
) -> list[RetrievedDefectContext]:
    """Retrieve fresh chunks from graph-authorized modules only."""
    _verify_graph_input(graph)
    if not isinstance(defect_report, DefectReport):
        _fail(
            "MALFORMED_DEFECT_REPORT",
            "defect_report",
            "A validated provisional DefectReport is required.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if (
        defect_report.source_generation_run_id != graph.manifest.generation_run_id
        or defect_report.source_graph_version != graph.snapshot.graph_version
        or defect_report.source_artifact_digest_sha256
        != graph.manifest.artifact_digest_sha256
        or graph.snapshot.artifact_digest_sha256
        != graph.manifest.artifact_digest_sha256
    ):
        _fail(
            "DEFECT_CONTEXT_ARTIFACT_DIGEST_MISMATCH",
            "defect_report.source_artifact_digest_sha256",
            "The defect report is not bound to the current verified graph artifact.",
        )

    module_nodes = _module_nodes(graph.snapshot)
    current_digests = {
        node_id: str(node.attributes.get("sha256") or "")
        for node_id, node in module_nodes.items()
    }
    ranked_by_id: dict[str, RetrievedDefectContext] = {}

    for defect in defect_report.defects:
        explanation = (defect.explanation or "").strip()
        if not explanation:
            _fail(
                "DEFECT_CONTEXT_XAI_REQUIRED",
                f"defects.{defect.defect_id}.explanation",
                "Standalone defect-context retrieval requires non-empty XAI text.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        module_path = defect.location.relative_path if defect.location else None
        module_node = _find_module(module_nodes, module_path)
        if module_node is None:
            _fail(
                "DEFECT_CONTEXT_MODULE_NOT_IN_GRAPH",
                f"defects.{defect.defect_id}.location.relative_path",
                "The defect module is not an active code module in the current graph.",
            )

        module_requirements = set(
            requirements_for_module(
                graph.snapshot, module_node.node_id, graph.manifest
            )
        )
        scoped_module_ids: set[str] = set()
        for requirement_id in defect.affected_requirement_ids:
            # These calls are deliberately the established query boundary.  They
            # validate the RTM identity and apply the existing impact policy.
            trace = chain(graph.snapshot, requirement_id)
            impact = impact_set(graph.snapshot, requirement_id, graph.manifest)
            if not impact.code_node_ids:
                _fail(
                    "DEFECT_CONTEXT_NO_DOWNSTREAM_CODE",
                    f"defects.{defect.defect_id}.affected_requirement_ids",
                    f"Requirement '{trace.requirement_id}' has no downstream code scope.",
                )
            if requirement_id not in module_requirements:
                _fail(
                    "DEFECT_CONTEXT_RTM_MODULE_MISMATCH",
                    f"defects.{defect.defect_id}.affected_requirement_ids",
                    "The reported module is not linked to the referenced requirement.",
                )
            scoped_module_ids.update(impact.code_node_ids)

        if module_node.node_id not in scoped_module_ids:
            _fail(
                "DEFECT_CONTEXT_RTM_MODULE_MISMATCH",
                f"defects.{defect.defect_id}.location.relative_path",
                "The reported module is outside the graph-derived impact set.",
            )

        for chunk, similarity in graph.store.query(
            explanation, tuple(sorted(scoped_module_ids))
        ):
            # A stale index entry is evidence from an older module version and is
            # silently excluded rather than treated as a retrieval failure.
            if chunk.artifact_digest != current_digests.get(chunk.module_id):
                continue
            item = RetrievedDefectContext(
                chunk_id=chunk.chunk_id,
                source_module=chunk.source_module,
                module_id=chunk.module_id,
                symbol=chunk.symbol,
                requirement_id=chunk.requirement_id,
                uml_id=chunk.uml_id,
                artifact_digest=chunk.artifact_digest,
                version=chunk.version,
                layer=chunk.layer,
                content=chunk.content,
                similarity_score=similarity,
            )
            previous = ranked_by_id.get(item.chunk_id)
            if previous is None or item.similarity_score > previous.similarity_score:
                ranked_by_id[item.chunk_id] = item

    ranked = sorted(
        ranked_by_id.values(),
        key=lambda item: (-item.similarity_score, item.chunk_id),
    )
    return ranked[: max(graph.top_k, 0)]


def _verify_graph_input(graph: DefectContextGraph) -> Path:
    workspace = ManifestVerificationService(graph.workspace_root).verify(
        graph.manifest, graph.workspace_relative_path
    )
    if (
        graph.snapshot.generation_run_id != graph.manifest.generation_run_id
        or graph.snapshot.manifest_sha256 != canonical_sha256(graph.manifest)
    ):
        _fail(
            "DEFECT_CONTEXT_GRAPH_MANIFEST_MISMATCH",
            "graph",
            "The graph snapshot is not bound to the supplied verified manifest.",
        )
    return workspace


def _module_nodes(snapshot: TraceGraphSnapshot) -> dict[str, TraceGraphNode]:
    return {
        node.node_id: node
        for node in snapshot.nodes
        if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
        and node.node_type is GraphNodeType.CODE_MODULE
    }


def _find_module(
    nodes: dict[str, TraceGraphNode], module_path: str | None
) -> TraceGraphNode | None:
    if not module_path:
        return None
    return next(
        (
            node
            for node in nodes.values()
            if node.attributes.get("relative_path") == module_path
            or node.attributes.get("module_identity") == module_path
            or node.source_identity == module_path
            or node.node_id == module_path
        ),
        None,
    )


def _layer(record: GeneratedFileRecord) -> str:
    path = record.relative_path.lower()
    for fragment, layer in (
        ("/controllers/", "controller"),
        ("/services/", "service"),
        ("/repositories/", "repository"),
        ("/models/", "model"),
        ("/components/", "ui"),
        ("/pages/", "ui"),
        ("/tests/", "test_seam"),
    ):
        if fragment in path:
            return layer
    return record.artifact_type.value.lower()


_CLASS = re.compile(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)[^\{]*\{")
_FUNCTION = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
)
_ARROW = re.compile(
    r"(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s*)?\([^)]*\)\s*=>\s*\{"
)
_METHOD = re.compile(
    r"(?m)^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
)


def _source_chunks(source: str) -> tuple[tuple[str, str, str], ...]:
    spans: dict[tuple[int, int], tuple[str, str]] = {}
    for pattern, kind in ((_CLASS, "class"), (_FUNCTION, "function"), (_ARROW, "function")):
        for match in pattern.finditer(source):
            end = _matching_brace(source, match.end() - 1)
            if end is None:
                continue
            spans[(match.start(), end + 1)] = (match.group(1), kind)
            if kind == "class":
                body_start = match.end()
                body = source[body_start:end]
                for method in _METHOD.finditer(body):
                    brace = body_start + method.end() - 1
                    method_end = _matching_brace(source, brace)
                    if method_end is not None and method_end <= end:
                        spans[(body_start + method.start(), method_end + 1)] = (
                            f"{match.group(1)}.{method.group(1)}",
                            "method",
                        )
    if not spans:
        return (("<module>", "module", source.rstrip() + "\n"),)
    return tuple(
        (symbol, kind, source[start:end].rstrip() + "\n")
        for (start, end), (symbol, kind) in sorted(spans.items())
    )


def _matching_brace(source: str, opening: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            index += 2
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _fail(code: str, field: str, message: str, status_code: int = 409) -> None:
    raise ApplicationError(
        [ErrorDetail(code=code, field=field, message=message)],
        status_code=status_code,
    )
