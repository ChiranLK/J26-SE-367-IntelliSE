# Living Requirement Traceability — Research Novelty 1

This document defines the provisional Component 3 Task 7 methodology. It
builds an append-only, typed traceability graph from a verified Task 6
manifest. It does not implement Component 4 XAI, scoped regeneration, or
deployment authorization.

## Acceptance and integrity boundary

Before graph construction, Component 3 verifies:

1. the Task 6 canonical evidence digest;
2. exact canonical equality between the supplied manifest and the workspace's
   stored `artifact-manifest.json`;
3. safe workspace and artifact-relative paths;
4. the presence, byte size, and SHA-256 of every manifest file; and
5. the aggregate artifact digest over sorted `path`, NUL, file hash, newline
   records.

No generated JavaScript is executed. SHA-256 detects inconsistent bytes but is
not proof of authorship or approval and cannot stop an actor who can modify all
records and recompute hashes. Trusted signing and protected upstream storage
remain future integration work.

## Typed graph model

Snapshot schema `1.0` supports these node types:

- `REQUIREMENT`
- `UML_ELEMENT`
- `DESIGN_ANCHOR`
- `CODE_MODULE`
- `API_OPERATION`
- `DATABASE_ARTIFACT` (table or column, identified in attributes)
- `TEST_HOOK`
- `UI_ARTIFACT`

It supports `DERIVED_FROM`, `IMPLEMENTS`, `EXPOSES`, `PERSISTS_TO`, and
`VERIFIED_BY` relations. The existing Task 6 `DEFINES` relation is also
preserved because it is already part of the accepted typed evidence and is
needed to connect SQL modules to table/column identities.

### Normative relation direction policy

`C3_GRAPH_RELATION_DIRECTION_V1` treats every edge as
`source --RELATION--> target`. `DERIVED_FROM` always follows a
**downstream-to-upstream** convention: the source is the derived artifact and
the target is its upstream evidence. The exact permitted endpoint pairs are:

| Relation | Permitted source -> target | Meaning |
|---|---|---|
| `DERIVED_FROM` | `UML_ELEMENT -> REQUIREMENT` | The C2 UML element is derived from the C1 requirement identified by the exact C2 anchor. |
| `DERIVED_FROM` | `DESIGN_ANCHOR -> REQUIREMENT`, `DESIGN_ANCHOR -> UML_ELEMENT` | The anchor records its two exact upstream identities. |
| `DERIVED_FROM` | `CODE_MODULE -> UML_ELEMENT`, `CODE_MODULE -> DESIGN_ANCHOR`, `CODE_MODULE -> UI_ARTIFACT` | The generated module cites that upstream design evidence. UI links remain review-required where the input lacks an authoritative mapping. |
| `IMPLEMENTS` | `CODE_MODULE -> REQUIREMENT`, `CODE_MODULE -> TEST_HOOK` | The code module implements the target requirement or injected seam. |
| `EXPOSES` | `CODE_MODULE -> API_OPERATION` | The code module exposes the identified API operation. |
| `PERSISTS_TO` | `CODE_MODULE -> DATABASE_ARTIFACT` | The code module persists to the table/column. The current in-memory repository link remains unresolved. |
| `VERIFIED_BY` | `CODE_MODULE -> CODE_MODULE`, `CODE_MODULE -> TEST_HOOK` | The source module has trace evidence pointing to its test module or test hook; this does not assert test execution. |
| `DEFINES` | `CODE_MODULE -> DATABASE_ARTIFACT` | The SQL/code module defines the identified database artifact. |

Graph construction rejects any other supported node-type combination with
`INVALID_TRACE_RELATION_DIRECTION`. It does not infer or silently invert an
arbitrary link. New graph snapshots record this policy version and bind it into
their graph content digest. Historical snapshots that predate the field remain
unchanged and deserialize it as `null`.

Task 6 mapping policy `task-mvp-traceability-v2` emits the canonical
`UML_ELEMENT -> DERIVED_FROM -> REQUIREMENT` direction. Historical policy
`task-mvp-traceability-v1` emitted the reverse edge. Task 7 normalizes only
that one legacy rule when the link contains exactly matching requirement, UML,
and C2 anchor evidence. The normalized link records
`C3_LEGACY_C2_DIRECTION_NORMALIZATION_V1` and the original link ID in its
provenance. Missing or ambiguous anchor evidence is rejected with
`LEGACY_TRACE_DIRECTION_MIGRATION_REQUIRED`; regeneration or an explicit
migration is then required. Existing workspace manifests, hashes, and SQLite
snapshots are never rewritten.

Stable node IDs are constructed only from manifest identities, for example
`REQUIREMENT:REQ-TASK-001` and `CODE_MODULE:FILE-017F30BBE617`. Files are not
matched using filename similarity. Links retain their mapping rule, evidence
references, details, resolution status, and review status. C2 anchors also
produce deterministic `DESIGN_ANCHOR` links backed by the exact anchor ID.

Manifest links marked `RESOLVED` are accepted only when both endpoint nodes
exist and provenance is not `UNRESOLVED_SOURCE_REFERENCE`. Uncertain UI and
runtime SQL-persistence links remain `UNRESOLVED` / `REVIEW_REQUIRED`.

## Determinism and persistence

The graph ID is a deterministic project-scoped identifier. Nodes and links are
sorted by stable IDs. `graph_content_digest_sha256` covers the source identity,
generation run, manifest/evidence/artifact digests, nodes, links, coverage, and
diagnostics using `C3_CANONICAL_JSON_V1`.

Rebuilding an identical manifest produces identical graph content and content
digest. Persisting it again creates a new snapshot ID and incremented graph
version; it never overwrites the older version.

SQLite stores immutable snapshot JSON and the accepted source-manifest JSON in
`TRACEABILITY_STORE_PATH`, defaulting to:

```text
component-3/runtime/traceability/traceability.sqlite3
```

That mutable directory is Git-ignored. SQLite is an MVP local store, not a
multi-tenant or tamper-resistant evidence repository.

## Living update algorithm

1. Retrieve the requested base snapshot and its previously accepted manifest.
2. Require updates to start from the latest version, preventing silent forks.
3. independently verify the candidate manifest and all candidate files.
4. Reject a different project. Compare source versions and identity sets; if
   they changed, require an explicit caller-asserted research approval record.
   The record is retained with `authenticity_verified=false`.
5. Compare files by stable `file_id`:
   - only new ID: `added`;
   - only old ID: `removed`;
   - same ID but changed hash or path: `changed`;
   - same ID, path, and hash: `unchanged`.
6. Deterministically build a candidate graph from the new evidence.
7. Preserve byte-for-byte identical active links whose affected endpoints did
   not change.
8. Revalidate links touching changed code-module nodes against the new verified
   manifest evidence.
9. Add newly supported nodes and links.
10. Carry links absent or superseded in the candidate into the new snapshot as
    `RETIRED`, recording the retirement version and reason. Removed nodes are
    similarly retained as retired records; earlier snapshots remain immutable.
11. Recalculate coverage/diagnostics and append the new SQLite version.
12. Return a `GraphChangeReport` containing artifact/node/link classifications,
    preserved, revalidated, added, and retired link IDs.

The comparison endpoint performs steps 1–10 without persistence. The update
endpoint persists the result.

## Coverage policy

`C3_COVERAGE_POLICY_V1` classifies each requirement:

- `VERIFIED`: at least one active resolved `IMPLEMENTS` link from a code module
  and an active resolved `VERIFIED_BY` link from an implementing module;
- `PARTIAL`: resolved implementation evidence exists but no resolved test link
  is connected to an implementing module;
- `UNRESOLVED`: no resolved implementation evidence exists.

Reports also list dangling active nodes, unresolved/review-required links, and
missing evidence diagnostics. Here, `VERIFIED` means graph evidence is present;
it does not mean Component 4 executed or approved a test.

## Precision, recall, and F1 evaluation

Evaluation accepts a separately supplied `RESEARCHER_CURATED` dataset with a
dataset/version/reference, an explicit node scope, and manually labeled link
triples. Active resolved algorithm links are filtered to that same scope.

```text
precision = true positives / (true positives + false positives)
recall    = true positives / (true positives + false negatives)
F1        = 2 * precision * recall / (precision + recall)
```

An empty denominator yields `0.0`, including F1 when `precision + recall` is
zero. Evaluation report version `1.1` applies the formulas to exact set counts
without decimal rounding; serialization therefore preserves the same Python
floating-point values used by precision and recall. These metrics measure link
agreement only. They do not measure generated-software correctness, semantic
preservation, test execution, Component 4 approval, or evidence authenticity.

Results are labeled `CALCULATED_NOT_BENCHMARKED`. The included simulated
fixture is a unit-test oracle for the method, not independently reviewed ground
truth, Component 4 output, a production dataset, or a reported scientific
benchmark. Real evaluation results must be collected and reported separately
by the researcher.

### Human-review checklist for research ground truth

The simulated fixture remains `NOT_VERIFIED` until a real review records all
of the following without altering the algorithm output:

- [ ] Inspect the authoritative requirement and UML sources.
- [ ] Identify expected typed links independently of the algorithm output.
- [ ] Confirm every expected edge uses the normative source/target direction.
- [ ] Record the independent reviewer's real identity and review date.
- [ ] Record disagreements and their adjudication outcome.
- [ ] Record final researcher approval of the versioned ground-truth dataset.

No reviewer identity, signature, date, approval, or benchmark result is
currently claimed.

## API

```text
POST /api/v1/traceability/graphs
GET  /api/v1/traceability/graphs/{graph_id}
GET  /api/v1/traceability/graphs/{graph_id}/versions/{version}
POST /api/v1/traceability/graphs/{graph_id}/compare
POST /api/v1/traceability/graphs/{graph_id}/updates
POST /api/v1/traceability/graphs/{graph_id}/versions/{version}/evaluate
```

Creation, comparison, and update requests contain the manifest plus its safe
path relative to `GENERATED_WORKSPACE_ROOT`. Arbitrary host paths are rejected.

## Provisional research decisions requiring approval

- Whether one project should always map to one graph ID.
- Whether identical manifests should create new versions or be deduplicated.
- Whether source-version approval needs signed C1/C2 evidence rather than the
  current explicitly unauthenticated researcher assertion.
- Whether `VERIFIED` should require direct per-requirement test-hook evidence
  instead of the current implementing-module-to-test path.
- Whether database tables and columns should remain one node type with a kind
  attribute or become separate graph node types.
- Whether retired nodes/links should appear in every later snapshot or move to
  separate temporal-history tables.
- Ground-truth scope, labeling protocol, adjudication, and experimental sample
  size for the research evaluation.

## Known limitations

- The graph consumes the narrow Task 6 manifest and its provisional mapping
  rules; it does not independently infer software semantics.
- SQLite has no cryptographic audit log, access control, encryption policy, or
  multi-process coordination beyond transactions and version conflict checks.
- Task 6 hashes do not authenticate the source issuer.
- Comparison uses stable file IDs and hashes; rename detection is intentionally
  not inferred from similar filenames or content.
- UI-to-file and in-memory-repository-to-SQL relationships remain review
  required.
- No generated dependency is installed and no generated code is executed.
- Scoped regeneration, graph-driven patch authorization, deployment gates,
  Component 4 XAI, and C4 readiness remain outside this task.
