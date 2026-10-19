"""Offline Chroma tests use deterministic fake embeddings, not quality evidence."""

import hashlib
import re

import pytest

pytest.importorskip("chromadb")

from intelise_c3.rag import load_rule_cards  # noqa: E402
from intelise_c3.rag.chroma_store import ChromaBestPracticeStore  # noqa: E402

DIM = 256


class FakeEmbedding:
    @staticmethod
    def name():
        return "fake-hash-embedding"

    def __call__(self, input):
        output = []
        for text in input:
            vector = [0.0] * DIM
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                index = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM
                vector[index] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            output.append([value / norm for value in vector])
        return output

    def embed_query(self, input):
        return self.__call__(input)

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return FakeEmbedding()

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine"]


@pytest.fixture()
def store(tmp_path):
    return ChromaBestPracticeStore(
        load_rule_cards("rules"),
        persist_dir=tmp_path,
        model_name="fake",
        embedding_function=FakeEmbedding(),
    )


def test_metadata_filter_applies(store):
    rules = store.get_rules("controller calls repository directly", "spring", "controller", k=10)
    assert rules
    assert all(rule.stack in ("spring", "any") for rule in rules)
    assert all(rule.layer in ("controller", "any") for rule in rules)


def test_semantic_match_ranks_relevant_rule_first(store):
    rules = store.get_rules(
        "controllers must not access repositories directly use service layer",
        "spring", "controller", k=3,
    )
    assert rules[0].id == "spring-ctrl-001"


def test_k_limit_and_zero(store):
    assert len(store.get_rules("anything", "node", "api", k=1)) == 1
    assert store.get_rules("anything", "node", "api", k=0) == []


def test_category_filter(store):
    rules = store.get_rules("input", "node", "api", k=10, category="security")
    assert rules and all(rule.category == "security" for rule in rules)


def test_deterministic(store):
    first = [rule.id for rule in store.get_rules("create record api", "node", "api", k=4)]
    second = [rule.id for rule in store.get_rules("create record api", "node", "api", k=4)]
    assert first == second


def test_index_syncs_with_rule_files(tmp_path):
    cards = load_rule_cards("rules")
    first = ChromaBestPracticeStore(cards, tmp_path, "fake", FakeEmbedding())
    assert first._col.count() == len(cards)
    second = ChromaBestPracticeStore(cards[:3], tmp_path, "fake", FakeEmbedding())
    assert second._col.count() == 3


def test_min_similarity_can_return_nothing(tmp_path):
    store = ChromaBestPracticeStore(
        load_rule_cards("rules"), tmp_path, "fake", FakeEmbedding(), min_similarity=0.99
    )
    assert store.get_rules("zzz qqq", "spring", "controller") == []


def test_unknown_stack_raises(store):
    with pytest.raises(ValueError):
        store.get_rules("x", "django", "controller")
