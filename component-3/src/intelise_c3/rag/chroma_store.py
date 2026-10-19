"""Embedding-backed Chroma implementation of ``BestPracticeStore``."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Callable, Optional

import chromadb

from intelise_c3.rag.best_practices import (
    SUPPORTED_LAYERS,
    SUPPORTED_STACKS,
    BestPracticeStore,
    RuleCard,
)

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-")[:40]


def _document(card: RuleCard) -> str:
    return (
        f"{card.rule}\nCategory: {card.category}. Stack: {card.stack}. "
        f"Layer: {card.layer}.\nAvoid: {card.bad_example}\nPrefer: {card.good_example}"
    )


def _default_embedding_function(model_name: str):
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)


class ChromaBestPracticeStore(BestPracticeStore):
    """Metadata-filtered semantic retrieval with deterministic re-ranking."""

    def __init__(
        self,
        cards: list[RuleCard],
        persist_dir: str | Path = "./rag_db",
        model_name: str = DEFAULT_MODEL,
        embedding_function: Optional[Callable] = None,
        min_similarity: Optional[float] = None,
    ) -> None:
        self._cards = {card.id: card for card in cards}
        self._min_similarity = min_similarity
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        embedding = embedding_function or _default_embedding_function(model_name)
        self._col = self._client.get_or_create_collection(
            name=f"best_practices__{_slug(model_name)}",
            embedding_function=embedding,
            metadata={"hnsw:space": "cosine"},
        )
        self._sync(cards)

    def _sync(self, cards: list[RuleCard]) -> None:
        wanted = {card.id for card in cards}
        existing = set(self._col.get()["ids"])
        stale = list(existing - wanted)
        if stale:
            self._col.delete(ids=stale)
        if cards:
            self._col.upsert(
                ids=[card.id for card in cards],
                documents=[_document(card) for card in cards],
                metadatas=[
                    {
                        "stack": card.stack,
                        "layer": card.layer,
                        "category": card.category,
                        "priority": card.priority,
                    }
                    for card in cards
                ],
            )

    def get_rules(self, task, stack, layer, k=4, category=None):
        if stack not in SUPPORTED_STACKS or stack == "any":
            raise ValueError(f"unsupported stack: {stack}")
        if layer not in SUPPORTED_LAYERS or layer == "any":
            raise ValueError(f"unsupported layer: {layer}")
        if k <= 0:
            return []
        clauses: list[dict] = [
            {"stack": {"$in": [stack, "any"]}},
            {"layer": {"$in": [layer, "any"]}},
        ]
        if category:
            clauses.append({"category": category})
        result = self._col.query(
            query_texts=[task or f"{stack} {layer} best practices"],
            n_results=min(k * 3, max(self._col.count(), 1)),
            where={"$and": clauses},
        )
        scored = []
        for rule_id, distance in zip(result["ids"][0], result["distances"][0]):
            similarity = 1.0 - distance
            if self._min_similarity is not None and similarity < self._min_similarity:
                continue
            card = self._cards[rule_id]
            scored.append((-round(similarity, 4), -card.priority, card.id, card))
        scored.sort(key=lambda item: item[:3])
        return [item[3] for item in scored[:k]]
