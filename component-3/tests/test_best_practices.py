import json
from pathlib import Path

import pytest

from intelise_c3.rag import (
    RuleCardError,
    create_store,
    format_rules_for_prompt,
    load_rule_cards,
)


@pytest.fixture(scope="module")
def store():
    return create_store("filter", "rules")


def test_all_shipped_cards_load():
    assert len(load_rule_cards("rules")) >= 10


def test_stack_and_layer_filter(store):
    rules = store.get_rules("list gpa records", "spring", "controller")
    assert rules and rules[0].id == "spring-ctrl-001"
    assert all(rule.stack in ("spring", "any") for rule in rules)
    assert all(rule.layer in ("controller", "any") for rule in rules)


def test_other_stacks_excluded(store):
    ids = {rule.id for rule in store.get_rules("ui", "spring", "controller", k=20)}
    assert "react-ui-001" not in ids and "node-ctrl-001" not in ids


def test_any_rules_included(store):
    ids = {rule.id for rule in store.get_rules("secrets", "node", "service", k=20)}
    assert "any-sec-001" in ids


def test_k_limit_and_zero(store):
    assert len(store.get_rules("x", "node", "api", k=1)) == 1
    assert store.get_rules("x", "node", "api", k=0) == []


def test_deterministic(store):
    first = store.get_rules("create gpa record", "node", "api", k=4)
    second = store.get_rules("create gpa record", "node", "api", k=4)
    assert [rule.id for rule in first] == [rule.id for rule in second]


def test_category_filter(store):
    rules = store.get_rules("x", "node", "api", k=10, category="security")
    assert rules and all(rule.category == "security" for rule in rules)


def test_unknown_stack_or_layer_raises(store):
    with pytest.raises(ValueError):
        store.get_rules("x", "django", "controller")
    with pytest.raises(ValueError):
        store.get_rules("x", "spring", "kitchen")


def test_prompt_format(store):
    text = format_rules_for_prompt(store.get_rules("x", "spring", "controller", k=1))
    assert "[spring-ctrl-001]" in text and "Avoid:" in text and "Prefer:" in text
    assert format_rules_for_prompt([]) == ""


def test_malformed_card_rejected(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(RuleCardError):
        load_rule_cards(tmp_path)


def test_duplicate_id_rejected(tmp_path):
    card = json.loads((Path("rules") / "spring-ctrl-001.json").read_text(encoding="utf-8"))
    (tmp_path / "a.json").write_text(json.dumps(card), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(RuleCardError):
        load_rule_cards(tmp_path)


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        create_store("nope", "rules")
