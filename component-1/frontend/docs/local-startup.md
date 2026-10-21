# Start Component 01 with one command

From the repository root:

```sh
./start-component-1
```

Azure Speech is also supported by the full backend. From its backend folder,
run `.venv/bin/python scripts/configure_azure_speech.py` and enter KEY 1 at the
hidden prompt before restarting. This selects Azure explicitly; the launcher
then checks Azure configuration instead of requiring Whisper assets. Never put
the key in frontend environment variables. Local configuration checks do not
prove cloud authentication or incur a transcription request. See the backend's
`docs/azure-speech.md` for limits, provenance and an isolated live check.

Keep that terminal open. Use the printed frontend URL (normally
http://127.0.0.1:5173); API docs are normally http://127.0.0.1:8001/docs.
Press **Ctrl+C** once to stop this launch's frontend, backend and any Ollama
process it started. MongoDB remains running with its data volume intact;
an Ollama server that was already running is left alone. The launcher never
stops an existing application occupying a port. On first use, stop the older
backend/frontend terminals with Ctrl+C, then run this command.

## What the launcher does

1. Resolves this checkout regardless of the shell's working directory; requires
   Node 22.12+ in the 22.x series and already installed frontend dependencies.
2. Uses the explicit interpreter at
   `.worktrees/component-1-backend/component-1/backend/.venv/bin/python`.
   It verifies the imported package belongs to that full backend worktree,
   avoiding the copied activation script that selects the older environment.
3. Reads existing backend settings through the backend's own Settings class.
   Main-checkout backend `.env` is the base, full-worktree `.env` overrides it,
   and shell environment variables take precedence. No `.env` is rewritten and
   no credentials/connection strings are printed. Model paths are resolved from
   the backend worktree; explicitly configured invalid paths fail, without fallback.
4. Verifies the trusted classifier loads, and that the isolated Whisper interpreter,
   checkpoint/hash, manifest and FFmpeg decoders exist. It does not load/train a
   new ASR model or download weights. The actual ASR model loads lazily on upload.
5. Pings the configured real MongoDB with a bounded timeout. For the default
   local MongoDB target only, starts Docker Desktop if necessary and starts
   `intellise-c1-mongodb`. If absent, creates the documented container using the
   already prepared `mongo:8.0` image and persistent
   `intellise-c1-mongodb-data` volume. Nothing is deleted/reset. A remote/Atlas
   failure stops startup; it never substitutes a local database for that target.
6. For the explicit local launcher profile, uses Ollama by default if no provider
   was configured. Honors an explicitly configured Ollama/Anthropic provider.
   Checks Ollama tags and starts local `ollama serve` only when its local default
   endpoint is unavailable. A missing requested model fails with preparation
   instructions; there is no automatic pull, inference request, retry or provider
   fallback. An explicit Anthropic selection requires its configured API key.
7. Starts the full backend; verifies health/projects, transcription and provenance
   OpenAPI routes and project-storage availability. Starts Vite with its actual
   backend URL and the same classifier environment/model. CORS includes the
   launch's localhost/127.0.0.1 frontend origins.

## One-time prerequisites and optional settings

This is a **startup** command, not a dependency installer. Existing dependencies
and the trained artifact are reused. If starting on another machine, follow the
backend README and `docs/audio-transcription.md` there, run `npm ci` in the
frontend, install Docker/Ollama as needed, and explicitly prepare their images
and models. The launcher gives an actionable error rather than downloading them.
For example, if the local Docker image is absent, explicitly run
`docker pull mongo:8.0` once. Never remove the named volume to fix startup.

Classifier default: the full backend's `research/models/dcai-v1/lr-c10`.
Whisper defaults prefer an existing `.venv-whisper` / `models/whisper` in the
full backend, then the main backend, then existing `/private/tmp/intellise-c1-*`
verification assets. Temporary assets emit a notice; they can disappear after
cleanup/restart. Configure durable ASR paths using `C1_WHISPER_PYTHON` and
`C1_WHISPER_MODEL_DIR` in your backend `.env` for long-term use. The classifier
environment remains separate from Whisper/PyTorch dependencies.

If MongoDB has no configured URI, this local profile uses
`mongodb://127.0.0.1:27017` with the backend's configured/default database name.
This is an explicit local-development default, never an availability fallback.
Reuse your existing database configuration to keep access to saved projects.

Overrides may be supplied in the shell, without editing source:

```sh
C1_BACKEND_PORT=8011 C1_FRONTEND_PORT=5174 ./start-component-1
```

Run only one audio-enabled backend against a database: workers are designed for
a single application instance. Different ports do not make multiple workers safe.
For a different checkout, set `C1_BACKEND_DIR` (absolute or repository-relative)
and optionally `C1_BACKEND_PYTHON` (absolute or backend-relative).

Read-only readiness checks and help:

```sh
./start-component-1 --check
./start-component-1 --help
```

`--check` never starts Docker/Ollama or the application and does not write database
records. It still needs network access to the configured services and free launch
ports. A stopped service will be reported; use a normal launch to start the
documented local services. No frontend/backend tests are run on normal startup.

## Scope and known limitations

Ready means routes, assets and storage are available, not model accuracy. Audio
must still be reviewed; original and reviewed text stay separate. Saving,
extraction and classification require explicit UI actions. The baseline is
TF-IDF/logistic regression with within-corpus evaluation, not BERT or a confidence
guarantee. The known Ollama relevance/exact-source failures remain research work.
This local launcher does not provide production supervision, model downloads,
TLS, database migrations or a multi-worker transcription queue.
