# Dynamic CRUD Docker validation — Stage 2

## Scope and result boundary

This Stage 2 harness generates the simulated Student, Library, and Inventory
applications through the same Component 3 pipeline and validates them inside
disposable Linux containers. It does not execute generated JavaScript on the
Windows host. The fixtures remain simulated C1/C2-style evidence; this work
does not claim real upstream integration or Component 4 approval.

The runtime repositories are `IN_MEMORY`. The generated SQL files are design
artifacts and are checked for model consistency, but no database server or
database-backed persistence is implemented or claimed.

## Reproducible command

Docker Desktop must be running with Linux containers. From `component-3/`:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -m intelise_c3.scripts.validate_dynamic_crud_docker
Remove-Item Env:PYTHONPATH
```

The command validates all three domains and exits non-zero if any domain
fails. To validate one domain, add `--domain student_management`,
`--domain library_management`, or `--domain inventory_management`. Use
`--keep-images` only for a separately approved manual preview; otherwise the
harness removes each image after validation.

Reports and command logs are written below the ignored
`.stage2-validation/stage2-<UTC>-<random>/` directory. These runtime files are
not generation history and must not be committed. Generated research
workspaces, historical manifests, graph snapshots, and Task runs are not
rewritten.

## Validation sequence

For every domain the orchestrator:

1. loads the explicitly simulated provisional input package;
2. invokes the real input validation, design understanding, stack selection,
   CRUD-spec builder, and code generation services;
3. verifies every manifest file hash, the artifact digest, and evidence digest;
4. checks paths, dependencies, lifecycle scripts, Node engine, OpenAPI
   operations and schemas, SQL table identities, and the `IN_MEMORY` boundary;
5. builds the React frontend and runs both frontend and backend dependency
   audits in Docker;
6. runs generated backend tests during the Docker image build;
7. starts the Express backend in a network-disabled container; and
8. exercises supported GET, POST, PATCH, and DELETE operations, including
   HTTP 400 malformed-input and HTTP 404 missing-record cases.

Library contains two independent entities, `Book` and `Member`; the same
runtime smoke sequence is applied to both. API operation IDs, paths, success
statuses, schema field types, generated client paths, and manifest identities
remain derived from the shared `CrudApplicationSpec`.

## Isolation policy

The tracked runtime command applies:

- non-root UID/GID `1000:1000` and an image configured as `USER node`;
- `--network none` for runtime validation;
- a read-only root filesystem and a 32 MiB `noexec,nosuid,nodev` temporary
  filesystem;
- all Linux capabilities dropped and `no-new-privileges` enabled;
- 128-process, 256 MiB memory, 0.5 CPU, and command-time limits;
- no privileged mode, Docker socket, host-source mount, or other host mount;
- no automatic restart and no published runtime port.

The build stage uses the digest-pinned official Node 24 Debian slim image.
Direct dependencies and allowed npm scripts are exact allowlists. npm
lifecycle install scripts are disabled, and high/critical dependency-audit
findings fail the build. The build is capped at 1 GiB memory, a 128 MiB shared
memory segment, 1,024 open files, and ten minutes.

## Remaining isolation and audit limitations

- Docker Desktop and its Linux VM share host-managed infrastructure; this is
  risk reduction, not a formally verified security sandbox.
- Image pulling and npm installation/auditing require network access during
  the build. Results depend on the registry and advisory database at run time
  and are not a reproducible software-bill-of-materials attestation.
- `--ignore-scripts` blocks package lifecycle scripts, but dependency parsing,
  bundling, tests, and npm itself still process untrusted inputs inside the
  build container.
- Exact direct versions do not pin every transitive dependency because a
  generated lockfile is not yet retained as manifest evidence.
- A browser preview needs loopback port publishing and a temporary connected
  Docker network, which is intentionally outside the network-disabled
  automated runtime harness. Browser success must be reported only after an
  actual browser observation.
- Passing these checks proves the tested build and narrow HTTP behavior. It
  does not prove semantic correctness, production security, scalability,
  database persistence, C4 retesting, or deployment readiness.

## Manual browser preview (optional)

Run the harness with `--keep-images`, then start the selected image with the
same non-root/read-only/capability/resource controls, bind only loopback host
ports, serve `/app/frontend-dist` with the tracked
`docker-validation/static-server.mjs`, and set the backend CORS origin to the
exact preview URL. Inspect the list/form/navigation behavior in a real
browser. Remove only those disposable preview containers, their temporary
network, and validation images afterward.

The automated Stage 2 run does not treat an HTTP 200 response as proof of a
successful browser rendering.
