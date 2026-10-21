"""Member-level Requirement -> API / test-seam linking.

The released C2 design anchors a requirement to a UML *class*. Linking every API operation and test seam of a class to
every requirement of that class over-links: ``GpaCalculationService`` hosts calculate, listHistory and clearHistory, so
"calculate the GPA" would also appear to need "clear history". An API operation or test seam therefore names the UML
members (methods or attributes) it exercises. A member belongs to a requirement when its class is anchored to that
requirement AND the requirement statement uses the member's words. A member whose words appear in no statement of its
class falls back to the class-level anchors, so a link is never dropped for lack of wording.

Deterministic string matching only: no model and no application-specific word list.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z]+")


def _words(text: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)) if len(word) >= 3]


def _related(left: str, right: str) -> bool:
    length = 0
    while length < len(left) and length < len(right) and left[length] == right[length]:
        length += 1
    return length >= 4 or (length >= 3 and length == min(len(left), len(right)))


def member_matches(statement: str, member: str) -> bool:
    """True when the requirement statement uses a word of the member name (``clearHistory`` -> clear, history)."""
    statement_words = set(_words(statement))
    return any(_related(word, other) for word in _words(member) for other in statement_words)


def requirement_links(
    classes: tuple[str, ...],
    members: tuple[str, ...],
    anchors_by_class: dict[str, set[str]],
    statements: dict[str, str],
) -> dict[str, str]:
    """Requirement id -> why it is linked, for one API operation or test seam."""
    links: dict[str, str] = {}
    for name in classes:
        for requirement_id in anchors_by_class.get(name, ()):
            links.setdefault(requirement_id, f"class {name}")
    for member in members:
        owner, _, member_name = member.partition(".")
        candidates = sorted(anchors_by_class.get(owner, ()))
        matched = [r for r in candidates if member_matches(statements.get(r, ""), member_name)]
        for requirement_id in matched or candidates:
            reason = f"{member} used in the requirement" if matched else f"class {owner} (no requirement names {member})"
            links.setdefault(requirement_id, reason)
    return links
