"""Embedding-backed Chroma implementation of ``BestPracticeStore``."""

from __future__ import annotations

# Import file paths, collection-name cleanup and optional callback types.
from pathlib import Path
import re
from typing import Callable, Optional

# Import the persistent vector database used for semantic retrieval.
import chromadb

from intelise_c3.rag.best_practices import (
    MAX_TOP_K,
    SUPPORTED_LAYERS,
    SUPPORTED_STACKS,
    BestPracticeStore,
    RetrievalHit,
    RetrievalQuery,
    RuleCard,
    _metadata_allows,
    apply_context_budget,
)

# RAG SEMANTIC RETRIEVAL SETTINGS
# Use this sentence-transformer model unless another model is configured.
DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _slug(text: str) -> str:
    # Convert the embedding-model name into a safe Chroma collection suffix.
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-")[:40]


def _document(card: RuleCard) -> str:
    # Combine the rule and examples into the text stored as one vector document.
    return (
        f"{card.rule}\nCategory: {card.category}. Stack: {card.stack}. "
        f"Layer: {card.layer}.\nAvoid: {card.bad_example}\nPrefer: {card.good_example}"
    )


def _default_embedding_function(model_name: str):
    # Load the configured sentence-transformer embedding function only when needed.
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
        # CHROMA STORE SETUP
        # Keep a direct id-to-card lookup for converting vector results back to rules.
        self._cards = {card.id: card for card in cards}

        # Save the optional minimum semantic-similarity threshold.
        self._min_similarity = min_similarity

        # Open or create the persistent Chroma database directory.
        self._client = chromadb.PersistentClient(path=str(persist_dir))

        # Use a supplied embedding function or load the configured default model.
        embedding = embedding_function or _default_embedding_function(model_name)

        # Open one cosine-distance collection for this embedding model.
        self._col = self._client.get_or_create_collection(
            name=f"best_practices__{_slug(model_name)}",
            embedding_function=embedding,
            metadata={"hnsw:space": "cosine"},
        )
        # Synchronize the persistent vector collection with the current JSON cards.
        self._sync(cards)

    def _sync(self, cards: list[RuleCard]) -> None:
        # CHROMA INDEX SYNCHRONIZATION
        # Compare current JSON rule ids with ids already stored in Chroma.
        wanted = {card.id for card in cards}
        existing = set(self._col.get()["ids"])
        # Find and delete vector records for rules removed from the JSON corpus.
        stale = list(existing - wanted)
        if stale:
            self._col.delete(ids=stale)
        # Insert new cards and update changed cards with their filter metadata.
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
        # SEMANTIC BEST-PRACTICE RETRIEVAL
        # Validate the requested technology stack and application layer.
        if stack not in SUPPORTED_STACKS or stack == "any":
            raise ValueError(f"unsupported stack: {stack}")
        if layer not in SUPPORTED_LAYERS or layer == "any":
            raise ValueError(f"unsupported layer: {layer}")
        # Return no results when the caller requests a non-positive count.
        if k <= 0:
            return []
        # Build Chroma metadata filters for exact stack/layer or shared "any" cards.
        clauses: list[dict] = [
            {"stack": {"$in": [stack, "any"]}},
            {"layer": {"$in": [layer, "any"]}},
        ]
        # Add an exact category filter when the caller supplies one.
        if category:
            clauses.append({"category": category})
        # Embed the task and request extra semantic candidates for re-ranking.
        result = self._col.query(
            query_texts=[task or f"{stack} {layer} best practices"],
            n_results=min(k * 3, max(self._col.count(), 1)),
            where={"$and": clauses},
        )
        # Convert cosine distances into similarity-based score records.
        scored = []
        for rule_id, distance in zip(result["ids"][0], result["distances"][0]):
            # Chroma cosine distance becomes similarity by subtracting from one.
            similarity = 1.0 - distance

            # Ignore a result below the optional similarity threshold.
            if self._min_similarity is not None and similarity < self._min_similarity:
                continue
            card = self._cards[rule_id]
            # Rank by similarity, priority and stable rule id.
            scored.append((-round(similarity, 4), -card.priority, card.id, card))

        # Sort deterministically and return only the requested number of cards.
        scored.sort(key=lambda item: item[:3])
        return [item[3] for item in scored[:k]]

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        """Semantic retrieval with metadata filters; the score is cosine similarity."""

        # Validate the structured retrieval query.
        if query.stack not in SUPPORTED_STACKS or query.stack == "any":
            raise ValueError(f"unsupported stack: {query.stack}")
        if query.layer not in SUPPORTED_LAYERS or query.layer == "any":
            raise ValueError(f"unsupported layer: {query.layer}")
        # Retrieve a wider semantic candidate set for metadata filtering.
        result = self._col.query(
            query_texts=[query.task or f"{query.stack} {query.layer} best practices"],
            n_results=max(min(MAX_TOP_K * 4, self._col.count()), 1),
            where={"$and": [{"stack": {"$in": [query.stack, "any"]}}, {"layer": {"$in": [query.layer, "any"]}}]},
        )
        # Convert allowed semantic matches into auditable retrieval hits.
        hits = []
        for rule_id, distance in zip(result["ids"][0], result["distances"][0]):
            # Calculate cosine similarity and apply the optional minimum threshold.
            similarity = 1.0 - distance
            if self._min_similarity is not None and similarity < self._min_similarity:
                continue
            card = self._cards[rule_id]
            # Apply artifact, module and task-type filters not stored in Chroma.
            if _metadata_allows(card, query):
                hits.append(RetrievalHit(card, round(similarity, 6), 0))
        # Re-rank deterministically by similarity, priority and rule id.
        hits.sort(key=lambda hit: (-hit.score, -hit.card.priority, hit.card.id))

        # Enforce the shared three-to-five result count and prompt-token budget.
        return apply_context_budget(hits, query)
