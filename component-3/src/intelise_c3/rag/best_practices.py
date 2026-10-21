"""Versioned best-practice retrieval behind one stable store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Optional

SUPPORTED_STACKS = {"react", "angular", "node", "spring", "any"}
SUPPORTED_LAYERS = {
    "controller", "service", "repository", "model", "ui", "api",
    "database", "test_seam", "deployment", "any",
}
REQUIRED_FIELDS = (
    "id", "stack", "layer", "category", "priority", "rule",
    "bad_example", "good_example",
)
# Optional retrieval metadata. Cards without it keep their historical meaning:
# empty tuples mean "applies to any artifact type / module / task type".
OPTIONAL_LIST_FIELDS = ("artifact_types", "modules", "task_types")
OPTIONAL_TEXT_FIELDS = ("version", "provenance", "document_id")
# Material that must never be indexed as best-practice guidance: upstream truth
# (C1 approval, C2 meaning), domain facts (grade points/formula), C4 decisions
# and secrets belong to contracts or the structured Knowledge Base instead.
FORBIDDEN_CATEGORIES = {
    "requirement-approval", "uml-semantics", "grading-policy", "gpa-formula",
    "readiness-decision", "secret", "credential",
}
_TOKEN = re.compile(r"[a-z0-9_]+")


class RuleCardError(ValueError):
    """Raised when a rule card is malformed."""


@dataclass(frozen=True)
class RuleCard:
    id: str
    stack: str
    layer: str
    category: str
    priority: int
    rule: str
    bad_example: str
    good_example: str
    version: str = "1.0.0"
    provenance: str = "C3 research team reviewed card"
    document_id: str = ""
    artifact_types: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    task_types: tuple[str, ...] = ()

    @property
    def chunk_id(self) -> str:
        return f"{self.document_id or self.id}#{self.id}"

    @property
    def content_digest(self) -> str:
        text = f"{self.rule}\n{self.bad_example}\n{self.good_example}"
        return sha256(text.encode("utf-8")).hexdigest()

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(f"{self.rule}\n{self.bad_example}\n{self.good_example}")


def estimate_tokens(text: str) -> int:
    """Provider-neutral token estimate (about four characters per token)."""
    return max(1, (len(text) + 3) // 4)


def _validate(raw: dict, source: str) -> RuleCard:
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise RuleCardError(f"{source}: missing fields {missing}")
    if raw["stack"] not in SUPPORTED_STACKS:
        raise RuleCardError(f"{source}: unsupported stack '{raw['stack']}'")
    if raw["layer"] not in SUPPORTED_LAYERS:
        raise RuleCardError(f"{source}: unsupported layer '{raw['layer']}'")
    if raw["priority"] not in (1, 2, 3):
        raise RuleCardError(f"{source}: priority must be 1, 2 or 3")
    for field in ("id", "rule", "bad_example", "good_example", "category"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise RuleCardError(f"{source}: '{field}' must be a non-empty string")
    if raw["category"] in FORBIDDEN_CATEGORIES:
        raise RuleCardError(
            f"{source}: category '{raw['category']}' is authoritative truth and must not be indexed as RAG guidance"
        )
    extras: dict = {}
    for field in OPTIONAL_TEXT_FIELDS:
        if field in raw:
            if not isinstance(raw[field], str) or not raw[field].strip():
                raise RuleCardError(f"{source}: '{field}' must be a non-empty string")
            extras[field] = raw[field]
    for field in OPTIONAL_LIST_FIELDS:
        if field in raw:
            value = raw[field]
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise RuleCardError(f"{source}: '{field}' must be a list of non-empty strings")
            extras[field] = tuple(value)
    unknown = set(raw) - set(REQUIRED_FIELDS) - set(OPTIONAL_TEXT_FIELDS) - set(OPTIONAL_LIST_FIELDS)
    if unknown:
        raise RuleCardError(f"{source}: unknown fields {sorted(unknown)}")
    return RuleCard(**{field: raw[field] for field in REQUIRED_FIELDS}, **extras)


def load_rule_cards(rules_dir: str | Path) -> list[RuleCard]:
    """Load and strictly validate all JSON rule cards from ``rules_dir``."""
    base = Path(rules_dir)
    if not base.is_dir():
        raise RuleCardError(f"rules directory not found: {base}")
    cards: list[RuleCard] = []
    seen: set[str] = set()
    for path in sorted(base.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuleCardError(f"{path}: invalid JSON ({exc})") from exc
        for raw in data if isinstance(data, list) else [data]:
            card = _validate(raw, str(path))
            if card.id in seen:
                raise RuleCardError(f"{path}: duplicate rule id '{card.id}'")
            seen.add(card.id)
            cards.append(card)
    return cards


@dataclass(frozen=True)
class RetrievalQuery:
    """Filtered best-practice query for one affected module.

    ``artifact_type``, ``module`` and ``task_type`` filter on card metadata; a
    card with no value for a dimension applies to every value. ``top_k`` is
    clamped to 3..5 and the total retrieved text is capped by a token budget.
    """

    task: str
    stack: str
    layer: str
    artifact_type: Optional[str] = None
    module: Optional[str] = None
    task_type: Optional[str] = None
    top_k: int = 4
    max_context_tokens: int = 2000


MIN_TOP_K = 3
MAX_TOP_K = 5


@dataclass(frozen=True)
class RetrievalHit:
    card: RuleCard
    score: float
    rank: int

    def evidence(self) -> dict:
        return {
            "rank": self.rank,
            "chunk_id": self.card.chunk_id,
            "document_id": self.card.document_id or self.card.id,
            "rule_id": self.card.id,
            "version": self.card.version,
            "stack": self.card.stack,
            "layer": self.card.layer,
            "category": self.card.category,
            "artifact_types": list(self.card.artifact_types),
            "provenance": self.card.provenance,
            "content_digest_sha256": self.card.content_digest,
            "token_estimate": self.card.token_estimate,
            "score": round(self.score, 6),
        }


def _metadata_allows(card: RuleCard, query: RetrievalQuery) -> bool:
    for wanted, offered in (
        (query.artifact_type, card.artifact_types),
        (query.module, card.modules),
        (query.task_type, card.task_types),
    ):
        if wanted and offered and wanted not in offered:
            return False
    return True


def apply_context_budget(hits: list[RetrievalHit], query: RetrievalQuery) -> list[RetrievalHit]:
    """Keep the best hits within top-k (3..5) and the context-token budget."""
    limit = min(max(query.top_k, MIN_TOP_K), MAX_TOP_K)
    kept: list[RetrievalHit] = []
    used = 0
    for hit in hits:
        if len(kept) >= limit:
            break
        if used + hit.card.token_estimate > query.max_context_tokens:
            continue
        kept.append(RetrievalHit(hit.card, hit.score, len(kept) + 1))
        used += hit.card.token_estimate
    return kept


class BestPracticeStore(ABC):
    """Stable interface shared by filter and Chroma implementations."""

    @abstractmethod
    def get_rules(
        self,
        task: str,
        stack: str,
        layer: str,
        k: int = 4,
        category: Optional[str] = None,
    ) -> list[RuleCard]:
        raise NotImplementedError

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        """Metadata-filtered, budgeted retrieval with ranks (score = inverse rank by default)."""
        candidates = self.get_rules(query.task, query.stack, query.layer, k=MAX_TOP_K * 4)
        hits = [
            RetrievalHit(card, 1.0 / (index + 1), index + 1)
            for index, card in enumerate(card for card in candidates if _metadata_allows(card, query))
        ]
        return apply_context_budget(hits, query)


class FilterBestPracticeStore(BestPracticeStore):
    """Metadata filter with deterministic keyword and priority ranking."""

    def __init__(self, cards: list[RuleCard]):
        self._cards = list(cards)

    def _scored(self, task, stack, layer, category=None):
        if stack not in SUPPORTED_STACKS or stack == "any":
            raise ValueError(f"unsupported stack: {stack}")
        if layer not in SUPPORTED_LAYERS or layer == "any":
            raise ValueError(f"unsupported layer: {layer}")
        task_tokens = set(_TOKEN.findall((task or "").lower()))
        scored = []
        for card in self._cards:
            if card.stack not in (stack, "any") or card.layer not in (layer, "any"):
                continue
            if category and card.category != category:
                continue
            text_tokens = set(_TOKEN.findall(f"{card.rule} {card.category}".lower()))
            score = (
                card.priority * 10
                + (5 if card.stack == stack else 0)
                + (3 if card.layer == layer else 0)
                + len(task_tokens & text_tokens)
            )
            scored.append((-score, card.id, card))
        scored.sort(key=lambda item: (item[0], item[1]))
        return scored

    def get_rules(self, task, stack, layer, k=4, category=None):
        scored = self._scored(task, stack, layer, category)
        if k <= 0:
            return []
        return [card for _, _, card in scored[:k]]

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        hits = [
            RetrievalHit(card, float(-negative), 0)
            for negative, _, card in self._scored(query.task, query.stack, query.layer)
            if _metadata_allows(card, query)
        ]
        return apply_context_budget(hits, query)


def format_rules_for_prompt(rules: list[RuleCard]) -> str:
    if not rules:
        return ""
    lines = ["Apply these project best-practice rules:"]
    for rule in rules:
        lines.append(f"- [{rule.id}] {rule.rule}")
        lines.append(f"  Avoid:  {rule.bad_example}")
        lines.append(f"  Prefer: {rule.good_example}")
    return "\n".join(lines)


def create_store(
    backend: Optional[str] = None,
    rules_dir: str | Path = "rules",
) -> BestPracticeStore:
    """Create the configured backend without changing the public store API."""
    selected = (backend or os.environ.get("RAG_BACKEND", "filter")).lower()
    cards = load_rule_cards(rules_dir)
    if selected == "filter":
        return FilterBestPracticeStore(cards)
    if selected == "chroma":
        from intelise_c3.rag.chroma_store import DEFAULT_MODEL, ChromaBestPracticeStore

        return ChromaBestPracticeStore(
            cards,
            persist_dir=os.environ.get("RAG_PERSIST_DIR", "./rag_db"),
            model_name=os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_MODEL),
        )
    raise ValueError(f"unknown RAG backend: {selected}")
