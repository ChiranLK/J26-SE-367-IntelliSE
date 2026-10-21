"""Deterministic DesignContext -> behaviour spec and domain skeleton (Stage 0).

The behaviour generator is the explicit path for class designs that are not
entity-CRUD (calculators, workflows, rule engines). C3 derives only structure
from the accepted C2 class diagram: classes, ``extends``, enums, fields and
method signatures. Method behaviour is not inferable from UML, so it is left
as ``TODO`` markers for the local model to implement from the C1 requirements.
Nothing here executes generated code or invents design intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import (
    DesignContext,
    ParsedElementKind,
    Visibility,
)

BEHAVIOUR_SPEC_POLICY_VERSION = "C3_BEHAVIOUR_SPEC_POLICY_V0"
FACADE_RULE = "FACADE_ENTRY_POINT_V1"
TODO_MARKER = "TODO: implement"

_JS_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_RESERVED = frozenset(
    """break case catch class const continue debugger default delete do else enum export
    extends false finally for function if import in instanceof new null return super switch
    this throw true try typeof var void while with yield let static await implements package
    protected interface private public constructor prototype""".split()
)
_NUMBER_TYPES = {"double", "float", "int", "integer", "long", "short", "decimal", "number", "byte"}
_STRING_TYPES = {"string", "char", "text", "uuid"}
_BOOLEAN_TYPES = {"bool", "boolean"}


@dataclass(frozen=True)
class BehaviourParam:
    name: str
    type_name: str
    kind: str  # NUMBER | STRING | BOOLEAN | ENUM | CLASS | TEXT


@dataclass(frozen=True)
class BehaviourMethod:
    name: str
    params: tuple[BehaviourParam, ...]
    return_type: str | None
    public: bool


@dataclass(frozen=True)
class BehaviourField:
    name: str
    type_name: str
    kind: str


@dataclass(frozen=True)
class BehaviourClass:
    name: str
    uml_id: str
    kind: str  # CLASS | ABSTRACT | ENUM
    base: str | None
    fields: tuple[BehaviourField, ...]
    methods: tuple[BehaviourMethod, ...]
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class BehaviourSpec:
    project_id: str
    facade: str
    facade_rule: str
    classes: tuple[BehaviourClass, ...]
    requirements: tuple[dict, ...]
    anchors: tuple[dict, ...]
    relationships: tuple[dict, ...]
    diagnostics: tuple[str, ...] = field(default=())

    def by_name(self) -> dict[str, BehaviourClass]:
        return {item.name: item for item in self.classes}

    def concrete_subtypes(self, type_name: str) -> tuple[str, ...]:
        """Concrete classes assignable to ``type_name`` (itself and descendants)."""
        classes = self.by_name()
        result = []
        for item in self.classes:
            if item.kind != "CLASS":
                continue
            current: str | None = item.name
            while current is not None:
                if current == type_name:
                    result.append(item.name)
                    break
                current = classes[current].base if current in classes else None
        return tuple(result)

    def probe_plan(self) -> tuple[dict, ...]:
        """User-style call sequence derived only from the facade's declared method order.

        Declared order, re-entering the last primitive-input method before each later
        no-argument call (e.g. enter, choose, enter, compute). Sample values are fixed;
        the plan carries no expected results.
        """
        facade = self.by_name()[self.facade]
        numbers = (12, 5, 7, 3, 9, 4)
        counter = 0

        def sample(param: BehaviourParam):
            nonlocal counter
            if param.kind == "NUMBER":
                value = numbers[counter % len(numbers)]
                counter += 1
                return value
            if param.kind == "BOOLEAN":
                return True
            if param.kind in {"ENUM", "CLASS"}:
                choices = self._choices(param)
                return choices[0] if choices else ""
            return "sample"

        plan: list[dict] = []
        last_input: BehaviourMethod | None = None
        public = [m for m in facade.methods if m.public]
        for index, method in enumerate(public):
            if not method.params and index > 0 and last_input is not None:
                plan.append({"method": last_input.name, "args": [sample(p) for p in last_input.params]})
            plan.append({"method": method.name, "args": [sample(p) for p in method.params]})
            if method.params and all(p.kind in {"NUMBER", "STRING"} for p in method.params):
                last_input = method
        return tuple(plan)

    def as_json(self) -> dict:
        return {
            "spec_policy_version": BEHAVIOUR_SPEC_POLICY_VERSION,
            "project_id": self.project_id,
            "facade": self.facade,
            "facade_rule": self.facade_rule,
            "probe_plan": list(self.probe_plan()),
            "classes": [
                {
                    "name": item.name,
                    "uml_id": item.uml_id,
                    "kind": item.kind,
                    "base": item.base,
                    "fields": [{"name": f.name, "type": f.type_name, "kind": f.kind} for f in item.fields],
                    "methods": [
                        {
                            "name": m.name,
                            "public": m.public,
                            "return_type": m.return_type,
                            "params": [
                                {
                                    "name": p.name,
                                    "type": p.type_name,
                                    "kind": p.kind,
                                    "choices": list(self._choices(p)),
                                }
                                for p in m.params
                            ],
                        }
                        for m in item.methods
                    ],
                    "values": list(item.values),
                }
                for item in self.classes
            ],
            "requirements": list(self.requirements),
            "anchors": list(self.anchors),
            "relationships": list(self.relationships),
            "diagnostics": list(self.diagnostics),
        }

    def _choices(self, param: BehaviourParam) -> tuple[str, ...]:
        if param.kind == "ENUM":
            return self.by_name()[param.type_name].values
        if param.kind == "CLASS":
            return self.concrete_subtypes(param.type_name)
        return ()


def _fail(code: str, field_name: str, message: str) -> None:
    raise ApplicationError(
        [ErrorDetail(code=code, field=field_name, message=message)],
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def _check_identifier(name: str, field_name: str) -> None:
    if not _JS_IDENTIFIER.match(name) or name in _RESERVED:
        _fail(
            "UNSUPPORTED_BEHAVIOUR_IDENTIFIER",
            field_name,
            f"'{name}' is not a safe JavaScript identifier for generated code.",
        )


def _reachable_counts(design: DesignContext) -> dict[str, int]:
    """Number of other classes each class can reach by following non-inheritance relationships."""
    edges: dict[str, set[str]] = {}
    for rel in design.relationships:
        if rel.relationship_type != "INHERITANCE":
            edges.setdefault(rel.source_class, set()).add(rel.target_class)
    counts: dict[str, int] = {}
    for start in edges:
        seen: set[str] = set()
        stack = list(edges[start])
        while stack:
            current = stack.pop()
            if current in seen or current == start:
                continue
            seen.add(current)
            stack.extend(edges.get(current, ()))
        counts[start] = len(seen)
    return counts


def build_behaviour_spec(design: DesignContext, facade: str | None = None) -> BehaviourSpec:
    """Derive structure only; fail closed on anything that cannot be rendered faithfully."""
    if not design.classes:
        _fail("MISSING_BEHAVIOUR_CLASSES", "design_context.classes", "The design has no parsed classes.")
    names = [item.name for item in design.classes]
    if len(set(names)) != len(names):
        _fail("AMBIGUOUS_BEHAVIOUR_CLASS", "design_context.classes", "Class names must be unique.")
    enums = {item.name for item in design.classes if item.kind is ParsedElementKind.ENUM}
    known = set(names)

    parents: dict[str, str] = {}
    for rel in design.relationships:
        if rel.relationship_type == "INHERITANCE":
            # PlantUML "Parent <|-- Child": source is the parent.
            parent, child = rel.source_class, rel.target_class
            if child in parents and parents[child] != parent:
                _fail(
                    "UNSUPPORTED_MULTIPLE_INHERITANCE",
                    f"design_context.relationships.{rel.source_uml_id}",
                    f"'{child}' extends more than one class; JavaScript classes allow one base.",
                )
            if parent not in known or child not in known:
                _fail(
                    "UNKNOWN_BEHAVIOUR_CLASS",
                    f"design_context.relationships.{rel.source_uml_id}",
                    "An inheritance relationship names a class that is not declared.",
                )
            parents[child] = parent
    for start in parents:
        seen, current = set(), start
        while current in parents:
            if current in seen:
                _fail("CYCLIC_INHERITANCE", "design_context.relationships", "Inheritance contains a cycle.")
            seen.add(current)
            current = parents[current]

    def kind_of(type_name: str) -> str:
        lowered = type_name.strip().casefold()
        if lowered in _NUMBER_TYPES:
            return "NUMBER"
        if lowered in _STRING_TYPES:
            return "STRING"
        if lowered in _BOOLEAN_TYPES:
            return "BOOLEAN"
        if type_name in enums:
            return "ENUM"
        if type_name in known:
            return "CLASS"
        return "TEXT"

    diagnostics: list[str] = []
    classes: list[BehaviourClass] = []
    for item in design.classes:
        _check_identifier(item.name, f"design_context.classes.{item.name}")
        if item.kind is ParsedElementKind.ENUM:
            if not item.values:
                _fail("EMPTY_BEHAVIOUR_ENUM", f"design_context.classes.{item.name}", "Enums need at least one value.")
            for value in item.values:
                _check_identifier(value, f"design_context.classes.{item.name}.values")
            classes.append(BehaviourClass(item.name, item.source_uml_id, "ENUM", None, (), (), tuple(item.values)))
            continue
        fields = []
        for attribute in item.attributes:
            _check_identifier(attribute.name, f"design_context.classes.{item.name}.attributes")
            fields.append(BehaviourField(attribute.name, attribute.type_name, kind_of(attribute.type_name)))
        methods = []
        for method in item.methods:
            _check_identifier(method.name, f"design_context.classes.{item.name}.methods")
            params = []
            for parameter in method.parameters:
                _check_identifier(parameter.name, f"design_context.classes.{item.name}.{method.name}")
                kind = kind_of(parameter.type_name)
                if kind == "TEXT":
                    diagnostics.append(
                        f"PARAMETER_TYPE_AS_TEXT: {item.name}.{method.name}({parameter.name}: {parameter.type_name})"
                    )
                params.append(BehaviourParam(parameter.name, parameter.type_name, kind))
            methods.append(
                BehaviourMethod(method.name, tuple(params), method.return_type, method.visibility is Visibility.PUBLIC)
            )
        classes.append(
            BehaviourClass(
                item.name,
                item.source_uml_id,
                "ABSTRACT" if item.is_abstract else "CLASS",
                parents.get(item.name),
                tuple(fields),
                tuple(methods),
            )
        )

    classes = _add_association_fields(classes, design, diagnostics)
    ordered = _order_classes(classes)
    concrete = [item for item in ordered if item.kind == "CLASS"]
    if facade is not None:
        chosen = next((item for item in concrete if item.name == facade), None)
        if chosen is None:
            _fail("UNKNOWN_BEHAVIOUR_FACADE", "facade_class", f"'{facade}' is not a concrete class in the design.")
        rule = "FACADE_SELECTED_BY_RESEARCHER"
    else:
        candidates = [item for item in concrete if any(m.public for m in item.methods)]
        if not candidates:
            _fail(
                "MISSING_BEHAVIOUR_FACADE",
                "design_context.classes",
                "No concrete class declares a public method to drive the application.",
            )
        # The entry point is the class that drives the others: the one that reaches the most classes
        # through the diagram's relationships (a Service reaches its Repository, Policy and entities;
        # a Repository only reaches its entity). Ties fall back to the public-method count, then the name.
        reach = _reachable_counts(design)
        chosen = sorted(
            candidates,
            key=lambda item: (-reach.get(item.name, 0), -sum(m.public for m in item.methods), item.name),
        )[0]
        rule = FACADE_RULE

    # Anchors may target the diagram's per-class UML elements; resolve them by element name.
    class_ids = {item.source_uml_id: item.name for item in design.classes}
    for element in design.source_uml_elements:
        if element.name in known and element.uml_id not in class_ids:
            class_ids[element.uml_id] = element.name
    return BehaviourSpec(
        project_id=design.project_id,
        facade=chosen.name,
        facade_rule=rule,
        classes=tuple(ordered),
        requirements=tuple(
            {
                "requirement_id": r.requirement_id,
                "title": r.title,
                "requirement_type": r.requirement_type,
            }
            for r in design.requirements
        ),
        anchors=tuple(
            {
                "anchor_id": a.anchor_id,
                "requirement_id": a.requirement_id,
                "uml_id": a.uml_id,
                "class_name": class_ids.get(a.uml_id),
            }
            for a in design.requirement_uml_anchors
        ),
        relationships=tuple(
            {
                "source": rel.source_class,
                "target": rel.target_class,
                "type": rel.relationship_type,
                "label": rel.label,
                "source_multiplicity": rel.source_multiplicity,
                "target_multiplicity": rel.target_multiplicity,
            }
            for rel in design.relationships
        ),
        diagnostics=tuple(diagnostics),
    )


_MANY = {"*", "0..*", "1..*", "many"}


def _add_association_fields(
    classes: list[BehaviourClass], design: DesignContext, diagnostics: list[str]
) -> list[BehaviourClass]:
    """Turn class-to-class associations/compositions into reference fields (structure only).

    ``A "1" -- "1" B`` gives ``A.b``; a target multiplicity of ``*``/``0..*``/``1..*`` gives an
    array field ``A.bs``. Skipped when ``A`` already has an attribute of type ``B``, when ``B``
    is an enum (enum values are normally declared as attributes), or when the name exists.
    """
    by_name = {item.name: item for item in classes}
    extra: dict[str, list[BehaviourField]] = {}
    for rel in design.relationships:
        if rel.relationship_type not in {"ASSOCIATION", "COMPOSITION", "AGGREGATION"}:
            continue
        owner, target = by_name.get(rel.source_class), by_name.get(rel.target_class)
        if owner is None or target is None or owner.kind == "ENUM" or target.kind == "ENUM":
            continue
        if any(f.type_name == target.name for f in owner.fields):
            continue
        many = (rel.target_multiplicity or "").strip() in _MANY
        name = target.name[0].lower() + target.name[1:] + ("s" if many else "")
        existing = {f.name for f in owner.fields} | {f.name for f in extra.get(owner.name, [])}
        if name in existing or not _JS_IDENTIFIER.match(name) or name in _RESERVED:
            continue
        extra.setdefault(owner.name, []).append(
            BehaviourField(name, f"{target.name}[]" if many else target.name, "ARRAY" if many else "CLASS_REF")
        )
        diagnostics.append(
            f"ASSOCIATION_FIELD: {owner.name}.{name} from '{rel.source_class} {rel.connector} {rel.target_class}'"
        )
    return [
        BehaviourClass(c.name, c.uml_id, c.kind, c.base, c.fields + tuple(extra.get(c.name, [])), c.methods, c.values)
        for c in classes
    ]


def _order_classes(classes: list[BehaviourClass]) -> list[BehaviourClass]:
    """Enums first, then every base class before its subclasses (stable otherwise)."""
    by_name = {item.name: item for item in classes}
    ordered: list[BehaviourClass] = [item for item in classes if item.kind == "ENUM"]
    placed = {item.name for item in ordered}

    def place(item: BehaviourClass) -> None:
        if item.name in placed:
            return
        if item.base and item.base in by_name:
            place(by_name[item.base])
        ordered.append(item)
        placed.add(item.name)

    for item in classes:
        place(item)
    return ordered


def _default_value(spec_classes: dict[str, BehaviourClass], owner: str, f: BehaviourField) -> str:
    if f.kind == "NUMBER":
        return "0"
    if f.kind in {"STRING", "TEXT"}:
        return '""'
    if f.kind == "BOOLEAN":
        return "false"
    if f.kind == "ENUM":
        return f"{f.type_name}.{spec_classes[f.type_name].values[0]}"
    if f.kind == "ARRAY":
        return "[]"
    if f.kind == "CLASS_REF":
        return "null"
    target = spec_classes.get(f.type_name)
    if target is not None and target.kind == "CLASS" and target.name != owner:
        return f"new {target.name}()"
    return "null"


MODULE_HEADER = (
    "// Generated by InteliSE C3 behaviour generator (Stage 0) from the accepted C2 class diagram.\n"
    "// Structure is deterministic; method bodies are written by the local model from C1 requirements.\n"
)


def render_class_block(spec: BehaviourSpec, item: BehaviourClass) -> str:
    """One deterministic top-level block: an enum constant or a class with TODO method bodies."""
    classes = spec.by_name()
    if item.kind == "ENUM":
        members = ", ".join(f'{value}: "{value}"' for value in item.values)
        return f"export const {item.name} = Object.freeze({{ {members} }});\n"
    lines = [f"export class {item.name}" + (f" extends {item.base}" if item.base else "") + " {"]
    lines.append("  constructor() {")
    if item.base:
        lines.append("    super();")
    for f in item.fields:
        lines.append(f"    this.{f.name} = {_default_value(classes, item.name, f)};")
    lines.append("  }")
    for method in item.methods:
        params = ", ".join(p.name for p in method.params)
        lines.append("")
        lines.append(f"  {method.name}({params}) {{")
        if item.kind == "ABSTRACT":
            lines.append(f'    throw new Error("Abstract method {item.name}.{method.name}");')
        else:
            lines.append(f'    throw new Error("{TODO_MARKER} {item.name}.{method.name}");')
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def assemble_module(spec: BehaviourSpec, blocks: dict[str, str]) -> str:
    """Module text in spec order, using accepted blocks where present and skeleton blocks otherwise."""
    parts = [MODULE_HEADER]
    for item in spec.classes:
        parts.append(blocks.get(item.name) or render_class_block(spec, item))
    return "\n".join(parts)


def render_domain_skeleton(spec: BehaviourSpec) -> str:
    """Deterministic module with every UML class and signature; bodies are TODO markers."""
    return assemble_module(spec, {})


def api_summary(spec: BehaviourSpec, exclude: str | None = None) -> str:
    """Deterministic list of what exists on each class, so the model only calls real members."""
    lines = []
    for item in spec.classes:
        if item.name == exclude:
            continue
        if item.kind == "ENUM":
            lines.append(f"- {item.name}: enum with values {', '.join(item.name + '.' + v for v in item.values)}")
            continue
        fields = ", ".join(f"{f.name} ({f.type_name})" for f in item.fields) or "none"
        methods = ", ".join(
            f"{m.name}({', '.join(p.name + ': ' + p.type_name for p in m.params)})"
            + (f" returns {m.return_type}" if m.return_type and m.return_type != "void" else "")
            for m in item.methods
        ) or "none"
        kind = "abstract class" if item.kind == "ABSTRACT" else "class"
        base = f" extends {item.base}" if item.base else ""
        lines.append(f"- {kind} {item.name}{base}: fields {fields}; methods {methods}")
    return "\n".join(lines)
