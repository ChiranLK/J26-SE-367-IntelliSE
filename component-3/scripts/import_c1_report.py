"""Convert a Component 1 plain-text requirements report into C1ApprovedSRS JSON.

The real C1 export carries no approval information, so the default output is a
DRAFT package that /validate-input rejects. APPROVED is produced only when the
caller supplies the approval reference, the approver and the validation-report
reference explicitly; none of them is ever invented.

Usage:
    python scripts/import_c1_report.py REPORT.txt --project-id ID --srs-version V \\
        [--output c1.json]
    python scripts/import_c1_report.py REPORT.txt --project-id ID --srs-version V \\
        --approve --approval-ref REF --approved-by NAME --validation-report-ref REF
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from pydantic import ValidationError

from intelise_c3.contracts.provisional_input import (
    C1ApprovalStatus,
    C1ApprovedSRS,
    C1Requirement,
)
from intelise_c3.services.input_validation import SUPPORTED_INPUT_CONTRACT_VERSION

NOT_PROVIDED = "NOT_PROVIDED"

_HEADER = re.compile(r"^(?P<label>R\d+)\s*\|\s*(?P<category>FR|NFR)\b[^|]*\|\s*(?P<review>.+?)\s*$")
_REQUIREMENT_ID = re.compile(r"^Requirement ID:\s*(?P<id>\S+)\s*$")
_SECTION = re.compile(r"^[A-Z][A-Z ]+$")
_IGNORED_PREFIXES = (
    "Original model prediction:",
    "Evidence ",
    "Unclear points:",
    "No configured rule matched",
)


class ReportImportError(ValueError):
    """The report does not have the expected C1 plain-text structure."""


@dataclass(frozen=True)
class ReportRequirement:
    """One requirement block as written in the C1 report."""

    label: str
    category: str
    review_state: str
    text: str
    requirement_id: str


def parse_report(text: str) -> tuple[ReportRequirement, ...]:
    """Extract requirement blocks; IDs and text are kept verbatim."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "REQUIREMENTS")
    except StopIteration:
        raise ReportImportError("No 'REQUIREMENTS' section found in the report.") from None

    blocks: list[dict[str, str | None]] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        header = _HEADER.match(stripped)
        if header:
            blocks.append(
                {
                    "label": header["label"],
                    "category": header["category"],
                    "review_state": header["review"],
                    "text": None,
                    "id": None,
                }
            )
            continue
        if not blocks:
            continue
        id_match = _REQUIREMENT_ID.match(stripped)
        if id_match:
            blocks[-1]["id"] = id_match["id"]
        elif _SECTION.match(stripped):
            break  # next report section (e.g. SAVED DISCUSSION)
        elif blocks[-1]["text"] is None and not stripped.startswith(_IGNORED_PREFIXES):
            blocks[-1]["text"] = stripped

    if not blocks:
        raise ReportImportError("The REQUIREMENTS section contains no requirement headers.")

    requirements: list[ReportRequirement] = []
    for block in blocks:
        label = str(block["label"])
        if not block["text"]:
            raise ReportImportError(f"{label}: requirement text line is missing.")
        if not block["id"]:
            raise ReportImportError(f"{label}: 'Requirement ID:' line is missing.")
        requirements.append(
            ReportRequirement(
                label=label,
                category=str(block["category"]),
                review_state=str(block["review_state"]),
                text=str(block["text"]),
                requirement_id=str(block["id"]),
            )
        )

    for field in ("label", "requirement_id"):
        values = [getattr(item, field) for item in requirements]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ReportImportError(f"Duplicate {field}: {', '.join(duplicates)}.")
    return tuple(requirements)


def build_c1_document(
    requirements: tuple[ReportRequirement, ...],
    *,
    project_id: str,
    srs_version: str,
    approval_ref: str | None = None,
    validation_report_ref: str | None = None,
    approve: bool = False,
) -> C1ApprovedSRS:
    """Build the contract model; DRAFT unless ``approve`` is set."""
    state = C1ApprovalStatus.APPROVED if approve else C1ApprovalStatus.DRAFT
    return C1ApprovedSRS(
        contract_version=SUPPORTED_INPUT_CONTRACT_VERSION,
        project_id=project_id,
        srs_version=srs_version,
        approval_status=state,
        approval_provenance_ref=approval_ref if approve and approval_ref else NOT_PROVIDED,
        validation_report_ref=validation_report_ref or NOT_PROVIDED,
        requirements=tuple(
            C1Requirement(
                requirement_id=item.requirement_id, title=item.text, status=state
            )
            for item in requirements
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("report", type=Path, help="C1 plain-text report")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--srs-version", required=True)
    parser.add_argument("--output", type=Path, help="Write JSON here (default: stdout)")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approved-by")
    parser.add_argument("--validation-report-ref")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    approval_flags = {
        "--approval-ref": args.approval_ref,
        "--approved-by": args.approved_by,
    }
    if args.approve:
        missing = [
            name
            for name, value in {
                **approval_flags,
                "--validation-report-ref": args.validation_report_ref,
            }.items()
            if value is None or not value.strip()
        ]
        if missing:
            parser.error(
                "--approve requires explicit " + ", ".join(missing)
                + "; refusing to invent approval data."
            )
    elif any(value is not None for value in approval_flags.values()):
        parser.error("--approval-ref/--approved-by are only valid together with --approve.")

    try:
        text = args.report.read_text(encoding="utf-8-sig")
        requirements = parse_report(text)
        document = build_c1_document(
            requirements,
            project_id=args.project_id,
            srs_version=args.srs_version,
            approval_ref=args.approval_ref,
            validation_report_ref=args.validation_report_ref,
            approve=args.approve,
        )
    except (OSError, ReportImportError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    payload = json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(payload)

    functional = sum(item.category == "FR" for item in requirements)
    print(
        f"imported {len(requirements)} requirements ({functional} FR, "
        f"{len(requirements) - functional} NFR) as {document.approval_status.value}",
        file=sys.stderr,
    )
    if args.approve:
        # The provisional contract has no approver field; keep an audit trail on stderr.
        print(f"approved_by={args.approved_by!r} approval_ref={args.approval_ref!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
