"""GPA domain-pack specification derived deterministically from accepted inputs + KB.

Precedence is explicit: approved C1 constraints override KB validation
defaults; the released C2 design defines entities and operations; grade points,
formula and edge-case behaviour come only from the accepted KB policy. Nothing
here is produced by RAG or an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from intelise_c3.contracts.hybrid import ConstraintKind, HybridInputPackage
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.hybrid.knowledge_base import GradingPolicy, KnowledgeBase


class GpaSpecError(ValueError):
    """The accepted inputs cannot be expressed by the GPA domain pack."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FieldConstraint:
    target: str
    required: bool = False
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    enum_from_policy: bool = False
    unique_within_request: bool = False
    sources: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value not in (None, False, ())} | {"target": self.target}


@dataclass(frozen=True)
class EntityField:
    name: str
    uml_type: str


@dataclass(frozen=True)
class GpaSpec:
    project_id: str
    srs_version: str
    uml_version: str
    policy: GradingPolicy
    rounding_decimal_places: int
    rounding_mode: str
    max_modules: int
    constraints: dict[str, FieldConstraint]
    module_result_fields: tuple[EntityField, ...]
    calculation_fields: tuple[EntityField, ...]
    persistence_required: bool
    requirement_ids: tuple[str, ...]
    ui_component_ids: tuple[str, ...] = field(default=())
    #: True when an LLM writes be.service and be.validation: the smoke test then runs the shared benchmark cases.
    llm_backend_logic: bool = False
    #: True when an LLM writes the UI files (App, components, client validation, styles) instead of templates.
    llm_frontend: bool = False
    #: True when the released design declares clearHistory() (service) and clear() (repository).
    clear_history: bool = False

    def constraint(self, target: str) -> FieldConstraint:
        return self.constraints.get(target, FieldConstraint(target=target))

    def fingerprint(self) -> str:
        return canonical_sha256(
            {
                "policy": self.policy.digest_sha256,
                "rounding": [self.rounding_decimal_places, self.rounding_mode],
                "constraints": {key: value.as_json() for key, value in sorted(self.constraints.items())},
                "persistence": self.persistence_required,
                "llm_backend_logic": self.llm_backend_logic,
                "llm_frontend": self.llm_frontend,
                **({"clear_history": True} if self.clear_history else {}),
            }
        )


def _merge(base: FieldConstraint, **changes: Any) -> FieldConstraint:
    values = {**base.__dict__, **changes}
    return FieldConstraint(**values)


def build_gpa_spec(package: HybridInputPackage, design: DesignContext, kb: KnowledgeBase) -> GpaSpec:
    policy = kb.gpa_policy
    if policy is None:
        raise GpaSpecError("GPA_POLICY_MISSING", "The Knowledge Base has no GPA grading policy; GPA generation is REVIEW_REQUIRED.")
    classes = {parsed.name: parsed for parsed in design.classes}
    for required in kb.item("KB-GPA-DOMAIN")["recognition"]["required_uml_classes"]:
        if required not in classes:
            raise GpaSpecError("GPA_DESIGN_INCOMPLETE", f"Released design lacks required GPA class {required}.")
    type_map = kb.item("KB-TYPE-MAP")["mappings"]
    for class_name in ("ModuleResult", "GpaCalculation"):
        for attribute in classes[class_name].attributes:
            if attribute.type_name not in type_map:
                raise GpaSpecError(
                    "UNSUPPORTED_UML_TYPE",
                    f"{class_name}.{attribute.name} has type {attribute.type_name}, which the KB type map does not cover.",
                )

    defaults = kb.item("KB-GPA-VALIDATION-DEFAULTS")
    constraints: dict[str, FieldConstraint] = {}
    for target, rule in defaults["defaults"].items():
        constraints[target] = FieldConstraint(
            target=target,
            required=bool(rule.get("required")),
            minimum=rule.get("min"),
            maximum=rule.get("max"),
            max_length=rule.get("max_length"),
            enum_from_policy=bool(rule.get("enum_from_policy")),
            sources=("KB-GPA-VALIDATION-DEFAULTS",),
        )
    for requirement in package.c1.requirements:
        for constraint in requirement.constraints:
            current = constraints.get(constraint.target, FieldConstraint(target=constraint.target))
            source = (f"{requirement.requirement_id}:{constraint.constraint_id}",)
            sources = current.sources + source
            if constraint.kind is ConstraintKind.REQUIRED:
                current = _merge(current, required=True, sources=sources)
            elif constraint.kind is ConstraintKind.RANGE:
                current = _merge(current, minimum=constraint.minimum, maximum=constraint.maximum, sources=sources)
            elif constraint.kind is ConstraintKind.PATTERN:
                current = _merge(current, pattern=constraint.pattern, sources=sources)
            elif constraint.kind is ConstraintKind.ENUM_FROM_POLICY:
                current = _merge(current, enum_from_policy=True, sources=sources)
            elif constraint.kind is ConstraintKind.UNIQUE_WITHIN_REQUEST:
                current = _merge(current, unique_within_request=True, sources=sources)
            constraints[constraint.target] = current

    rounding = kb.item("KB-GPA-ROUNDING")
    repository_anchored = {
        anchor.requirement_id
        for anchor in package.c2.requirement_uml_anchors
        if anchor.uml_element.endswith("Repository")
    }
    persistence_required = bool(repository_anchored) and "GpaCalculationRepository" in classes
    clear_history = "clearHistory" in {method.name for method in classes["GpaCalculationService"].methods}
    if clear_history:
        if not persistence_required:
            raise GpaSpecError("CLEAR_HISTORY_REQUIRES_PERSISTENCE", "The design declares clearHistory() but no requirement anchors a repository.")
        if "clear" not in {method.name for method in classes["GpaCalculationRepository"].methods}:
            raise GpaSpecError("CLEAR_HISTORY_DESIGN_INCOMPLETE", "GpaCalculationService.clearHistory() needs GpaCalculationRepository.clear() in the released design.")
    return GpaSpec(
        project_id=package.c1.project_id,
        srs_version=package.c1.srs_version,
        uml_version=package.c2.uml_version,
        policy=policy,
        rounding_decimal_places=int(rounding["decimal_places"]),
        rounding_mode=rounding["mode"],
        max_modules=int(defaults["max_modules_per_calculation"]),
        constraints=constraints,
        module_result_fields=tuple(EntityField(a.name, a.type_name) for a in classes["ModuleResult"].attributes),
        calculation_fields=tuple(EntityField(a.name, a.type_name) for a in classes["GpaCalculation"].attributes),
        persistence_required=persistence_required,
        clear_history=clear_history,
        requirement_ids=tuple(requirement.requirement_id for requirement in package.c1.requirements),
        ui_component_ids=tuple(
            component.component_id for screen in package.c2.ui_specification for component in screen.components
        ),
    )
