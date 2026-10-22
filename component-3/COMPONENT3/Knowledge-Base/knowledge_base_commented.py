"""Versioned, structured Knowledge Base of facts (not rules, not RAG).

The KB is loaded from ``component-3/knowledge-base``. Every file is validated,
every knowledge item has a stable ``item_id`` (used as a KNOWLEDGE_ITEM trace
node), and a canonical digest over the parsed JSON binds generation caches and
manifests to the exact facts used. Digests are computed over parsed JSON so a
CRLF checkout does not change them.
"""

from __future__ import annotations

# Import immutable data containers, JSON reading and path helpers.
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

# Import the Component 3 root and stable JSON hashing helper.
from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.generation.evidence import canonical_sha256

# KNOWLEDGE BASE LOCATION AND POLICY RULES
# Read all structured knowledge facts from this project folder.
KB_ROOT = COMPONENT_ROOT / "knowledge-base"

# Accept only clearly classified sample or client-approved grading policies.
POLICY_AUTHORITY_STATUSES = frozenset({"SAMPLE_RESEARCH_POLICY", "CLIENT_APPROVED_POLICY"})


class KnowledgeBaseError(ValueError):
    """Raised when the Knowledge Base is malformed or internally inconsistent."""


@dataclass(frozen=True)
class GradeEntry:
    """Store one validated grade, grade point, marks range and pass status."""

    # Keep the exact values used by GPA generation and validation.
    grade: str
    grade_point: float
    grade_point_tenths: int
    marks_min: int
    marks_max: int
    counts_as_pass: bool


@dataclass(frozen=True)
class GradingPolicy:
    """Store the complete versioned GPA grading policy and its provenance."""

    # Store policy identity, authority and institutional information.
    item_id: str
    policy_id: str
    policy_version: str
    policy_name: str
    authority_status: str
    authority_status_reason: str
    requires_explicit_acceptance: bool
    institution: str
    scale_maximum: float
    # Store the validated grade table and its source evidence.
    grades: tuple[GradeEntry, ...]
    provenance: dict[str, Any]
    known_unverified_aspects: tuple[str, ...]
    digest_sha256: str

    def grade_point_tenths(self, grade: str) -> int | None:
        # GRADE LOOKUP
        # Find the integer-tenths grade point used for exact GPA calculations.
        for entry in self.grades:
            if entry.grade == grade:
                return entry.grade_point_tenths
        # Return no value when the requested grade is not in this policy.
        return None

    def disclosure(self) -> dict[str, Any]:
        # POLICY DISCLOSURE
        # Return the safe policy identity and provenance shown in generated outputs.
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_name": self.policy_name,
            "authority_status": self.authority_status,
            "authority_status_reason": self.authority_status_reason,
            "institution": self.institution,
            "policy_digest_sha256": self.digest_sha256,
            "known_unverified_aspects": list(self.known_unverified_aspects),
            # Include source labels and URLs without changing the policy facts.
            "sources": [
                {"source_id": s.get("source_id"), "title": s.get("title"), "url": s.get("url")}
                for s in self.provenance.get("sources", [])
            ],
        }


@dataclass(frozen=True)
class KnowledgeBase:
    """Store all validated KB facts, versions, digests and stack information."""

    # Store the KB identity and integrity fingerprints.
    kb_id: str
    kb_version: str
    digest_sha256: str
    file_digests: dict[str, str]
    # Store every knowledge item and the file that supplied it.
    items: dict[str, dict[str, Any]]
    item_files: dict[str, str]
    authority_order: tuple[str, ...]
    # Expose important domain and technology facts in convenient structures.
    gpa_policy: GradingPolicy | None = None
    stacks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def item(self, item_id: str) -> dict[str, Any]:
        # KNOWLEDGE ITEM LOOKUP
        # Return one fact by its stable item id or report an unknown reference.
        try:
            return self.items[item_id]
        except KeyError as error:
            raise KnowledgeBaseError(f"unknown knowledge item '{item_id}'") from error

    def item_version(self, item_id: str) -> str:
        # Bind an item to both its source file and source-file version.
        return f"{self.item_files[item_id]}@{self.items[item_id]['_file_version']}"

    def summary(self) -> dict[str, Any]:
        # KNOWLEDGE BASE SUMMARY
        # Return safe metadata for the dashboard and generation manifest.
        return {
            "kb_id": self.kb_id,
            "kb_version": self.kb_version,
            "kb_digest_sha256": self.digest_sha256,
            "item_count": len(self.items),
            "files": dict(sorted(self.file_digests.items())),
            "authority_order": list(self.authority_order),
            # Show the generator implementation status of every known stack.
            "stacks": {
                stack_id: stack.get("hybrid_generator_status") for stack_id, stack in sorted(self.stacks.items())
            },
            "gpa_policy": self.gpa_policy.disclosure() if self.gpa_policy else None,
        }


def _read_json(path: Path) -> Any:
    # SAFE KNOWLEDGE FILE READING
    # Read UTF-8 JSON and convert file or syntax errors into one KB error type.
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KnowledgeBaseError(f"{path.name}: unreadable or invalid JSON ({error})") from error


def _load_policy(item: dict[str, Any]) -> GradingPolicy:
    # GPA GRADING POLICY VALIDATION
    # Require the identity, authority, grade table, provenance and maximum scale.
    required = ("policy_id", "policy_version", "authority_status", "grades", "provenance", "scale_maximum")

    # Reject a policy with missing mandatory fields.
    missing = [key for key in required if key not in item]
    if missing:
        raise KnowledgeBaseError(f"grading policy missing fields {missing}")
    # Reject an unrecognized policy authority classification.
    if item["authority_status"] not in POLICY_AUTHORITY_STATUSES:
        raise KnowledgeBaseError(f"grading policy authority_status '{item['authority_status']}' is not recognized")
    # Require at least one recorded provenance source.
    if not item["provenance"].get("sources"):
        raise KnowledgeBaseError("grading policy must record at least one provenance source")
    # Convert the policy maximum to the numeric value used for validation.
    scale_max = float(item["scale_maximum"])

    # Prepare the validated grade list and duplicate-grade tracker.
    grades: list[GradeEntry] = []
    seen: set[str] = set()
    # Validate every grade entry in the source policy.
    for raw in item["grades"]:
        # Normalize the grade label and reject blanks or duplicates.
        grade = str(raw.get("grade", "")).strip()
        if not grade or grade in seen:
            raise KnowledgeBaseError(f"grading policy has a blank or duplicate grade '{grade}'")
        seen.add(grade)
        # Convert the grade point and preserve it as exact integer tenths.
        point = float(raw["grade_point"])
        tenths = round(point * 10)
        # Reject a grade point requiring more than one decimal place.
        if abs(tenths - point * 10) > 1e-9:
            raise KnowledgeBaseError(f"grade '{grade}' point {point} needs more than one decimal place")
        # Reject a grade point outside the declared grading scale.
        if not 0 <= point <= scale_max:
            raise KnowledgeBaseError(f"grade '{grade}' point {point} is outside 0..{scale_max}")
        # Reject an invalid marks range whose minimum is above its maximum.
        if int(raw["marks_min"]) > int(raw["marks_max"]):
            raise KnowledgeBaseError(f"grade '{grade}' has an inverted marks range")
        # Save the validated grade entry.
        grades.append(
            GradeEntry(grade, point, tenths, int(raw["marks_min"]), int(raw["marks_max"]), bool(raw["counts_as_pass"]))
        )
    # Reject a policy that contains no usable grade entries.
    if not grades:
        raise KnowledgeBaseError("grading policy has no grades")
    # Return the normalized policy with a digest of its authoritative content.
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

    # KNOWLEDGE BASE LOADING PROCESS
    # Read the main manifest that lists every approved KB document.
    manifest = _read_json(root / "manifest.json")

    # Require the manifest identity, version, file list and authority order.
    for key in ("kb_id", "kb_version", "files", "authority_order"):
        if key not in manifest:
            raise KnowledgeBaseError(f"manifest.json missing '{key}'")
    # Prepare file hashes, knowledge items and item-to-file trace links.
    file_digests: dict[str, str] = {}
    items: dict[str, dict[str, Any]] = {}
    item_files: dict[str, str] = {}
    # Load every knowledge document declared by the manifest.
    for relative in manifest["files"]:
        # Resolve the file and stop path traversal outside the KB folder.
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise KnowledgeBaseError(f"KB file '{relative}' escapes the KB root")
        # Read the JSON knowledge document and validate its basic structure.
        document = _read_json(path)
        if not isinstance(document, dict) or "version" not in document or not isinstance(document.get("items"), list):
            raise KnowledgeBaseError(f"{relative}: must contain 'version' and an 'items' list")
        # Hash the parsed JSON so line-ending changes do not change evidence.
        file_digests[relative] = canonical_sha256(document)

        # Register every stable knowledge item from this document.
        for item in document["items"]:
            # Require a non-empty item id for traceability.
            item_id = item.get("item_id") if isinstance(item, dict) else None
            if not item_id:
                raise KnowledgeBaseError(f"{relative}: every item needs an item_id")
            # Reject duplicate knowledge identities across different files.
            if item_id in items:
                raise KnowledgeBaseError(f"{relative}: duplicate item_id '{item_id}'")
            # Save the fact together with its source-document version and path.
            items[item_id] = {**item, "_file_version": document["version"]}
            item_files[item_id] = relative

    # Build the strongly validated GPA policy when its knowledge item exists.
    policy = _load_policy(items["KB-GPA-GRADE-SCALE"]) if "KB-GPA-GRADE-SCALE" in items else None

    # Index all technology-stack facts by their stable stack id.
    stacks = {item["stack_id"]: item for item in items.values() if "stack_id" in item}

    # Bind the full KB manifest and all document hashes into one stable digest.
    digest = canonical_sha256({"manifest": manifest, "files": file_digests})

    # Return the complete validated Knowledge Base used by generation.
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
