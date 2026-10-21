"""Deterministic DesignContext to CrudApplicationSpec translation."""

from __future__ import annotations

import re

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.crud_spec import (
    CrudApplicationSpec,
    CrudEntitySpec,
    CrudFieldSpec,
    CrudOperation,
    CrudScalarType,
)
from intelise_c3.domain.design_context import (
    DesignContext,
    ParsedClass,
    ParsedElementKind,
)

CRUD_SPEC_POLICY_VERSION = "C3_CRUD_SPEC_POLICY_V1"

_JS_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_GENERIC_PROJECT_TOKENS = {"project", "mvp", "app", "application"}
_ALL_OPERATIONS = (
    CrudOperation.LIST,
    CrudOperation.CREATE,
    CrudOperation.UPDATE,
    CrudOperation.DELETE,
)
_SCALAR_TYPES = {
    "string": CrudScalarType.STRING,
    "text": CrudScalarType.STRING,
    "uuid": CrudScalarType.STRING,
    "int": CrudScalarType.INTEGER,
    "integer": CrudScalarType.INTEGER,
    "long": CrudScalarType.INTEGER,
    "short": CrudScalarType.INTEGER,
    "number": CrudScalarType.NUMBER,
    "float": CrudScalarType.NUMBER,
    "double": CrudScalarType.NUMBER,
    "decimal": CrudScalarType.NUMBER,
    "bool": CrudScalarType.BOOLEAN,
    "boolean": CrudScalarType.BOOLEAN,
    "date": CrudScalarType.DATE,
    "localdate": CrudScalarType.DATE,
}


class CrudApplicationSpecBuilder:
    """Build the narrow supported CRUD profile without inventing design intent."""

    def build(self, design: DesignContext) -> CrudApplicationSpec:
        classes = {item.name: item for item in design.classes}
        if len(classes) != len(design.classes):
            self._fail(
                "AMBIGUOUS_CRUD_CLASS",
                "design_context.classes",
                "CRUD generation requires unique class names.",
            )

        for item in design.classes:
            if item.is_abstract or item.kind is not ParsedElementKind.CLASS:
                declared = "enum" if item.kind is ParsedElementKind.ENUM else "abstract class"
                self._fail(
                    "UNSUPPORTED_CRUD_CLASS_KIND",
                    f"design_context.classes.{item.name}",
                    (
                        f"Stage 1 CRUD generation supports only concrete classes; "
                        f"'{item.name}' is declared as an {declared}."
                    ),
                )

        persists = []
        uses = []
        for relationship in design.relationships:
            label = (relationship.label or "").strip().casefold()
            if label == "persists":
                persists.append(relationship)
            elif label == "uses":
                uses.append(relationship)
            else:
                self._fail(
                    "UNSUPPORTED_CRUD_RELATIONSHIP",
                    f"design_context.relationships.{relationship.source_uml_id}",
                    (
                        "Stage 1 supports only explicit Service -> Repository 'uses' "
                        "and Repository -> Entity 'persists' relationships; "
                        f"'{relationship.source_class} {relationship.connector} "
                        f"{relationship.target_class}' is unsupported."
                    ),
                )

        if not persists:
            self._fail(
                "MISSING_CRUD_PERSISTENCE_EVIDENCE",
                "design_context.relationships",
                "At least one explicit Repository -> Entity 'persists' relationship is required.",
            )

        entity_to_repository: dict[str, str] = {}
        for relationship in persists:
            if relationship.target_class in entity_to_repository:
                self._fail(
                    "AMBIGUOUS_CRUD_REPOSITORY",
                    "design_context.relationships",
                    f"Entity '{relationship.target_class}' has more than one repository.",
                )
            entity_to_repository[relationship.target_class] = relationship.source_class

        repository_to_service: dict[str, str] = {}
        for relationship in uses:
            if relationship.target_class in repository_to_service:
                self._fail(
                    "AMBIGUOUS_CRUD_SERVICE",
                    "design_context.relationships",
                    f"Repository '{relationship.target_class}' has more than one service.",
                )
            repository_to_service[relationship.target_class] = relationship.source_class

        entity_names = set(entity_to_repository)
        repository_names = set(entity_to_repository.values())
        service_names = set(repository_to_service.values())
        classified = entity_names | repository_names | service_names
        unclassified = set(classes) - classified
        if unclassified:
            self._fail(
                "AMBIGUOUS_CRUD_CLASS_ROLE",
                "design_context.classes",
                "Every class must participate in one supported CRUD boundary; "
                "unclassified classes: " + ", ".join(sorted(unclassified)) + ".",
            )

        requirement_matches = self._match_requirements(design, entity_names)
        entities: list[CrudEntitySpec] = []
        for parsed_class in design.classes:
            if parsed_class.name not in entity_names:
                continue
            repository_name = entity_to_repository[parsed_class.name]
            service_name = repository_to_service.get(repository_name)
            if service_name is None:
                self._fail(
                    "MISSING_CRUD_SERVICE_EVIDENCE",
                    "design_context.relationships",
                    f"Repository '{repository_name}' has no explicit service 'uses' relationship.",
                )
            entity = self._entity(
                design,
                parsed_class,
                classes[repository_name],
                classes[service_name],
                requirement_matches[parsed_class.name],
            )
            entities.append(entity)

        expected_roles = len(entities) * 3
        if len(classified) != expected_roles:
            self._fail(
                "AMBIGUOUS_CRUD_CLASS_ROLE",
                "design_context.classes",
                "Each independent entity must have its own service and repository classes.",
            )

        application_name, application_slug = self._application_identity(
            design.project_id, tuple(entities)
        )
        return CrudApplicationSpec(
            project_id=design.project_id,
            srs_version=design.srs_version,
            uml_version=design.uml_version,
            application_name=application_name,
            application_slug=application_slug,
            source_requirement_ids=tuple(
                requirement.requirement_id for requirement in design.requirements
            ),
            source_uml_ids=tuple(item.uml_id for item in design.source_uml_elements),
            source_ui_artifact_ids=tuple(item.ui_id for item in design.ui_artifacts),
            entities=tuple(entities),
        )

    def _entity(
        self,
        design: DesignContext,
        entity_class: ParsedClass,
        repository_class: ParsedClass,
        service_class: ParsedClass,
        requirements: tuple[str, ...],
    ) -> CrudEntitySpec:
        for parsed in (entity_class, repository_class, service_class):
            if not _JS_IDENTIFIER.fullmatch(parsed.name):
                self._fail(
                    "UNSUPPORTED_CRUD_IDENTIFIER",
                    f"design_context.classes.{parsed.name}",
                    f"Class name '{parsed.name}' is not a supported JavaScript identifier.",
                )
        if entity_class.methods or not entity_class.attributes:
            self._fail(
                "AMBIGUOUS_CRUD_ENTITY",
                f"design_context.classes.{entity_class.name}",
                "A Stage 1 entity must have attributes and no behavioral methods.",
            )
        if repository_class.attributes or service_class.attributes:
            self._fail(
                "AMBIGUOUS_CRUD_CLASS_ROLE",
                "design_context.classes",
                "Service and repository classes may define methods but not entity fields.",
            )

        service_operations = self._service_operations(service_class)
        if service_operations != set(_ALL_OPERATIONS):
            missing = sorted(item.value for item in set(_ALL_OPERATIONS) - service_operations)
            self._fail(
                "INCOMPLETE_CRUD_METHOD_EVIDENCE",
                f"design_context.classes.{service_class.name}",
                "The service must explicitly define list, create, update and delete/remove; "
                "missing: " + ", ".join(missing) + ".",
            )
        self._validate_repository_methods(repository_class)

        fields = tuple(self._field(entity_class, item.name, item.type_name) for item in entity_class.attributes)
        identifiers = [item for item in fields if item.name == "id"]
        if len(identifiers) != 1 or identifiers[0].scalar_type is not CrudScalarType.STRING:
            self._fail(
                "UNSUPPORTED_CRUD_IDENTIFIER_FIELD",
                f"design_context.classes.{entity_class.name}.attributes",
                "Each entity requires exactly one `id: String` attribute.",
            )
        if len(fields) < 2:
            self._fail(
                "INCOMPLETE_CRUD_ENTITY",
                f"design_context.classes.{entity_class.name}.attributes",
                "Each entity requires at least one mutable field in addition to id.",
            )

        requirement_operations = self._requirement_operations(design, requirements)
        if requirement_operations != set(_ALL_OPERATIONS):
            missing = sorted(item.value for item in set(_ALL_OPERATIONS) - requirement_operations)
            self._fail(
                "INCOMPLETE_CRUD_REQUIREMENT_EVIDENCE",
                "design_context.requirements",
                f"Entity '{entity_class.name}' lacks explicit requirement evidence for: "
                + ", ".join(missing)
                + ".",
            )
        entity_anchors = tuple(
            anchor
            for anchor in design.requirement_uml_anchors
            if anchor.requirement_id in requirements
            and anchor.uml_id == entity_class.source_uml_id
        )
        anchored_requirements = {anchor.requirement_id for anchor in entity_anchors}
        missing_anchor_requirements = tuple(
            requirement_id
            for requirement_id in requirements
            if requirement_id not in anchored_requirements
        )
        if missing_anchor_requirements:
            self._fail(
                "MISSING_ENTITY_DIAGRAM_CRUD_ANCHOR_EVIDENCE",
                "design_context.requirement_uml_anchors",
                (
                    f"Entity '{entity_class.name}' is missing an exact requirement-to-source "
                    "diagram UML anchor for: "
                    + ", ".join(missing_anchor_requirements)
                    + "."
                ),
            )
        anchors = tuple(anchor.anchor_id for anchor in entity_anchors)

        variable = entity_class.name[0].lower() + entity_class.name[1:]
        route = self._pluralize(self._kebab(entity_class.name))
        return CrudEntitySpec(
            source_uml_id=entity_class.source_uml_id,
            class_name=entity_class.name,
            variable_name=variable,
            plural_class_name=self._pluralize(entity_class.name),
            route_segment=route,
            table_name=route.replace("-", "_"),
            service_class_name=service_class.name,
            repository_class_name=repository_class.name,
            fields=fields,
            operations=_ALL_OPERATIONS,
            requirement_ids=requirements,
            design_anchor_ids=anchors,
        )

    def _field(self, entity: ParsedClass, name: str, type_name: str) -> CrudFieldSpec:
        if not _JS_IDENTIFIER.fullmatch(name):
            self._fail(
                "UNSUPPORTED_CRUD_IDENTIFIER",
                f"design_context.classes.{entity.name}.attributes.{name}",
                f"Field name '{name}' is not a supported JavaScript identifier.",
            )
        scalar = _SCALAR_TYPES.get(type_name.replace(" ", "").casefold())
        if scalar is None:
            self._fail(
                "UNSUPPORTED_CRUD_FIELD_TYPE",
                f"design_context.classes.{entity.name}.attributes.{name}",
                f"Field type '{type_name}' is outside the supported scalar profile.",
            )
        control = {
            CrudScalarType.STRING: "text",
            CrudScalarType.INTEGER: "number",
            CrudScalarType.NUMBER: "number",
            CrudScalarType.BOOLEAN: "checkbox",
            CrudScalarType.DATE: "date",
        }[scalar]
        return CrudFieldSpec(
            source_uml_id=entity.source_uml_id,
            name=name,
            scalar_type=scalar,
            generated=name == "id",
            input_control=control,
        )

    def _match_requirements(
        self, design: DesignContext, entity_names: set[str]
    ) -> dict[str, tuple[str, ...]]:
        matches: dict[str, list[str]] = {name: [] for name in entity_names}
        terms = {
            name: {
                self._human_words(name).casefold(),
                self._pluralize(self._human_words(name)).casefold(),
            }
            for name in entity_names
        }
        for requirement in design.requirements:
            title = " ".join(requirement.title.casefold().split())
            candidates = [
                name
                for name, names in terms.items()
                if any(re.search(rf"\b{re.escape(term)}\b", title) for term in names)
            ]
            if len(candidates) != 1:
                self._fail(
                    "AMBIGUOUS_CRUD_REQUIREMENT",
                    f"design_context.requirements.{requirement.requirement_id}",
                    (
                        "Each Stage 1 requirement must name exactly one generated entity; "
                        f"matched {len(candidates)} entities."
                    ),
                )
            matches[candidates[0]].append(requirement.requirement_id)
        return {name: tuple(values) for name, values in matches.items()}

    @staticmethod
    def _service_operations(parsed: ParsedClass) -> set[CrudOperation]:
        operations: set[CrudOperation] = set()
        supported = {
            "list": CrudOperation.LIST,
            "create": CrudOperation.CREATE,
            "update": CrudOperation.UPDATE,
            "delete": CrudOperation.DELETE,
            "remove": CrudOperation.DELETE,
        }
        for method in parsed.methods:
            operation = supported.get(method.name.casefold())
            if operation is None:
                CrudApplicationSpecBuilder._fail(
                    "UNSUPPORTED_CRUD_SERVICE_METHOD",
                    f"design_context.classes.{parsed.name}.methods.{method.name}",
                    f"Service method '{method.name}' is outside the supported CRUD profile.",
                )
            operations.add(operation)
        return operations

    @staticmethod
    def _validate_repository_methods(parsed: ParsedClass) -> None:
        actual = {method.name.casefold() for method in parsed.methods}
        delete_names = actual & {"delete", "remove"}
        required = {"list", "findbyid", "create", "update"}
        if not required.issubset(actual) or len(delete_names) != 1 or actual - required - delete_names:
            CrudApplicationSpecBuilder._fail(
                "UNSUPPORTED_CRUD_REPOSITORY_METHODS",
                f"design_context.classes.{parsed.name}.methods",
                "Repository methods must be exactly list, findById, create, update and delete/remove.",
            )

    @staticmethod
    def _requirement_operations(
        design: DesignContext, requirement_ids: tuple[str, ...]
    ) -> set[CrudOperation]:
        operations: set[CrudOperation] = set()
        by_id = {item.requirement_id: item for item in design.requirements}
        for requirement_id in requirement_ids:
            title = by_id[requirement_id].title.casefold()
            if re.search(r"\blist\b", title):
                operations.add(CrudOperation.LIST)
            if re.search(r"\bcreate\b", title):
                operations.add(CrudOperation.CREATE)
            if re.search(r"\bupdate\b", title):
                operations.add(CrudOperation.UPDATE)
            if re.search(r"\b(?:delete|remove)\b", title):
                operations.add(CrudOperation.DELETE)
            if not any(
                token in title
                for token in ("list", "create", "update", "delete", "remove", "repository", "persistence")
            ):
                CrudApplicationSpecBuilder._fail(
                    "AMBIGUOUS_CRUD_REQUIREMENT",
                    f"design_context.requirements.{requirement_id}",
                    "Requirement does not contain supported CRUD or repository evidence.",
                )
        return operations

    @staticmethod
    def _application_identity(
        project_id: str, entities: tuple[CrudEntitySpec, ...]
    ) -> tuple[str, str]:
        tokens = [
            token.casefold()
            for token in re.findall(r"[A-Za-z]+", project_id)
            if token.casefold() not in _GENERIC_PROJECT_TOKENS
        ]
        meaningful = []
        for token in tokens:
            if token not in meaningful:
                meaningful.append(token)
        if meaningful:
            base = " ".join(item.capitalize() for item in meaningful)
        else:
            base = " and ".join(item.class_name for item in entities)
        if not base.casefold().endswith("management"):
            base += " Management"
        return base, CrudApplicationSpecBuilder._kebab(base)

    @staticmethod
    def _human_words(value: str) -> str:
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ")

    @staticmethod
    def _kebab(value: str) -> str:
        words = CrudApplicationSpecBuilder._human_words(value)
        return re.sub(r"[^a-z0-9]+", "-", words.casefold()).strip("-")

    @staticmethod
    def _pluralize(value: str) -> str:
        if re.search(r"[^aeiou]y$", value, re.IGNORECASE):
            return value[:-1] + "ies"
        if re.search(r"(?:s|x|z|ch|sh)$", value, re.IGNORECASE):
            return value + "es"
        return value + "s"

    @staticmethod
    def _fail(code: str, field: str, message: str) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
