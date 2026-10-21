# Dynamic CRUD generation — Stage 1

## Status and research boundary

Stage 1 adds a deterministic, schema-driven React + Node.js generator for a
narrow profile of independent CRUD entities. It does not use an LLM to infer
missing operations or design intent. The Student, Library, and Inventory inputs
under `tests/fixtures/simulated/` are explicitly **SIMULATED** research fixtures;
they are not approved C1/C2 outputs and do not prove end-to-end integration.

Generated JavaScript is treated as untrusted. The Python tests verify rendered
text, paths, manifests, hashes, evidence, and graph construction without
installing dependencies or executing the generated application. No tracked
Docker preview runner exists in the current baseline, so Stage 1 makes no
full-stack runtime-success claim.

## Upstream contract compatibility

The repository contains an actual tracked C1 extraction model but no C2 source
package or approved C2 sample.

| Source | Fields available in tracked code | Stage 1 interpretation |
|---|---|---|
| C1 project/extraction | project ID, project name/description/discussion, draft project status, extraction run ID, source discussion hash, creation time, model ID, prompt version, candidate requirement ID/text/evidence/actor/action, candidate review status | Insufficient by itself for C3 generation. It does not supply an approved SRS version, accepted requirement state, approval provenance, or validation-report reference required by the provisional C3 boundary. |
| C2 | No tracked C2 directory, contract, or example output exists | Real compatibility is `NOT_VERIFIED`. |
| C3 provisional input | contract versions, project ID, approved SRS version/status/provenance/report, requirement IDs/titles; validated design release/status/report, PlantUML element IDs/source refs/source, requirement-to-UML anchor IDs, UI design IDs/source refs | These remain adaptable assumptions until the C1 and C2 owners approve real schemas. Reference strings are preserved evidence labels, not proof of authenticity. |

The translation path is:

`ProvisionalInputPackage -> GenerationContext -> DesignContext -> CrudApplicationSpec`

Stage 1 never requires new fields from C1/C2. It consumes only the already
accepted immutable `DesignContext`. Actual C1/C2 samples cannot yet be used for
an end-to-end compatibility test because an approved C2 contract/sample is
absent and the tracked C1 extraction output does not satisfy the approved-input
boundary. Tests explicitly confirm that the current C1 extraction shape is not
mistaken for an approved C1 SRS package.

## Versioned intermediate specification

`CrudApplicationSpec` version `1.0` is immutable and supports one or more
independent aggregates. Every aggregate must have:

- one entity class with exactly one `id: String` and at least one mutable field;
- one dedicated service class and one dedicated repository class;
- explicit `Service -> Repository : uses` and
  `Repository -> Entity : persists` UML relationships;
- explicit list, create, update, and delete/remove methods in service and
  repository evidence;
- requirements that name exactly one entity and collectively state all four
  CRUD operations;
- an exact requirement-to-source-diagram UML anchor for every mapped
  requirement. The provisional C2 anchor identifies a UML artifact/diagram,
  not a class member; element-level anchor precision is therefore unavailable
  and must not be claimed.

Supported scalar UML types normalize to `STRING`, `INTEGER`, `NUMBER`,
`BOOLEAN`, or `DATE`. Optional/null fields, composite keys, enums, inheritance,
associations between entities, nested values, file uploads, authentication,
and non-CRUD workflows are unsupported. Unsupported or ambiguous evidence is
rejected; it is not omitted or converted into Task Management behavior.

## Deterministic outputs

The same renderer produces application metadata, React navigation/pages/forms/
lists/API clients/CSS, Express routes/controllers/services, injected in-memory
repositories, per-entity service test seams, an OpenAPI 3.1 document, and a SQL
schema. Names, form controls, validations, paths, operation IDs, table/column
IDs, and trace bindings come from `CrudApplicationSpec`.

Direct dependency versions are pinned in generated `package.json` files. IDs
use `globalThis.crypto.randomUUID()`. Express input rejects unknown, missing,
or invalid scalar fields with HTTP 400; missing records return HTTP 404. CORS is
restricted to the explicit `CORS_ALLOWED_ORIGIN` setting (default loopback).

The SQL file is design evidence only. Runtime repositories remain `IN_MEMORY`;
therefore repository-to-table links are `UNRESOLVED / REVIEW_REQUIRED`, not
claims of database-backed persistence. UI design references are also retained
as `UNRESOLVED / REVIEW_REQUIRED` because C2 currently supplies an artifact
reference but no element-level layout mapping.

## Provenance and compatibility

Dynamic manifests preserve exact C1 requirement IDs, C2 UML IDs, anchor IDs,
UI references, source versions, approval/validation reference labels, artifact
SHA-256 values, and the run evidence digest. The traceability graph builder can
consume those manifests using explicit mappings; no link is based on filename
similarity.

Historical Task manifests and workspaces are not rewritten. Structurally
recognized Task input continues through the versioned legacy Task generator,
including its existing local-Ollama mode.

Dynamic local-LLM generation is deliberately rejected in Stage 1 rather than
falling back to templates. The current structural verifier and scoped
regenerator have Task-specific rule/patch policies; they explicitly reject a
dynamic generator manifest. Schema-driven verification and regeneration
adapters are later work and must be implemented before those services can make
claims about dynamic runs.

## Test fixtures and current limitations

One shared implementation is exercised with:

- Student: `Student` with string, integer, number, boolean, and date fields;
- Library: independent `Book` and `Member` entities;
- Inventory: `InventoryItem` with inventory-specific fields and routes.

These fixtures verify different code paths, forms, API operations, repositories,
tables, digests, and source identities. They are unit-test inputs, not research
benchmark results.

Validation is intentionally narrow. For example, a date is checked against
`YYYY-MM-DD` shape but not calendar semantics; numeric ranges cannot be derived
because the provisional upstream contract carries no min/max constraints. UI
layout is a deterministic accessible default rather than an asserted rendering
of an approved C2 wireframe.

