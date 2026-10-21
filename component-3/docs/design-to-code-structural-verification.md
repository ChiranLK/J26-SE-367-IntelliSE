# Deterministic Design-to-Code Structural Verification

This document defines the narrow Component 3 Task 8 verification method for
the generated React + Node.js Task Management MVP. The verifier reads text and
metadata only. It never imports, builds, installs, starts, or executes generated
JavaScript.

## Verified input boundary

`POST /api/v1/structural-verifications` accepts:

- the Task 6 `GenerationManifest`;
- its safe path relative to `GENERATED_WORKSPACE_ROOT`; and
- the immutable `DesignContext` used for that generation run.

Before structural findings are produced, Component 3 reuses
`ManifestVerificationService` to verify the evidence digest, stored-manifest
equality, safe paths, every recorded file size and SHA-256, and the aggregate
artifact digest. It then checks the canonical DesignContext hash against the
hash bound into the run evidence and checks exact project, SRS/UML versions,
requirement IDs, UML IDs, anchors, UI references, contract versions, and
upstream provenance references.

An input-integrity or identity failure returns HTTP 409 and produces no
misleading successful report. The rule set supports only the generated
`react-nodejs` MVP. Other selected stacks are rejected explicitly.

The verified manifest's typed traceability evidence supplies exact generated
module, requirement, and UML identities for findings. The persisted living
graph is derived from that same manifest and is not accepted as an alternative
source of truth for this check. This avoids trusting a stale graph when the
manifest or files have changed.

## Rule set

Report version `1.0` uses `C3_TASK_MVP_STRUCTURAL_RULES_V1`.

| Finding ID | Rule | Deterministic evidence |
|---|---|---|
| `C3SV-DESIGN-001` | Supported design boundary | Exact parsed `Task`, `TaskService`, and `TaskRepository` names; Task fields; required methods; and directed relationships from `DesignContext`. Missing supported elements fail. Additional classes or relationships require review. |
| `C3SV-MODULE-001` | Required module boundary | Exact manifest paths, module identities, and artifact types for app, routes, controller, service, repository, OpenAPI, React client, and SQL schema. |
| `C3SV-ARCH-001` | Layering | Static imports, injected composition, and forbidden direct dependencies. The supported direction is Routes -> Controller -> Service -> Repository, composed in `app.js`. Direct Controller -> Repository access fails. |
| `C3SV-FLOW-001` | Express call chain | Fixed Task route method/path mappings, controller handler identities, and controller calls to service operations. |
| `C3SV-API-001` | Manifest/OpenAPI alignment | Manifest operation identities versus the limited OpenAPI path/method/operationId/success-status structure and Task fields. |
| `C3SV-UI-001` | React API client alignment | Static Task API base URL, methods, path-parameter construction, and serialized request bodies. |
| `C3SV-REPOSITORY-001` | Repository seam | Exact MVP method signatures and matching service calls for `list`, `findById`, `create`, `update`, and `remove`. |
| `C3SV-DATABASE-001` | Database artifact alignment | Design Task fields, manifest table/column identities, and the limited SQL table/column declaration. |
| `C3SV-LIMIT-001` | Unsupported proof boundary | Always `REVIEW_REQUIRED`; static evidence cannot prove runtime behavior, semantics, test execution, real database persistence, or Component 4 readiness. |

The parsers are intentionally limited to the formatting emitted by the Task 6
generator. They are deterministic source scanners, not general JavaScript,
OpenAPI, SQL, React, or PlantUML parsers. Missing or conflicting supported
structures are `FAIL`. Structures outside the documented subset are
`REVIEW_REQUIRED` where they can be identified safely; they are never silently
treated as verified.

## Status and provenance

Every finding has a stable finding ID, rule ID, status, message, exact affected
manifest file IDs, requirement IDs, UML IDs, evidence paths, expected evidence,
observed evidence, and optional remediation. These fields are designed for a
later scoped-regeneration milestone but do not authorize a patch by themselves.

Overall status is calculated in this order:

1. any `FAIL` finding -> `FAIL`;
2. otherwise any `REVIEW_REQUIRED` finding -> `REVIEW_REQUIRED`;
3. otherwise -> `PASS`.

The report also records the generation run ID, source versions, source IDs,
artifact/evidence/DesignContext hashes, rule-set version, and verification UTC
timestamp. Findings for identical verified bytes and DesignContext are
deterministic; the timestamp records when verification occurred.

## C3 versus Component 4

These are deterministic Component 3 structural findings. A `PASS` means only
that the supported static pattern was observed in verified files. It does not
mean the generated application compiled, ran, passed tests, preserved full
requirements semantics, or received independent approval.

Component 4 remains responsible for independent testing, semantic-preservation
assessment, XAI defect explanations, convergence, and readiness reports. This
service neither implements XAI nor converts a structural result into deployment
authorization.

## Known limitations and manual review

- Generated JavaScript is not executed, so dynamic imports, runtime routing,
  asynchronous behavior, framework semantics, and error paths are not proven.
- The SQL file is design-only. Runtime persistence remains `IN_MEMORY`.
- OpenAPI and SQL checks cover only the generator's documented narrow syntax.
- Regex evidence can detect supported syntax but is not a full AST or data-flow
  proof. Semantically equivalent reformatted code may require a future parser.
- Dependency vulnerability auditing, building, and runtime testing require a
  separately approved isolated environment.
- C1/C2 provenance references and hashes are integrity evidence, not proof of
  authentic upstream approval.
- A researcher must review any `REVIEW_REQUIRED` finding before using the
  report for an experiment or later regeneration decision.

## Swagger workflow

Start Component 3, open `http://127.0.0.1:8000/docs`, and use:

```text
POST /api/v1/structural-verifications
```

Supply the exact stored manifest, its workspace-relative path, and its bound
DesignContext. Do not edit the stored workspace to manufacture a passing
result; any byte change without a new valid manifest is rejected first.
