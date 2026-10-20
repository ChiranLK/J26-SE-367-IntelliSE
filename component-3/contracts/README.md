# Component integration contracts

The FR-C3-01 C1/C2 schemas implemented in
`src/intelise_c3/contracts/provisional_input.py` are **PROVISIONAL**. They are
Component 3 assumptions for research and testing, not approved group
integration contracts. The Component 1 and Component 2 owners must confirm or
replace them before real integration.

## Current assumptions

- Contract version `1.0` is the only provisional version accepted.
- C1 supplies a project ID, SRS version, package approval state, stable
  requirement IDs, per-requirement states, an approval provenance reference,
  and an SRS validation-report reference.
- C2 supplies the same project ID and source SRS version, a UML version,
  release and validation states, a design validation-report reference, UML
  elements, structured UI/wireframe artifacts, and requirement-to-UML anchors.
- A provisional UML element may carry an optional `plantuml_source`. Task 4
  requires this source for elements labeled `CLASS` or `CLASS_DIAGRAM`; input
  validation preserves it without claiming that Component 3 validated its
  semantics.
- C1 may carry an optional `design_uml_version_ref`. When present, C2's `uml_version`
  must equal it, otherwise validation fails with 409 `UML_VERSION_MISMATCH`. A blank
  C2 `uml_version` is also reported as `UML_VERSION_MISMATCH`.
- Identifiers use letters, digits, dots, underscores, colons, and hyphens.
- Reference strings are opaque and are preserved; Component 3 does not resolve
  them or establish their authenticity.

An approval or validation reference in JSON does **not** prove genuine client
approval or an authoritative upstream validation result. Authentication,
signatures, trusted issuer checks, and retrieval from C1/C2 systems remain
future integration work.

External transport models remain separate from Component 3's internal
`GenerationContext` domain model so confirmed contracts can later be adapted
without redefining downstream state.

The stack-selection request is a Component 3 decision input, not a C1 or C2
contract. Its evidence references and confidence values require manual review.

The Task 6 `CodeGenerationRequest` is also an internal Component 3 request
contract. Its `ProvisionalStackApproval` is an explicit workflow assertion for
the research MVP, not authoritative evidence of the caller's identity or
approval power. Real integration must replace that trust boundary with the
team's approved identity and authorization mechanism.
