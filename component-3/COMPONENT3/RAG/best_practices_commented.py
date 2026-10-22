"""Versioned best-practice retrieval behind one stable store interface."""

from __future__ import annotations

# Import interfaces, immutable data containers, hashing and file helpers.
from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Optional

# RAG BEST-PRACTICE RETRIEVAL RULES
# BEST-PRACTICE CARD LOCATIONS
# The original guidance is stored as reviewed JSON cards under component-3/rules.
# Easy-to-open study copies are in COMPONENT3/RAG/Best-Practice-Cards.
# This Python file validates, filters and retrieves those cards.
#
# INPUT VALIDATION
# node-val-001.json validates request fields, types and ranges at the API boundary.
#
# SQL INJECTION PREVENTION
# node-repo-001.json requires parameterized SQL inside repository modules.
#
# CONTROLLER, SERVICE AND REPOSITORY SEPARATION
# node-ctrl-002.json handles HTTP errors in the controller boundary.
# node-svc-001.json keeps services testable through dependency injection.
# node-repo-001.json keeps database queries inside repository modules.
#
# REACT FORM ACCESSIBILITY
# react-ui-002.json requires labels and accessible field-error attributes.
#
# STABLE API CONTRACTS AND TEST SEAMS
# any-api-002.json defines stable service, OpenAPI and UI test seams.
# any-api-003.json defines stable OpenAPI operation IDs and schemas.
#
# DOCKER CONTAINER SECURITY
# any-dep-001.json requires non-root containers, localhost ports and health checks.

# Define the technology stacks that best-practice cards may target.
SUPPORTED_STACKS = {"react", "angular", "node", "spring", "any"}

# Define the application layers that best-practice cards may target.
SUPPORTED_LAYERS = {
    "controller", "service", "repository", "model", "ui", "api",
    "database", "test_seam", "deployment", "any",
}

# Require every rule card to contain its identity, target and guidance text.
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

# Extract simple lowercase words for deterministic keyword matching.
_TOKEN = re.compile(r"[a-z0-9_]+")


class RuleCardError(ValueError):
    """Raised when a rule card is malformed."""


@dataclass(frozen=True)
class RuleCard:
    """Store one reviewed best-practice rule and its retrieval metadata."""

    # Store the required rule identity, target, priority and examples.
    id: str
    stack: str
    layer: str
    category: str
    priority: int
    rule: str
    bad_example: str
    good_example: str

    # Store optional version, provenance and filtering metadata.
    version: str = "1.0.0"
    provenance: str = "C3 research team reviewed card"
    document_id: str = ""
    artifact_types: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    task_types: tuple[str, ...] = ()

    @property
    def chunk_id(self) -> str:
        # Build the stable chunk identity recorded in RAG evidence.
        return f"{self.document_id or self.id}#{self.id}"

    @property
    def content_digest(self) -> str:
        # Hash the rule text and examples so changes can be detected.
        text = f"{self.rule}\n{self.bad_example}\n{self.good_example}"
        return sha256(text.encode("utf-8")).hexdigest()

    @property
    def token_estimate(self) -> int:
        # Estimate how much prompt context this rule will consume.
        return estimate_tokens(f"{self.rule}\n{self.bad_example}\n{self.good_example}")


def estimate_tokens(text: str) -> int:
    """Provider-neutral token estimate (about four characters per token)."""
    return max(1, (len(text) + 3) // 4)


def _validate(raw: dict, source: str) -> RuleCard:
    # BEST-PRACTICE CARD VALIDATION
    # Validate the JSON cards for input validation, SQL safety, layering,
    # accessibility, API/test seams and Docker security before retrieval.
    # This validates the guidance card itself; C1/C2 input validation is separate.
    # Reject a card when any required field is missing.
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise RuleCardError(f"{source}: missing fields {missing}")
    # Reject an unknown technology stack.
    if raw["stack"] not in SUPPORTED_STACKS:
        raise RuleCardError(f"{source}: unsupported stack '{raw['stack']}'")
    # Reject an unknown application layer.
    if raw["layer"] not in SUPPORTED_LAYERS:
        raise RuleCardError(f"{source}: unsupported layer '{raw['layer']}'")
    # Accept only the documented priority levels.
    if raw["priority"] not in (1, 2, 3):
        raise RuleCardError(f"{source}: priority must be 1, 2 or 3")
    # Require the important text fields to contain readable values.
    for field in ("id", "rule", "bad_example", "good_example", "category"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise RuleCardError(f"{source}: '{field}' must be a non-empty string")
    # Keep authoritative requirements, policies and secrets out of RAG guidance.
    if raw["category"] in FORBIDDEN_CATEGORIES:
        raise RuleCardError(
            f"{source}: category '{raw['category']}' is authoritative truth and must not be indexed as RAG guidance"
        )
    # Validate and collect optional text metadata.
    extras: dict = {}
    for field in OPTIONAL_TEXT_FIELDS:
        if field in raw:
            if not isinstance(raw[field], str) or not raw[field].strip():
                raise RuleCardError(f"{source}: '{field}' must be a non-empty string")
            extras[field] = raw[field]
    # Validate and collect optional list-based filters.
    for field in OPTIONAL_LIST_FIELDS:
        if field in raw:
            value = raw[field]
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise RuleCardError(f"{source}: '{field}' must be a list of non-empty strings")
            extras[field] = tuple(value)
    # Reject unexpected fields so the rule-card schema stays controlled.
    unknown = set(raw) - set(REQUIRED_FIELDS) - set(OPTIONAL_TEXT_FIELDS) - set(OPTIONAL_LIST_FIELDS)
    if unknown:
        raise RuleCardError(f"{source}: unknown fields {sorted(unknown)}")
    # Return the validated immutable best-practice card.
    return RuleCard(**{field: raw[field] for field in REQUIRED_FIELDS}, **extras)


def load_rule_cards(rules_dir: str | Path) -> list[RuleCard]:
    """Load and strictly validate all JSON rule cards from ``rules_dir``."""

    # LOAD THE ACTUAL BEST-PRACTICE FILES
    # Read node-val-001, node-repo-001, React, API and Docker JSON cards
    # from component-3/rules before they can be searched by RAG.
    # Resolve and confirm the best-practice rules directory.
    base = Path(rules_dir)
    if not base.is_dir():
        raise RuleCardError(f"rules directory not found: {base}")
    # Prepare the final card list and duplicate-id tracker.
    cards: list[RuleCard] = []
    seen: set[str] = set()
    # Read every JSON rule file in a stable path order.
    for path in sorted(base.rglob("*.json")):
        # Parse the JSON and report the exact invalid file.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuleCardError(f"{path}: invalid JSON ({exc})") from exc
        # Support either one card or a list of cards per JSON file.
        for raw in data if isinstance(data, list) else [data]:
            # Validate the card and reject duplicate rule identities.
            card = _validate(raw, str(path))
            if card.id in seen:
                raise RuleCardError(f"{path}: duplicate rule id '{card.id}'")
            seen.add(card.id)
            cards.append(card)
    # Return all reviewed and validated best-practice cards.
    return cards


@dataclass(frozen=True)
class RetrievalQuery:
    """Filtered best-practice query for one affected module.

    ``artifact_type``, ``module`` and ``task_type`` filter on card metadata; a
    card with no value for a dimension applies to every value. ``top_k`` is
    clamped to 3..5 and the total retrieved text is capped by a token budget.
    """

    # Describe the current generation task and its technology target.
    task: str
    stack: str
    layer: str
    # Apply optional metadata filters and retrieval size limits.
    artifact_type: Optional[str] = None
    module: Optional[str] = None
    task_type: Optional[str] = None
    top_k: int = 4
    max_context_tokens: int = 2000


# Keep every retrieval between three and five best-practice chunks.
MIN_TOP_K = 3
MAX_TOP_K = 5


@dataclass(frozen=True)
class RetrievalHit:
    """Store one retrieved card together with its score and final rank."""

    # Keep the matched card, retrieval score and displayed position.
    card: RuleCard
    score: float
    rank: int

    def evidence(self) -> dict:
        # Convert the hit into auditable manifest evidence.
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
    # SELECT PRACTICES FOR THE CURRENT CODE MODULE
    # Examples: validation cards for API validation, SQL cards for repositories,
    # accessibility cards for React UI and Docker cards for deployment files.
    # Compare the requested artifact, module and task type with the card filters.
    for wanted, offered in (
        (query.artifact_type, card.artifact_types),
        (query.module, card.modules),
        (query.task_type, card.task_types),
    ):
        # Reject only when both sides are specific and they do not match.
        if wanted and offered and wanted not in offered:
            return False
    # An empty card filter means the card applies to every value.
    return True


def apply_context_budget(hits: list[RetrievalHit], query: RetrievalQuery) -> list[RetrievalHit]:
    """Keep the best hits within top-k (3..5) and the context-token budget."""

    # Clamp the requested result count to the safe three-to-five range.
    limit = min(max(query.top_k, MIN_TOP_K), MAX_TOP_K)

    # Track selected hits and their estimated prompt-token total.
    kept: list[RetrievalHit] = []
    used = 0
    # Keep ranked hits until the count or token budget is reached.
    for hit in hits:
        if len(kept) >= limit:
            break
        # Skip a rule that would exceed the allowed context budget.
        if used + hit.card.token_estimate > query.max_context_tokens:
            continue
        kept.append(RetrievalHit(hit.card, hit.score, len(kept) + 1))
        used += hit.card.token_estimate
    # Return the final re-ranked prompt-safe results.
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
        # Require every backend to provide the original rule-retrieval API.
        raise NotImplementedError

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        """Metadata-filtered, budgeted retrieval with ranks (score = inverse rank by default)."""

        # Request extra candidates before applying detailed metadata filters.
        candidates = self.get_rules(query.task, query.stack, query.layer, k=MAX_TOP_K * 4)

        # Convert allowed candidates into ranked retrieval hits.
        hits = [
            RetrievalHit(card, 1.0 / (index + 1), index + 1)
            for index, card in enumerate(card for card in candidates if _metadata_allows(card, query))
        ]
        # Enforce the shared result-count and token limits.
        return apply_context_budget(hits, query)


class FilterBestPracticeStore(BestPracticeStore):
    """Metadata filter with deterministic keyword and priority ranking."""

    def __init__(self, cards: list[RuleCard]):
        # Keep an in-memory copy of the validated rule cards.
        self._cards = list(cards)

    def _scored(self, task, stack, layer, category=None):
        # RANK THE RELEVANT BEST PRACTICES
        # Match the task, technology stack and application layer so unrelated
        # guidance is not sent to the code-generation step.
        # Validate the requested stack and layer before scoring cards.
        if stack not in SUPPORTED_STACKS or stack == "any":
            raise ValueError(f"unsupported stack: {stack}")
        if layer not in SUPPORTED_LAYERS or layer == "any":
            raise ValueError(f"unsupported layer: {layer}")
        # Convert the task description into unique matching words.
        task_tokens = set(_TOKEN.findall((task or "").lower()))

        # Prepare deterministic score records for matching cards.
        scored = []

        # Check every card against stack, layer and optional category filters.
        for card in self._cards:
            if card.stack not in (stack, "any") or card.layer not in (layer, "any"):
                continue
            if category and card.category != category:
                continue
            # Extract words from the card guidance and category.
            text_tokens = set(_TOKEN.findall(f"{card.rule} {card.category}".lower()))

            # Combine priority, exact target matches and shared task words.
            score = (
                card.priority * 10
                + (5 if card.stack == stack else 0)
                + (3 if card.layer == layer else 0)
                + len(task_tokens & text_tokens)
            )
            # Store a negative score so normal ascending sorting gives best first.
            scored.append((-score, card.id, card))

        # Use the card id as a stable tie-break value.
        scored.sort(key=lambda item: (item[0], item[1]))
        return scored

    def get_rules(self, task, stack, layer, k=4, category=None):
        # Return only the requested number of highest-ranked cards.
        scored = self._scored(task, stack, layer, category)
        if k <= 0:
            return []
        return [card for _, _, card in scored[:k]]

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        # Build scored hits after applying detailed metadata filters.
        hits = [
            RetrievalHit(card, float(-negative), 0)
            for negative, _, card in self._scored(query.task, query.stack, query.layer)
            if _metadata_allows(card, query)
        ]
        # Enforce the shared count and prompt-token budget.
        return apply_context_budget(hits, query)


def format_rules_for_prompt(rules: list[RuleCard]) -> str:
    # SEND THE SELECTED PRACTICES AS CONTROLLED GUIDANCE
    # Add the chosen validation, SQL, layering, accessibility, API or Docker
    # rule together with its bad and good examples to an enabled LLM prompt.
    # Return no prompt text when retrieval found no applicable rule.
    if not rules:
        return ""
    # Add each rule with its unsafe and preferred examples.
    lines = ["Apply these project best-practice rules:"]
    for rule in rules:
        lines.append(f"- [{rule.id}] {rule.rule}")
        lines.append(f"  Avoid:  {rule.bad_example}")
        lines.append(f"  Prefer: {rule.good_example}")
    # Return one bounded guidance block for the model prompt.
    return "\n".join(lines)


def create_store(
    backend: Optional[str] = None,
    rules_dir: str | Path = "rules",
) -> BestPracticeStore:
    """Create the configured backend without changing the public store API."""

    # CONNECT THE JSON CARDS TO THE RETRIEVAL BACKEND
    # Load the same reviewed practice cards for deterministic filter retrieval
    # or Chroma semantic retrieval.
    selected = (backend or os.environ.get("RAG_BACKEND", "filter")).lower()
    cards = load_rule_cards(rules_dir)

    # Use fast deterministic keyword filtering when configured.
    if selected == "filter":
        return FilterBestPracticeStore(cards)

    # Use embedding-based Chroma retrieval when configured.
    if selected == "chroma":
        from intelise_c3.rag.chroma_store import DEFAULT_MODEL, ChromaBestPracticeStore

        return ChromaBestPracticeStore(
            cards,
            persist_dir=os.environ.get("RAG_PERSIST_DIR", "./rag_db"),
            model_name=os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_MODEL),
        )
    # Reject any unrecognized backend name.
    raise ValueError(f"unknown RAG backend: {selected}")
