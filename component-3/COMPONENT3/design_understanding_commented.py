"""Deterministic understanding of a deliberately limited PlantUML subset."""

from __future__ import annotations

# Import regex support and the small internal result container.
import re
from dataclasses import dataclass

# Import API error status and the C3 design data models.
from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import (
    DesignContext,
    DesignDiagnostic,
    DesignDiagnosticSeverity,
    ParsedAttribute,
    ParsedClass,
    ParsedElementKind,
    ParsedMethod,
    ParsedMethodParameter,
    ParsedRelationship,
    Visibility,
)
from intelise_c3.domain.generation_context import GenerationContext

# PLANTUML DESIGN PARSING RULES
# These patterns define the small, deterministic PlantUML subset C3 supports.
# Identify the UML artifact types that this parser can analyze.
_CLASS_DIAGRAM_TYPES = {"CLASS", "CLASS_DIAGRAM"}

# Define the allowed format for class, field and method names.
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_.]*"

# Find normal or abstract class declarations.
_CLASS_PATTERN = re.compile(
    rf"^(?P<abstract>abstract\s+)?class\s+(?P<name>{_IDENTIFIER})\s*(?P<body>\{{)?$"
)

# Find enum declarations and valid enum values.
_ENUM_PATTERN = re.compile(rf"^enum\s+(?P<name>{_IDENTIFIER})\s*(?P<body>\{{)?$")
_ENUM_VALUE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Single-line skinparam directives are presentation-only; block forms ("... {")
# are deliberately not matched so they still fail explicitly.
_SKINPARAM_PATTERN = re.compile(r"^skinparam\s+[^{}]+$")

# Find a method name, its parameters, return type and visibility.
_METHOD_PATTERN = re.compile(
    rf"^(?P<visibility>[+\-#~])?\s*(?P<name>{_IDENTIFIER})\s*"
    r"\((?P<parameters>[^)]*)\)\s*(?::\s*(?P<return_type>[^{{}}]+))?$"
)

# Find a class field with its name, type and visibility.
_ATTRIBUTE_PATTERN = re.compile(
    rf"^(?P<visibility>[+\-#~])?\s*(?P<name>{_IDENTIFIER})\s*:"
    r"\s*(?P<type_name>[^{{}}()]+)$"
)

# Find a relationship between two classes and its optional label or multiplicity.
_RELATIONSHIP_PATTERN = re.compile(
    rf"^(?P<left>{_IDENTIFIER})\s*"
    r"(?:\"(?P<left_multiplicity>[^\"]+)\"\s*)?"
    r"(?P<connector><\|--|--\|>|\*--|--\*|o--|--o|<--|-->|\.\.>|<\.\.|--)\s*"
    r"(?:\"(?P<right_multiplicity>[^\"]+)\"\s*)?"
    rf"(?P<right>{_IDENTIFIER})(?:\s*:\s*(?P<label>.+))?$"
)

# Find one typed parameter inside a method declaration.
_PARAMETER_PATTERN = re.compile(
    rf"^(?P<name>{_IDENTIFIER})\s*:\s*(?P<type_name>[^{{}}(),]+)$"
)

# Confirm that the document starts with a valid PlantUML opening line.
_START_PATTERN = re.compile(r"^@startuml(?:\s+\S+)?$")

# Convert PlantUML visibility symbols into normalized domain values.
_VISIBILITY = {
    "+": Visibility.PUBLIC,
    "-": Visibility.PRIVATE,
    "#": Visibility.PROTECTED,
    "~": Visibility.PACKAGE,
    None: Visibility.UNSPECIFIED,
}
# Convert PlantUML connectors into normalized relationship types.
_RELATIONSHIP_TYPES = {
    "--": "ASSOCIATION",
    "-->": "DIRECTED_ASSOCIATION",
    "<--": "DIRECTED_ASSOCIATION",
    "..>": "DEPENDENCY",
    "<..": "DEPENDENCY",
    "*--": "COMPOSITION",
    "--*": "COMPOSITION",
    "o--": "AGGREGATION",
    "--o": "AGGREGATION",
    "<|--": "INHERITANCE",
    "--|>": "INHERITANCE",
}


@dataclass(frozen=True)
class _ParsedDiagram:
    """Hold classes and relationships parsed from one class diagram."""

    # Store the two results produced by the PlantUML parser.
    classes: tuple[ParsedClass, ...]
    relationships: tuple[ParsedRelationship, ...]


class DesignUnderstandingService:
    """Build a DesignContext without changing or extending C2 design intent."""

    def build(self, generation_context: GenerationContext) -> DesignContext:
        """Parse supported class diagrams from an accepted immutable context."""

        # 1. REVIEW THE DESIGN
        # Read the C2 PlantUML artifacts and prepare the complete design summary.

        # Collect parsed output and diagnostics across every supplied UML artifact.
        parsed_classes: list[ParsedClass] = []
        parsed_relationships: list[ParsedRelationship] = []
        diagnostics: list[DesignDiagnostic] = []
        class_diagram_count = 0

        # Parse class diagrams and preserve other diagram types without interpreting them.
        for uml_element in generation_context.uml_elements:
            if uml_element.element_type.upper() not in _CLASS_DIAGRAM_TYPES:
                diagnostics.append(
                    DesignDiagnostic(
                        severity=DesignDiagnosticSeverity.INFO,
                        code="NON_CLASS_UML_PRESERVED",
                        source_uml_id=uml_element.uml_id,
                        message=(
                            f"UML artifact '{uml_element.uml_id}' was preserved but "
                            "not parsed because it is not a class diagram."
                        ),
                    )
                )
                continue

            # A class diagram must include PlantUML source before it can be parsed.
            class_diagram_count += 1
            if uml_element.plantuml_source is None or not uml_element.plantuml_source.strip():
                self._fail(
                    "MISSING_PLANTUML_SOURCE",
                    f"uml_elements.{uml_element.uml_id}.plantuml_source",
                    f"Class diagram '{uml_element.uml_id}' has no PlantUML source.",
                )

            parsed = self._parse_class_diagram(
                uml_element.uml_id, uml_element.plantuml_source
            )

            # Add this diagram's classes and relationships to the full design result.
            parsed_classes.extend(parsed.classes)
            parsed_relationships.extend(parsed.relationships)

            # Record a successful parse message for this class diagram.
            diagnostics.append(
                DesignDiagnostic(
                    severity=DesignDiagnosticSeverity.INFO,
                    code="CLASS_DIAGRAM_PARSED",
                    source_uml_id=uml_element.uml_id,
                    message=(
                        f"Parsed {len(parsed.classes)} classes and "
                        f"{len(parsed.relationships)} relationships from the "
                        "documented subset."
                    ),
                )
            )

        # Require at least one class diagram and one parsed class.
        if class_diagram_count == 0:
            self._fail(
                "MISSING_CLASS_DIAGRAM",
                "uml_elements",
                "At least one released class diagram is required for generation.",
            )
        if not parsed_classes:
            self._fail(
                "MISSING_CLASS_DEFINITION",
                "uml_elements",
                "No class definitions were found in the released class diagrams.",
            )

        # Reject duplicate class names across all supplied class diagrams.
        class_names: set[str] = set()
        for parsed_class in parsed_classes:
            if parsed_class.name in class_names:
                self._fail(
                    "DUPLICATE_CLASS_DEFINITION",
                    f"uml_elements.{parsed_class.source_uml_id}",
                    f"Class '{parsed_class.name}' is defined more than once.",
                )
            class_names.add(parsed_class.name)

        # Every relationship endpoint must name a class declared in the design.
        for relationship in parsed_relationships:
            unknown_names = [
                name
                for name in (relationship.source_class, relationship.target_class)
                if name not in class_names
            ]
            if unknown_names:
                self._fail(
                    "UNKNOWN_RELATIONSHIP_CLASS",
                    f"uml_elements.{relationship.source_uml_id}",
                    "Relationship references undefined class(es): "
                    + ", ".join(unknown_names),
                )

        # Record that upstream C1/C2 identities and trace links were retained.
        diagnostics.append(
            DesignDiagnostic(
                severity=DesignDiagnosticSeverity.INFO,
                code="UPSTREAM_PROVENANCE_PRESERVED",
                message=(
                    "C1 requirement identities, approval/SRS provenance, C2 UML "
                    "identities, anchors, and UI references were preserved."
                ),
            )
        )

        # Return the normalized design used by coverage, stack selection and generation.
        return DesignContext(
            generation_context_version=generation_context.context_version,
            project_id=generation_context.project_id,
            srs_version=generation_context.srs_version,
            uml_version=generation_context.uml_version,
            source_contract_versions=generation_context.source_contract_versions,
            upstream_provenance=generation_context.upstream_provenance,
            requirements=generation_context.requirements,
            source_uml_elements=generation_context.uml_elements,
            ui_artifacts=generation_context.ui_artifacts,
            requirement_uml_anchors=generation_context.requirement_uml_anchors,
            classes=tuple(parsed_classes),
            relationships=tuple(parsed_relationships),
            diagnostics=tuple(diagnostics),
        )

    def _parse_class_diagram(self, uml_id: str, source: str) -> _ParsedDiagram:
        # Read one PlantUML class diagram and convert it into structured data.

        # Keep parser state while reading the PlantUML document line by line.
        classes: list[ParsedClass] = []
        relationships: list[ParsedRelationship] = []
        current_class_name: str | None = None
        current_attributes: list[ParsedAttribute] = []
        current_methods: list[ParsedMethod] = []
        current_kind = ParsedElementKind.CLASS
        current_abstract = False
        current_values: list[str] = []
        started = False
        ended = False

        # Validate the envelope and interpret each supported declaration.
        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            # Remove extra spaces and ignore empty lines or comments.
            line = raw_line.strip()
            if not line or line.startswith("'") or line.startswith("//"):
                continue

            # Create a precise source location for any validation error.
            field = f"uml_elements.{uml_id}.plantuml_source.line.{line_number}"

            # Start reading content after the @startuml marker.
            if _START_PATTERN.fullmatch(line):
                if started:
                    self._fail(
                        "UNSUPPORTED_PLANTUML_CONSTRUCT",
                        field,
                        "Nested or repeated @startuml is not supported.",
                    )
                started = True
                continue

            # Finish the document at @enduml and reject an unclosed class body.
            if line == "@enduml":
                if current_class_name is not None:
                    self._fail(
                        "INCOMPLETE_CLASS_BODY",
                        field,
                        f"Class '{current_class_name}' is missing its closing brace.",
                    )
                ended = True
                continue

            # Reject content placed outside the PlantUML start and end markers.
            if not started or ended:
                self._fail(
                    "INCOMPLETE_PLANTUML_DOCUMENT",
                    field,
                    "Content must occur between @startuml and @enduml.",
                )

            # Ignore supported visual styling because it does not change the design.
            if current_class_name is None and _SKINPARAM_PATTERN.fullmatch(line):
                continue

            # While inside a class/enum body, parse members until the closing brace.
            if current_class_name is not None:
                if line == "}":
                    # Save the completed class or enum and reset the parser state.
                    classes.append(
                        ParsedClass(
                            source_uml_id=uml_id,
                            name=current_class_name,
                            attributes=tuple(current_attributes),
                            methods=tuple(current_methods),
                            kind=current_kind,
                            is_abstract=current_abstract,
                            values=tuple(current_values),
                        )
                    )
                    current_class_name = None
                    current_attributes = []
                    current_methods = []
                    current_kind = ParsedElementKind.CLASS
                    current_abstract = False
                    current_values = []
                    continue

                # Enum bodies may contain only unique simple values.
                if current_kind is ParsedElementKind.ENUM:
                    if not _ENUM_VALUE_PATTERN.fullmatch(line):
                        self._fail(
                            "UNSUPPORTED_PLANTUML_MEMBER",
                            field,
                            f"Unsupported enum value syntax: '{line}'.",
                        )
                    if line in current_values:
                        self._fail(
                            "DUPLICATE_ENUM_VALUE",
                            field,
                            f"Enum '{current_class_name}' repeats value '{line}'.",
                        )
                    current_values.append(line)
                    continue

                # Parse a supported method signature.
                method_match = _METHOD_PATTERN.fullmatch(line)
                if method_match:
                    current_methods.append(
                        self._parse_method(uml_id, line_number, method_match)
                    )
                    continue

                # Parse a supported class attribute.
                attribute_match = _ATTRIBUTE_PATTERN.fullmatch(line)
                if attribute_match:
                    current_attributes.append(
                        ParsedAttribute(
                            name=attribute_match.group("name"),
                            type_name=attribute_match.group("type_name").strip(),
                            visibility=_VISIBILITY[
                                attribute_match.group("visibility")
                            ],
                        )
                    )
                    continue

                self._fail(
                    "UNSUPPORTED_PLANTUML_MEMBER",
                    field,
                    f"Unsupported class member syntax: '{line}'.",
                )

            # 2. CLASSES IN THE DESIGN
            # Extract class names, fields, methods and enum details from C2 PlantUML.

            # Start a class/enum declaration or store a declaration without a body.
            class_match = _CLASS_PATTERN.fullmatch(line)
            enum_match = None if class_match else _ENUM_PATTERN.fullmatch(line)
            if class_match or enum_match:
                declaration = class_match or enum_match
                assert declaration is not None
                kind = (
                    ParsedElementKind.CLASS
                    if class_match
                    else ParsedElementKind.ENUM
                )
                is_abstract = bool(class_match and class_match.group("abstract"))
                if declaration.group("body"):
                    current_class_name = declaration.group("name")
                    current_attributes = []
                    current_methods = []
                    current_kind = kind
                    current_abstract = is_abstract
                    current_values = []
                else:
                    classes.append(
                        ParsedClass(
                            source_uml_id=uml_id,
                            name=declaration.group("name"),
                            attributes=(),
                            methods=(),
                            kind=kind,
                            is_abstract=is_abstract,
                        )
                    )
                continue

            # 3. CLASS CONNECTIONS
            # Extract how the classes connect, including relationship type and direction.

            # Parse a supported relationship between two declared classes.
            relationship_match = _RELATIONSHIP_PATTERN.fullmatch(line)
            if relationship_match:
                connector = relationship_match.group("connector")
                relationships.append(
                    ParsedRelationship(
                        source_uml_id=uml_id,
                        source_class=relationship_match.group("left"),
                        target_class=relationship_match.group("right"),
                        connector=connector,
                        relationship_type=_RELATIONSHIP_TYPES[connector],
                        source_multiplicity=relationship_match.group(
                            "left_multiplicity"
                        ),
                        target_multiplicity=relationship_match.group(
                            "right_multiplicity"
                        ),
                        label=relationship_match.group("label"),
                    )
                )
                continue

            self._fail(
                "UNSUPPORTED_PLANTUML_CONSTRUCT",
                field,
                f"Unsupported PlantUML syntax: '{line}'.",
            )

        # The complete diagram must have a valid PlantUML start and end marker.
        if not started or not ended:
            self._fail(
                "INCOMPLETE_PLANTUML_DOCUMENT",
                f"uml_elements.{uml_id}.plantuml_source",
                "PlantUML class diagrams require @startuml and @enduml.",
            )

        # Return all classes and relationships found in this diagram.
        return _ParsedDiagram(tuple(classes), tuple(relationships))

    def _parse_method(
        self, uml_id: str, line_number: int, match: re.Match[str]
    ) -> ParsedMethod:
        # Convert one matched method line into a structured method object.

        # Parse and validate each typed method parameter.
        parameters: list[ParsedMethodParameter] = []
        parameter_text = match.group("parameters").strip()
        if parameter_text:
            for parameter in parameter_text.split(","):
                parameter_match = _PARAMETER_PATTERN.fullmatch(parameter.strip())
                if not parameter_match:
                    self._fail(
                        "UNSUPPORTED_PLANTUML_PARAMETER",
                        (
                            f"uml_elements.{uml_id}.plantuml_source.line."
                            f"{line_number}"
                        ),
                        f"Unsupported method parameter syntax: '{parameter.strip()}'.",
                    )
                parameters.append(
                    ParsedMethodParameter(
                        name=parameter_match.group("name"),
                        type_name=parameter_match.group("type_name").strip(),
                    )
                )

        # Return the normalized method signature.
        return ParsedMethod(
            name=match.group("name"),
            parameters=tuple(parameters),
            return_type=(
                match.group("return_type").strip()
                if match.group("return_type")
                else None
            ),
            visibility=_VISIBILITY[match.group("visibility")],
        )

    @staticmethod
    def _fail(code: str, field: str, message: str) -> None:
        # Use one shared error format for every invalid PlantUML rule.

        # Stop parsing with a precise field-level HTTP 422 validation error.
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=422,
        )
