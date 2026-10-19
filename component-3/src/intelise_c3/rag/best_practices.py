"""Versioned best-practice retrieval behind one stable store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Optional

SUPPORTED_STACKS = {"react", "angular", "node", "spring", "any"}
SUPPORTED_LAYERS = {
    "controller", "service", "repository", "model", "ui", "api",
    "database", "test_seam", "any",
}
REQUIRED_FIELDS = (
    "id", "stack", "layer", "category", "priority", "rule",
    "bad_example", "good_example",
)
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
    return RuleCard(**{field: raw[field] for field in REQUIRED_FIELDS})


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


class FilterBestPracticeStore(BestPracticeStore):
    """Metadata filter with deterministic keyword and priority ranking."""

    def __init__(self, cards: list[RuleCard]):
        self._cards = list(cards)

    def get_rules(self, task, stack, layer, k=4, category=None):
        if stack not in SUPPORTED_STACKS or stack == "any":
            raise ValueError(f"unsupported stack: {stack}")
        if layer not in SUPPORTED_LAYERS or layer == "any":
            raise ValueError(f"unsupported layer: {layer}")
        if k <= 0:
            return []
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
        return [card for _, _, card in scored[:k]]


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
