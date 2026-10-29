"""Normative relation directions for the Component 3 traceability graph."""

from intelise_c3.domain.generation import TraceRelationType
from intelise_c3.domain.traceability import GraphNodeType


RELATION_DIRECTION_POLICY_VERSION = "C3_GRAPH_RELATION_DIRECTION_V1"
LEGACY_TRACEABILITY_MAPPING_POLICY_VERSION = "task-mvp-traceability-v1"
CURRENT_TRACEABILITY_MAPPING_POLICY_VERSION = "task-mvp-traceability-v2"
LEGACY_C2_DIRECTION_RULE = "C2_REQUIREMENT_UML_ANCHOR_V1"
LEGACY_C2_NORMALIZATION_RULE = "C3_LEGACY_C2_DIRECTION_NORMALIZATION_V1"


PERMITTED_RELATION_ENDPOINTS: dict[
    TraceRelationType,
    frozenset[tuple[GraphNodeType, GraphNodeType]],
] = {
    TraceRelationType.DERIVED_FROM: frozenset(
        {
            (GraphNodeType.UML_ELEMENT, GraphNodeType.REQUIREMENT),
            (GraphNodeType.DESIGN_ANCHOR, GraphNodeType.REQUIREMENT),
            (GraphNodeType.DESIGN_ANCHOR, GraphNodeType.UML_ELEMENT),
            (GraphNodeType.CODE_MODULE, GraphNodeType.UML_ELEMENT),
            (GraphNodeType.CODE_MODULE, GraphNodeType.DESIGN_ANCHOR),
            (GraphNodeType.CODE_MODULE, GraphNodeType.UI_ARTIFACT),
        }
    ),
    TraceRelationType.IMPLEMENTS: frozenset(
        {
            (GraphNodeType.CODE_MODULE, GraphNodeType.REQUIREMENT),
            (GraphNodeType.CODE_MODULE, GraphNodeType.TEST_HOOK),
        }
    ),
    TraceRelationType.EXPOSES: frozenset(
        {(GraphNodeType.CODE_MODULE, GraphNodeType.API_OPERATION)}
    ),
    TraceRelationType.PERSISTS_TO: frozenset(
        {(GraphNodeType.CODE_MODULE, GraphNodeType.DATABASE_ARTIFACT)}
    ),
    TraceRelationType.VERIFIED_BY: frozenset(
        {
            (GraphNodeType.CODE_MODULE, GraphNodeType.CODE_MODULE),
            (GraphNodeType.CODE_MODULE, GraphNodeType.TEST_HOOK),
        }
    ),
    TraceRelationType.DEFINES: frozenset(
        {(GraphNodeType.CODE_MODULE, GraphNodeType.DATABASE_ARTIFACT)}
    ),
}


def is_permitted_relation(
    relation_type: TraceRelationType,
    source_type: GraphNodeType,
    target_type: GraphNodeType,
) -> bool:
    """Return whether a typed edge follows the versioned direction policy."""

    return (source_type, target_type) in PERMITTED_RELATION_ENDPOINTS.get(
        relation_type,
        frozenset(),
    )
