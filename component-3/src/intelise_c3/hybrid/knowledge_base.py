"""Versioned, structured Knowledge Base of facts (not rules, not RAG).

The KB is loaded from ``component-3/knowledge-base``. Every file is validated,
every knowledge item has a stable ``item_id`` (used as a KNOWLEDGE_ITEM trace
node), and a canonical digest over the parsed JSON binds generation caches and
manifests to the exact facts used. Digests are computed over parsed JSON so a
CRLF checkout does not change them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.generation.evidence import canonical_sha256

KB_ROOT = COMPONENT_ROOT / "knowledge-base"
POLICY_AUTHORITY_STATUSES = frozenset({"SAMPLE_RESEARCH_POLICY", "CLIENT_APPROVED_POLICY"})


class KnowledgeBaseError(ValueError):
    """Raised when the Knowledge Base is malformed or internally inconsistent."""


@dataclass(frozen=True)
class GradeEntry:
    grade: str
    grade_point: float
    grade_point_tenths: int
    marks_min: int
    marks_max: int
    counts_as_pass: bool


@dataclass(frozen=True)
class GradingPolicy:
    item_id: str
    policy_id: str
    policy_version: str
    policy_name: str
    authority_status: str
    authority_status_reason: str
    requires_explicit_acceptance: bool
    institution: str
    scale_maximum: float
    grades: tuple[GradeEntry, ...]
    provenance: dict[str, Any]
    known_unverified_aspects: tuple[str, ...]
    digest_sha256: str

    def grade_point_tenths(self, grade: str) -> int | None:
        for entry in self.grades:
            if entry.grade == grade:
                return entry.grade_point_tenths
        return None

    def disclosure(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_name": self.policy_name,
            "authority_status": self.authority_status,
            "authority_status_reason": self.authority_status_reason,
            "institution": self.institution,
            "policy_digest_sha256": self.digest_sha256,
            "known_unverified_aspects": list(self.known_unverified_aspects),
            "sources": [
                {"source_id": s.get("source_id"), "title": s.get("title"), "url": s.get("url")}
                for s in self.provenance.get("sources", [])
            ],
        }


@dataclass(frozen=True)
class KnowledgeBase:
    kb_id: str
    kb_version: str
    digest_sha256: str
    file_digests: dict[str, str]
    items: dict[str, dict[str, Any]]
    item_files: dict[str, str]
    authority_order: tuple[str, ...]
    gpa_policy: GradingPolicy | None = None
    stacks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def item(self, item_id: str) -> dict[str, Any]:
        try:
            return self.items[item_id]
        except KeyError as error:
            raise KnowledgeBaseError(f"unknown knowledge item '{item_id}'") from error

    def item_version(self, item_id: str) -> str:
        return f"{self.item_files[item_id]}@{self.items[item_id]['_file_version']}"

    def summary(self) -> dict[str, Any]:
        return {
            "kb_id": self.kb_id,
            "kb_version": self.kb_version,
            "kb_digest_sha256": self.digest_sha256,
            "item_count": len(self.items),
            "files": dict(sorted(self.file_digests.items())),
            "authority_order": list(self.authority_order),
            "stacks": {
                stack_id: stack.get("hybrid_generator_status") for stack_id, stack in sorted(self.stacks.items())
            },
            "gpa_policy": self.gpa_policy.disclosure() if self.gpa_policy else None,
        }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KnowledgeBaseError(f"{path.name}: unreadable or invalid JSON ({error})") from error


def _load_policy(item: dict[str, Any]) -> GradingPolicy:
    required = ("policy_id", "policy_version", "authority_status", "grades", "provenance", "scale_maximum")
    missing = [key for key in required if key not in item]
    if missing:
        raise KnowledgeBaseError(f"grading policy missing fields {missing}")
    if item["authority_status"] not in POLICY_AUTHORITY_STATUSES:
        raise KnowledgeBaseError(f"grading policy authority_status '{item['authority_status']}' is not recognized")
    if not item["provenance"].get("sources"):
        raise KnowledgeBaseError("grading policy must record at least one provenance source")
    scale_max = float(item["scale_maximum"])
    grades: list[GradeEntry] = []
    seen: set[str] = set()
    for raw in item["grades"]:
        grade = str(raw.get("grade", "")).strip()
        if not grade or grade in seen:
            raise KnowledgeBaseError(f"grading policy has a blank or duplicate grade '{grade}'")
        seen.add(grade)
        point = float(raw["grade_point"])
        tenths = round(point * 10)
        if abs(tenths - point * 10) > 1e-9:
            raise KnowledgeBaseError(f"grade '{grade}' point {point} needs more than one decimal place")
        if not 0 <= point <= scale_max:
            raise KnowledgeBaseError(f"grade '{grade}' point {point} is outside 0..{scale_max}")
        if int(raw["marks_min"]) > int(raw["marks_max"]):
            raise KnowledgeBaseError(f"grade '{grade}' has an inverted marks range")
        grades.append(
            GradeEntry(grade, point, tenths, int(raw["marks_min"]), int(raw["marks_max"]), bool(raw["counts_as_pass"]))
        )
    if not grades:
        raise KnowledgeBaseError("grading policy has no grades")
    return GradingPolicy(
        item_id=item["item_id"],
        policy_id=item["policy_id"],
        policy_version=item["policy_version"],
        policy_name=item.get("policy_name", item["policy_id"]),
        authority_status=item["authority_status"],
        authority_status_reason=item.get("authority_status_reason", ""),
        requires_explicit_acceptance=bool(item.get("requires_explicit_acceptance", True))
        or item["authority_status"] == "SAMPLE_RESEARCH_POLICY",
        institution=item.get("institution", ""),
        scale_maximum=scale_max,
        grades=tuple(grades),
        provenance=item["provenance"],
        known_unverified_aspects=tuple(item.get("known_unverified_aspects", ())),
        digest_sha256=canonical_sha256({k: v for k, v in item.items() if not k.startswith("_")}),
    )


def load_knowledge_base(root: Path = KB_ROOT) -> KnowledgeBase:
    """Load and strictly validate the Knowledge Base rooted at ``root``."""
    manifest = _read_json(root / "manifest.json")
    for key in ("kb_id", "kb_version", "files", "authority_order"):
        if key not in manifest:
            raise KnowledgeBaseError(f"manifest.json missing '{key}'")
    file_digests: dict[str, str] = {}
    items: dict[str, dict[str, Any]] = {}
    item_files: dict[str, str] = {}
    for relative in manifest["files"]:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise KnowledgeBaseError(f"KB file '{relative}' escapes the KB root")
        document = _read_json(path)
        if not isinstance(document, dict) or "version" not in document or not isinstance(document.get("items"), list):
            raise KnowledgeBaseError(f"{relative}: must contain 'version' and an 'items' list")
        file_digests[relative] = canonical_sha256(document)
        for item in document["items"]:
            item_id = item.get("item_id") if isinstance(item, dict) else None
            if not item_id:
                raise KnowledgeBaseError(f"{relative}: every item needs an item_id")
            if item_id in items:
                raise KnowledgeBaseError(f"{relative}: duplicate item_id '{item_id}'")
            items[item_id] = {**item, "_file_version": document["version"]}
            item_files[item_id] = relative
    policy = _load_policy(items["KB-GPA-GRADE-SCALE"]) if "KB-GPA-GRADE-SCALE" in items else None
    stacks = {item["stack_id"]: item for item in items.values() if "stack_id" in item}
    digest = canonical_sha256({"manifest": manifest, "files": file_digests})
    return KnowledgeBase(
        kb_id=manifest["kb_id"],
        kb_version=manifest["kb_version"],
        digest_sha256=digest,
        file_digests=file_digests,
        items=items,
        item_files=item_files,
        authority_order=tuple(manifest["authority_order"]),
        gpa_policy=policy,
        stacks=stacks,
    )
