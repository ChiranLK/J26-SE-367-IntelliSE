"""Runtime adapter that records exactly which best-practice rules were retrieved."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.domain.generation import RagModuleRetrieval, RagRetrievalEvidence
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.rag.best_practices import (
    BestPracticeStore,
    FilterBestPracticeStore,
    format_rules_for_prompt,
    load_rule_cards,
)


class RagRuntime:
    """One generation run's retrieval store and append-only audit collector."""

    def __init__(
        self,
        *,
        enabled: bool,
        backend: str,
        embedding_model: str | None,
        store: BestPracticeStore | None,
        rule_corpus_sha256: str | None,
    ) -> None:
        self.enabled = enabled
        self.backend = backend
        self.embedding_model = embedding_model
        self.store = store
        self.rule_corpus_sha256 = rule_corpus_sha256
        self._retrievals: list[RagModuleRetrieval] = []

    @classmethod
    def disabled(cls) -> "RagRuntime":
        return cls(
            enabled=False,
            backend="off",
            embedding_model=None,
            store=None,
            rule_corpus_sha256=None,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "RagRuntime":
        # A few compatibility/test callers supply the older partial settings
        # namespace.  Absence must preserve the pre-RAG behaviour rather than
        # unexpectedly enabling retrieval or raising during generation.
        if not getattr(settings, "rag_enabled", False):
            return cls.disabled()
        rules_dir = COMPONENT_ROOT / "rules"
        cards = load_rule_cards(rules_dir)
        if settings.rag_backend == "filter":
            store: BestPracticeStore = FilterBestPracticeStore(cards)
            embedding_model = None
        else:
            from intelise_c3.rag.chroma_store import ChromaBestPracticeStore

            store = ChromaBestPracticeStore(
                cards,
                persist_dir=settings.rag_persist_dir,
                model_name=settings.rag_embedding_model,
            )
            embedding_model = settings.rag_embedding_model
        return cls(
            enabled=True,
            backend=settings.rag_backend,
            embedding_model=embedding_model,
            store=store,
            rule_corpus_sha256=canonical_sha256([asdict(card) for card in cards]),
        )

    @classmethod
    def for_test(
        cls,
        store: BestPracticeStore,
        *,
        backend: str = "filter",
        embedding_model: str | None = None,
        rules_dir: Path = COMPONENT_ROOT / "rules",
    ) -> "RagRuntime":
        cards = load_rule_cards(rules_dir)
        return cls(
            enabled=True,
            backend=backend,
            embedding_model=embedding_model,
            store=store,
            rule_corpus_sha256=canonical_sha256([asdict(card) for card in cards]),
        )

    def retrieve(
        self,
        *,
        module_path: str,
        task: str,
        stack: str,
        layer: str,
        applied_to_prompt: bool,
        k: int = 4,
    ) -> str:
        rules = (
            self.store.get_rules(task, stack, layer, k=k)
            if self.enabled and self.store is not None
            else []
        )
        self._retrievals.append(
            RagModuleRetrieval(
                module_path=module_path,
                task=task,
                stack=stack,
                layer=layer,
                retrieved_rule_ids=tuple(rule.id for rule in rules),
                applied_to_prompt=applied_to_prompt and bool(rules),
            )
        )
        return format_rules_for_prompt(rules) if applied_to_prompt else ""

    def new_run(self) -> "RagRuntime":
        """Reuse the configured store while starting an empty per-run audit."""
        return RagRuntime(
            enabled=self.enabled,
            backend=self.backend,
            embedding_model=self.embedding_model,
            store=self.store,
            rule_corpus_sha256=self.rule_corpus_sha256,
        )

    def evidence(self) -> RagRetrievalEvidence:
        return RagRetrievalEvidence(
            enabled=self.enabled,
            backend=self.backend,
            embedding_model=self.embedding_model,
            rule_corpus_sha256=self.rule_corpus_sha256,
            retrievals=tuple(self._retrievals),
        )
