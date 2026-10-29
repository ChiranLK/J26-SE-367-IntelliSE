"""Prompt contracts for the backend modules an LLM may write instead of a template.

Everything in the notes is a Knowledge Base fact, an approved C1 constraint or an injected-dependency
contract. The LLM never supplies domain policy values: the grade table arrives through the injected
``gradingPolicy`` object, and numeric limits arrive as data.
"""

from __future__ import annotations

import json
from typing import Any

from intelise_c3.hybrid.gpa_spec import GpaSpec
from intelise_c3.hybrid.gpa_templates import constraint_payload
from intelise_c3.hybrid.knowledge_base import KnowledgeBase
from intelise_c3.hybrid.llm_gateway import BoundedModuleContext, InterfaceMethod
from intelise_c3.hybrid.llm_sandbox import BENCHMARK_VERSION

SERVICE_PATH = "backend/src/services/gpaCalculationService.js"
VALIDATION_PATH = "backend/src/validation/gpaRequestValidator.js"
#: module id -> (kind, class or function name, target path)
LLM_BACKEND_MODULES: dict[str, tuple[str, str, str]] = {
    "be.service": ("class", "GpaCalculationService", SERVICE_PATH),
    "be.validation": ("function", "validateGpaRequest", VALIDATION_PATH),
}


def service_contract_notes(kb: KnowledgeBase) -> str:
    rounding = kb.item("KB-GPA-ROUNDING")
    return "\n".join([
        "CONSTRUCTOR: new GpaCalculationService({ repository, gradingPolicy, clock, idGenerator }); clock() returns a Date; idGenerator() returns a string id.",
        "repository: async save(calculation) -> the saved calculation; async list() -> array. Call repository.save for every successful calculation and return its result; listHistory() returns await repository.list().",
        "gradingPolicy: gradePointTenths(grade) -> integer tenths (33 means 3.3) or null when the grade is unknown; metadata() -> { policyId, policyVersion, authorityStatus }.",
        "INPUT modules: array of { moduleCode: string, credits: integer, grade: string, countsTowardGpa: boolean } (UML ModuleResult; countsTowardGpa defaults to true).",
        "RESULT: { id, policyId, policyVersion, policyAuthorityStatus, totalCredits (integer, GPA-counted credits only), gpa (number), gpaText (string with exactly 2 decimals), weightedGradePoints (number), createdAt (ISO string from clock()), modules }.",
        "RESULT.modules has ONE entry per input module, counted or not, in input order: { moduleCode, credits, grade, gradePoint (number from gradingPolicy, e.g. 3.3), countsTowardGpa (boolean) }. The repository persists these into a table where every column, including gradePoint, is NOT NULL.",
        "FORMULA (KB-GPA-FORMULA): GPA = SUM(credits*gradePoint)/SUM(credits) over modules with countsTowardGpa !== false. Work in integer tenths so only the final division rounds.",
        f"ROUNDING (KB-GPA-ROUNDING): {rounding['decimal_places']} decimal places, {rounding['mode']}, computed with integer arithmetic (not toFixed on a float).",
        "ERRORS: throw new Error(message) with a .code property: UNKNOWN_GRADE (any module, counted or not, whose grade is not in the policy; never guess a value), REPEATED_MODULE_POLICY_UNDEFINED (same moduleCode twice, case-insensitive), ZERO_CREDIT_NOT_ALLOWED (counted module with credits <= 0 or not an integer), NO_GPA_CREDITS (no module counts toward GPA).",
        "The module must be dependency-free: no import statements, no require.",
    ])


def validation_contract_notes(spec: GpaSpec) -> str:
    limits = json.dumps(constraint_payload(spec), sort_keys=True)
    return "\n".join([
        "SIGNATURE: export function validateGpaRequest(body, gradingPolicy) -> { value, errors, review }. Synchronous and pure.",
        "gradingPolicy.gradePointTenths(grade) -> integer tenths, or null when the grade is not in the accepted policy.",
        "body: { modules: [ { moduleCode, credits, grade, countsTowardGpa? } ] } (UML ModuleResult).",
        f"LIMITS (approved C1 constraints, Knowledge Base defaults where C1 is silent; use exactly these values): {limits}",
        "RESULT: errors = hard validation failures; review = items a human must review. Every item is { index (position of the module, null for request-level problems), field, code, message }.",
        "value = { modules: [ { moduleCode (trimmed string), credits (number), grade (trimmed string), countsTowardGpa (boolean; true when absent) } ] }, or null when 'modules' itself is unusable.",
        "REQUEST LEVEL: 'modules' missing, not an array or empty -> error MODULES_REQUIRED (stop there). More than maxModules modules -> error TOO_MANY_MODULES (stop there).",
        "PER MODULE (report every problem you find): moduleCode: when required and blank -> MODULE_CODE_REQUIRED; otherwise longer than maxLength -> MODULE_CODE_TOO_LONG; otherwise, when a pattern is given and it does not match -> MODULE_CODE_PATTERN (at most one moduleCode error per module).",
        "credits: exactly 0 -> ZERO_CREDIT_NOT_ALLOWED (KB-GPA-ZERO-CREDIT); otherwise not an integer or outside min..max -> CREDITS_OUT_OF_RANGE.",
        "grade: missing or blank -> error GRADE_REQUIRED; present but unknown to gradingPolicy -> REVIEW item UNKNOWN_GRADE, never an error, never a guessed value (KB-GPA-UNKNOWN-GRADE).",
        "countsTowardGpa: present but not a boolean -> error COUNTS_TOWARD_GPA_BOOLEAN.",
        "The same moduleCode twice (case-insensitive) -> REVIEW item REPEATED_MODULE_POLICY_UNDEFINED on the repeated module (KB-GPA-REPEATED-MODULES).",
        "The module must be dependency-free: no import statements, no require.",
    ])


def attribute_slice(name: str, attributes: Any) -> str:
    lines = "\n".join(f"  +{a.name}: {a.type_name}" for a in attributes)
    return f"class {name} {{\n{lines}\n}}"


def module_context(
    *, module_id: str, rule_ids: tuple[str, ...], requirement_slices: tuple[dict[str, Any], ...], uml_slice: str,
    uml_version: str, stack_id: str, kb: KnowledgeBase, rule_set_digest: str, rag: dict[str, Any], rag_prompt: str,
    notes: str, target_path: str, name: str, kind: str, methods: tuple[InterfaceMethod, ...],
) -> BoundedModuleContext:
    return BoundedModuleContext(
        module_id=module_id, target_path=target_path, class_name=name, methods=methods,
        requirement_slices=requirement_slices, uml_slice=uml_slice, uml_version=uml_version, stack_id=stack_id,
        rule_ids=rule_ids, kb_digest=kb.digest_sha256, rule_set_digest=rule_set_digest, rag_prompt=rag_prompt,
        rag_digest=rag["context_digest_sha256"], contract_notes=notes, kind=kind, check_version=BENCHMARK_VERSION,
    )
