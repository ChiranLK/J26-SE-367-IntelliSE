"""Deterministic, versioned generation-rule engine.

Rules (``component-3/generation-rules``) are kept separate from Knowledge Base
facts. A *target* is one unit that needs a decision (the selected stack, a UML
class, a requirement, a UI screen or a cross-cutting concern) described by a
flat fact dictionary. For each target and rule category the highest-priority
matching rule wins. Equal top priority between different rules is AMBIGUOUS
(-> REVIEW_REQUIRED). A target with no matching rule in any category is
UNSUPPORTED: the engine never fabricates an implementation for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.hybrid.knowledge_base import KnowledgeBase

RULES_ROOT = COMPONENT_ROOT / "generation-rules"
_OPERATORS = {"equals", "not_equals", "in", "contains", "contains_all", "subset_of", "exists"}
_REQUIRED_RULE_FIELDS = (
    "rule_id", "version", "category", "priority", "target_kind", "conditions",
    "produces", "requires_knowledge", "validation_requirements", "traceability", "on_failure",
)
_FAILURE_BEHAVIORS = {"REVIEW_REQUIRED", "UNSUPPORTED", "FAILED"}


class RuleOutcome(StrEnum):
    MATCHED = "MATCHED"
    UNSUPPORTED = "UNSUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class RuleSetError(ValueError):
    """Raised when the rule base is malformed or references unknown facts."""


@dataclass(frozen=True)
class GenerationRule:
    rule_id: str
    version: str
    category: str
    priority: int
    description: str
    target_kind: str
    conditions: tuple[dict[str, Any], ...]
    module_ids: tuple[str, ...]
    artifact_types: tuple[str, ...]
    requires_knowledge: tuple[str, ...]
    validation_requirements: tuple[str, ...]
    traceability: dict[str, Any]
    on_failure: str

    @property
    def ref(self) -> str:
        return f"{self.rule_id}@{self.version}"

    def matches(self, facts: dict[str, Any]) -> bool:
        return all(_condition_holds(condition, facts) for condition in self.conditions)


@dataclass(frozen=True)
class RuleSet:
    rule_set_id: str
    rule_set_version: str
    digest_sha256: str
    rules: tuple[GenerationRule, ...]

    def by_id(self, rule_id: str) -> GenerationRule:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise RuleSetError(f"unknown rule '{rule_id}'")

    def summary(self) -> dict[str, Any]:
        return {
            "rule_set_id": self.rule_set_id,
            "rule_set_version": self.rule_set_version,
            "rule_set_digest_sha256": self.digest_sha256,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "version": rule.version,
                    "category": rule.category,
                    "priority": rule.priority,
                    "target_kind": rule.target_kind,
                    "description": rule.description,
                    "module_ids": list(rule.module_ids),
                    "requires_knowledge": list(rule.requires_knowledge),
                    "on_failure": rule.on_failure,
                }
                for rule in self.rules
            ],
        }


@dataclass(frozen=True)
class GenerationTarget:
    target_id: str
    kind: str
    facts: dict[str, Any]
    requirement_ids: tuple[str, ...] = ()
    uml_refs: tuple[str, ...] = ()


@dataclass
class TargetDecision:
    target_id: str
    kind: str
    outcome: RuleOutcome
    matched_rules: list[GenerationRule] = field(default_factory=list)
    candidate_rule_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    requirement_ids: tuple[str, ...] = ()
    uml_refs: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "kind": self.kind,
            "outcome": self.outcome.value,
            "matched_rules": [rule.ref for rule in self.matched_rules],
            "candidate_rule_ids": self.candidate_rule_ids,
            "reasons": self.reasons,
            "requirement_ids": list(self.requirement_ids),
            "uml_refs": list(self.uml_refs),
        }


def _condition_holds(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
    fact = condition["fact"]
    value = facts.get(fact)
    if "exists" in condition:
        return (fact in facts) is bool(condition["exists"])
    if "equals" in condition:
        return value == condition["equals"]
    if "not_equals" in condition:
        return value != condition["not_equals"]
    if "in" in condition:
        return value in condition["in"]
    if "contains" in condition:
        return isinstance(value, (list, tuple, set)) and condition["contains"] in value
    if "contains_all" in condition:
        return isinstance(value, (list, tuple, set)) and set(condition["contains_all"]) <= set(value)
    if "subset_of" in condition:
        return isinstance(value, (list, tuple, set)) and set(value) <= set(condition["subset_of"])
    return False


def _parse_rule(raw: dict[str, Any], source: str) -> GenerationRule:
    missing = [key for key in _REQUIRED_RULE_FIELDS if key not in raw]
    if missing:
        raise RuleSetError(f"{source}: rule missing fields {missing}")
    conditions = raw["conditions"].get("all") if isinstance(raw["conditions"], dict) else None
    if not isinstance(conditions, list) or not conditions:
        raise RuleSetError(f"{source}: rule '{raw['rule_id']}' needs a non-empty conditions.all list")
    for condition in conditions:
        operators = set(condition) - {"fact"}
        if "fact" not in condition or len(operators) != 1 or not operators <= _OPERATORS:
            raise RuleSetError(f"{source}: rule '{raw['rule_id']}' has an invalid condition {condition}")
    if not isinstance(raw["priority"], int) or raw["priority"] < 0:
        raise RuleSetError(f"{source}: rule '{raw['rule_id']}' priority must be a non-negative integer")
    if raw["on_failure"] not in _FAILURE_BEHAVIORS:
        raise RuleSetError(f"{source}: rule '{raw['rule_id']}' has unknown on_failure '{raw['on_failure']}'")
    return GenerationRule(
        rule_id=raw["rule_id"],
        version=raw["version"],
        category=raw["category"],
        priority=raw["priority"],
        description=raw.get("description", ""),
        target_kind=raw["target_kind"],
        conditions=tuple(conditions),
        module_ids=tuple(raw["produces"].get("module_ids", ())),
        artifact_types=tuple(raw["produces"].get("artifact_types", ())),
        requires_knowledge=tuple(raw["requires_knowledge"]),
        validation_requirements=tuple(raw["validation_requirements"]),
        traceability=raw["traceability"],
        on_failure=raw["on_failure"],
    )


def load_rule_set(root: Path = RULES_ROOT, knowledge_base: KnowledgeBase | None = None) -> RuleSet:
    """Load the rule base; when a KB is given, every referenced knowledge item must exist."""
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuleSetError(f"generation-rules manifest unreadable ({error})") from error
    rules: list[GenerationRule] = []
    seen: set[str] = set()
    documents: dict[str, Any] = {}
    for name in manifest["files"]:
        document = json.loads((root / name).read_text(encoding="utf-8"))
        documents[name] = document
        for raw in document.get("rules", []):
            rule = _parse_rule(raw, name)
            if rule.rule_id in seen:
                raise RuleSetError(f"{name}: duplicate rule id '{rule.rule_id}'")
            seen.add(rule.rule_id)
            if knowledge_base is not None:
                unknown = [item for item in rule.requires_knowledge if item not in knowledge_base.items]
                if unknown:
                    raise RuleSetError(f"{name}: rule '{rule.rule_id}' references unknown knowledge items {unknown}")
            rules.append(rule)
    return RuleSet(
        rule_set_id=manifest["rule_set_id"],
        rule_set_version=manifest["rule_set_version"],
        digest_sha256=canonical_sha256({"manifest": manifest, "documents": documents}),
        rules=tuple(sorted(rules, key=lambda rule: rule.rule_id)),
    )


class RuleEngine:
    """Evaluate targets against a rule set deterministically."""

    def __init__(self, rule_set: RuleSet) -> None:
        self._rule_set = rule_set

    def decide(self, target: GenerationTarget) -> TargetDecision:
        candidates = [
            rule for rule in self._rule_set.rules
            if rule.target_kind == target.kind and rule.matches(target.facts)
        ]
        decision = TargetDecision(
            target_id=target.target_id,
            kind=target.kind,
            outcome=RuleOutcome.UNSUPPORTED,
            candidate_rule_ids=sorted(rule.rule_id for rule in candidates),
            requirement_ids=target.requirement_ids,
            uml_refs=target.uml_refs,
        )
        if not candidates:
            decision.reasons.append("NO_RULE_MATCHED: no versioned rule covers this target; no implementation is fabricated.")
            return decision
        by_category: dict[str, list[GenerationRule]] = {}
        for rule in candidates:
            by_category.setdefault(rule.category, []).append(rule)
        ambiguous = False
        for category in sorted(by_category):
            rules = sorted(by_category[category], key=lambda rule: (-rule.priority, rule.rule_id))
            top = [rule for rule in rules if rule.priority == rules[0].priority]
            if len(top) > 1:
                ambiguous = True
                decision.reasons.append(
                    f"AMBIGUOUS_RULES: category {category} has equal-priority matches "
                    f"{[rule.rule_id for rule in top]}."
                )
            else:
                decision.matched_rules.append(top[0])
        if ambiguous:
            decision.outcome = RuleOutcome.AMBIGUOUS
            decision.matched_rules = []
        else:
            decision.outcome = RuleOutcome.MATCHED
        return decision

    def decide_all(self, targets: list[GenerationTarget]) -> list[TargetDecision]:
        return [self.decide(target) for target in sorted(targets, key=lambda target: target.target_id)]


def review_state(decisions: list[TargetDecision]) -> RuleOutcome:
    """Aggregate per-target outcomes: any AMBIGUOUS/REVIEW -> REVIEW_REQUIRED; any FAILED -> FAILED."""
    outcomes = {decision.outcome for decision in decisions}
    if RuleOutcome.FAILED in outcomes:
        return RuleOutcome.FAILED
    if outcomes & {RuleOutcome.AMBIGUOUS, RuleOutcome.REVIEW_REQUIRED}:
        return RuleOutcome.REVIEW_REQUIRED
    if RuleOutcome.UNSUPPORTED in outcomes:
        return RuleOutcome.UNSUPPORTED
    return RuleOutcome.MATCHED
