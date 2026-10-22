"""LOCAL_SANDBOX_PREVIEW of a hybrid run: disposable Docker containers, never a deployment.

Topology per preview (all names carry the preview id and the label
``intelise.c3.hybrid-preview``):

* ``<id>-db``  PostgreSQL 16, uid 70, tmpfs storage, attached ONLY to an
  ``--internal`` network (no egress, never published).
* ``<id>-api`` generated Node backend, uid 1000, read-only root, published on
  ``127.0.0.1:<api_port>``; attached to the edge network and the internal db network.
* ``<id>-web`` generated React bundle behind a static server, uid 1000,
  published on ``127.0.0.1:<ui_port>``.

Ports are allocated dynamically and never equal the C3 dashboard/API ports.
No Docker socket, host-source bind mount or privileged mode is used. URLs are
returned only after HTTP health checks pass. State is reconstructed from
container labels, so a C3 restart can still list and stop running previews.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
from typing import Any
from uuid import uuid4

import httpx
from fastapi import status

from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.hybrid.pipeline import EVIDENCE_DIR, PROJECT_DIR, HybridPipeline

# APPLICATION PREVIEW SETTINGS
# These values control the temporary Docker preview, reserved ports, timeouts,
# and the known GPA request used to confirm that the generated app works.
PREVIEW_ROOT = COMPONENT_ROOT / "runtime" / "hybrid-preview"
LABEL = "intelise.c3.hybrid-preview"
DATABASE_IMAGE = "postgres:16-alpine"
RESERVED_PORTS = frozenset({8000, 5173, 5174, 5175, 3001, 8080, 5432})
BUILD_TIMEOUT = 900
HEALTH_TIMEOUT = 150
EXECUTION_LABEL = "LOCAL_SANDBOX_PREVIEW_NOT_DEPLOYED"
KNOWN_GPA_CHECK = {
    "modules": [
        {"moduleCode": "IT1010", "credits": 4, "grade": "A", "countsTowardGpa": True},
        {"moduleCode": "IT1020", "credits": 3, "grade": "B+", "countsTowardGpa": True},
        {"moduleCode": "IT1030", "credits": 2, "grade": "C", "countsTowardGpa": True},
        {"moduleCode": "IT1040", "credits": 3, "grade": "A-", "countsTowardGpa": True},
    ],
    "expected_gpa_text": "3.42",
    "derivation": "(4x4.0 + 3x3.3 + 2x2.0 + 3x3.7) / 12 = 41.0 / 12 = 3.4166... -> 3.42 (HALF_UP, 2 dp)",
}
Runner = Callable[..., subprocess.CompletedProcess]


# APPLICATION PREVIEW ERROR
# Creates one standard API error for preview-related failures.
def _error(code: str, message: str, status_code: int = status.HTTP_409_CONFLICT) -> ApplicationError:
    return ApplicationError([ErrorDetail(code=code, field="preview", message=message)], status_code=status_code)


# CURRENT UTC TIME
# Adds a consistent timestamp to preview records and Docker labels.
def _now() -> str:
    return datetime.now(UTC).isoformat()


# FREE LOCAL PORT SELECTION
# Finds an unused localhost port without using ports reserved by Component 3.
def free_loopback_port(exclude: set[int]) -> int:
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port not in exclude and port not in RESERVED_PORTS:
            return port
    raise _error("NO_FREE_PORT", "Could not allocate a free loopback port.", status.HTTP_503_SERVICE_UNAVAILABLE)


# APPLICATION PREVIEW SERVICE
# Builds and runs the generated frontend, backend, and PostgreSQL database
# inside temporary local Docker containers. This is a preview, not deployment.
class HybridPreviewService:
    # PREVIEW SERVICE DEPENDENCIES
    # Stores the generation pipeline, Docker runner, HTTP clients, and timeout.
    def __init__(self, pipeline: HybridPipeline, *, runner: Runner = subprocess.run, http_get=None, http_post=None,
                 health_timeout: float = HEALTH_TIMEOUT) -> None:
        self._pipeline = pipeline
        self._run = runner
        self._get = http_get or (lambda url: httpx.get(url, timeout=3.0))
        self._post = http_post or (lambda url, body: httpx.post(url, json=body, timeout=10.0))
        self._health_timeout = health_timeout

    # DOCKER COMMAND RUNNER
    # Runs a Docker command and converts missing Docker, timeouts, or failures
    # into clear preview API errors.
    def _docker(self, *args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = self._run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as error:
            raise _error("DOCKER_UNAVAILABLE", "The docker CLI was not found on this host.", status.HTTP_503_SERVICE_UNAVAILABLE) from error
        except subprocess.TimeoutExpired as error:
            raise _error("DOCKER_TIMEOUT", f"docker {args[0]} exceeded {timeout}s.", status.HTTP_504_GATEWAY_TIMEOUT) from error
        if check and result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-6:]
            raise _error("DOCKER_COMMAND_FAILED", f"docker {args[0]} failed: {' | '.join(tail)}", status.HTTP_502_BAD_GATEWAY)
        return result

    # DOCKER AVAILABILITY CHECK
    # Confirms that the Docker CLI and Docker daemon are ready before preview.
    def docker_available(self) -> dict[str, Any]:
        try:
            result = self._docker("version", "--format", "{{.Server.Version}}", timeout=20, check=False)
        except ApplicationError as error:
            return {"available": False, "reason": error.errors[0].message}
        if result.returncode != 0:
            return {"available": False, "reason": (result.stderr or "docker daemon unreachable").strip()[-300:]}
        return {"available": True, "server_version": result.stdout.strip()}

    # PREVIEW CLEANUP
    # Removes the three preview containers and their two Docker networks.
    def _cleanup(self, preview_id: str) -> None:
        for suffix in ("web", "api", "db"):
            self._docker("rm", "-f", f"{preview_id}-{suffix}", check=False)
        for suffix in ("edge", "dbnet"):
            self._docker("network", "rm", f"{preview_id}-{suffix}", check=False)

    # CONTAINER ERROR LOGS
    # Reads the latest container logs to explain a failed preview start.
    def _log_tail(self, container: str) -> str:
        result = self._docker("logs", "--tail", "40", container, check=False)
        return ((result.stdout or "") + (result.stderr or ""))[-3000:]

    # PREVIEW AUDIT RECORD
    # Saves preview start, failure, check, and stop events with the generation run.
    def _record(self, run_id: str, event: dict[str, Any]) -> None:
        try:
            run_dir, _ = self._pipeline.find_run(run_id)
        except ApplicationError:
            return
        with (run_dir / EVIDENCE_DIR / "preview-events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    # PREPARE VERIFIED BUILD CONTEXT
    # Copies only the generated files listed in the verified manifest into a
    # temporary Docker build folder. The original generated source stays unchanged.
    def _prepare_context(self, run_dir: Path, manifest: dict[str, Any], preview_id: str) -> Path:
        context = PREVIEW_ROOT / preview_id / "context"
        if context.exists():
            shutil.rmtree(context)
        for record in manifest["files"]:
            source = run_dir / PROJECT_DIR / record["path"]
            target = context / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (context / ".dockerignore").write_text("**/node_modules\n**/dist\n", encoding="utf-8")
        return context

    # WAIT FOR THE APPLICATION TO BECOME HEALTHY
    # Repeatedly checks that the API, PostgreSQL connection, and frontend are ready.
    def _wait_healthy(self, api_url: str, ui_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._health_timeout
        api_ok = ui_ok = False
        api_body: Any = None
        last_error = ""
        while time.monotonic() < deadline and not (api_ok and ui_ok):
            try:
                if not api_ok:
                    response = self._get(f"{api_url}/api/health")
                    api_body = response.json() if response.status_code == 200 else None
                    api_ok = bool(api_body and api_body.get("status") == "UP" and api_body.get("database") == "UP")
                if not ui_ok:
                    response = self._get(f"{ui_url}/")
                    ui_ok = response.status_code == 200 and 'id="root"' in response.text
            except Exception as error:  # noqa: BLE001 - connection refused while containers start
                last_error = type(error).__name__
            if not (api_ok and ui_ok):
                time.sleep(1.0)
        return {"api_healthy": api_ok, "api_health_body": api_body, "frontend_healthy": ui_ok,
                "checked_at_utc": _now(), "last_error": last_error or None}

    # START APPLICATION PREVIEW
    # Verifies the generated project, builds its images, starts all containers,
    # checks their health, and returns local preview URLs.
    def start(self, run_id: str) -> dict[str, Any]:
        # Confirm Docker is available before doing any preview work.
        availability = self.docker_available()
        if not availability["available"]:
            raise _error("DOCKER_UNAVAILABLE", f"Docker is not available: {availability['reason']}", status.HTTP_503_SERVICE_UNAVAILABLE)
        # Load the generation run and confirm its files still match the manifest.
        run_dir, manifest = self._pipeline.find_run(run_id)
        problems = self._pipeline.verify_run_files(run_dir, manifest)
        if problems:
            raise _error("ARTIFACT_INTEGRITY_FAILED", f"Run files no longer match the manifest: {problems[:3]}")
        # Reject failed runs or runs that do not contain Docker deployment files.
        if manifest["status"].startswith("REJECTED"):
            raise _error("RUN_NOT_PREVIEWABLE", f"Run status {manifest['status']} cannot be previewed.")
        if not any(r["path"] == "deployment/backend.Dockerfile" for r in manifest["files"]):
            raise _error("RUN_NOT_PREVIEWABLE", "The run has no deployment module.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        # Create a unique preview ID and two free localhost ports.
        preview_id = f"ihp-{uuid4().hex[:10]}"
        api_port = free_loopback_port(set())
        ui_port = free_loopback_port({api_port})
        api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
        # Create reusable image names and labels for finding the preview later.
        digest = manifest["artifact_digest_sha256"][:12]
        backend_image = f"intelise-c3-hybrid-api:{digest}"
        frontend_image = f"intelise-c3-hybrid-web:{digest}-{api_port}"
        labels = [
            "--label", f"{LABEL}={preview_id}", "--label", f"intelise.c3.run={run_id}",
            "--label", f"intelise.c3.artifact={manifest['artifact_digest_sha256']}",
            "--label", f"intelise.c3.api-port={api_port}", "--label", f"intelise.c3.ui-port={ui_port}",
            "--label", f"intelise.c3.started={_now()}",
        ]
        # Apply container security limits and create a temporary database password.
        hardening = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--pids-limit", "128", "--restart", "no"]
        password = secrets.token_urlsafe(24)
        started = time.monotonic()
        try:
            # BUILD FRONTEND AND BACKEND DOCKER IMAGES
            # Build both images from the verified generated project files.
            context = self._prepare_context(run_dir, manifest, preview_id)
            self._docker("build", "-f", str(context / "deployment/backend.Dockerfile"), "-t", backend_image,
                         "--label", f"{LABEL}-image=api", str(context), timeout=BUILD_TIMEOUT)
            self._docker("build", "-f", str(context / "deployment/frontend.Dockerfile"), "-t", frontend_image,
                         "--build-arg", f"VITE_API_BASE_URL={api_url}", "--label", f"{LABEL}-image=web", str(context),
                         timeout=BUILD_TIMEOUT)

            # CREATE ISOLATED DOCKER NETWORKS
            # The database network is internal. The edge network connects the
            # browser-facing frontend and backend without exposing PostgreSQL.
            self._docker("network", "create", "--internal", "--label", f"{LABEL}={preview_id}", f"{preview_id}-dbnet")
            self._docker("network", "create", "--label", f"{LABEL}={preview_id}", f"{preview_id}-edge")

            # START POSTGRESQL DATABASE CONTAINER
            # PostgreSQL stores generated app data during this preview session.
            # Its tmpfs data is disposable and disappears when the preview stops.
            self._docker("run", "-d", "--name", f"{preview_id}-db", "--network", f"{preview_id}-dbnet", *labels, *hardening,
                         "--user", "70:70", "--memory", "256m",
                         "--tmpfs", "/var/lib/postgresql/data:rw,uid=70,gid=70,mode=0700",
                         "--tmpfs", "/var/run/postgresql:rw,uid=70,gid=70",
                         "-e", "POSTGRES_USER=gpa", "-e", "POSTGRES_DB=gpa", "-e", f"POSTGRES_PASSWORD={password}",
                         "--health-cmd", "pg_isready -U gpa -d gpa", "--health-interval", "2s", "--health-retries", "30",
                         DATABASE_IMAGE)

            # START NODE.JS BACKEND CONTAINER
            # The API receives browser requests and uses the private PostgreSQL
            # container for generated application data.
            self._docker("create", "--name", f"{preview_id}-api", "--network", f"{preview_id}-edge", *labels, *hardening,
                         "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp", "--memory", "256m", "--cpus", "0.5",
                         "-p", f"127.0.0.1:{api_port}:3001",
                         "-e", f"PGHOST={preview_id}-db", "-e", "PGUSER=gpa", "-e", "PGDATABASE=gpa",
                         "-e", f"PGPASSWORD={password}", "-e", f"CORS_ALLOWED_ORIGIN={ui_url}", "-e", "PERSISTENCE=postgres",
                         backend_image)
            self._docker("network", "connect", f"{preview_id}-dbnet", f"{preview_id}-api")
            self._docker("start", f"{preview_id}-api")

            # START REACT FRONTEND CONTAINER
            # Serves the generated user interface on a localhost-only port.
            self._docker("run", "-d", "--name", f"{preview_id}-web", "--network", f"{preview_id}-edge", *labels, *hardening,
                         "--user", "1000:1000", "--read-only", "--memory", "128m", "--cpus", "0.25",
                         "-p", f"127.0.0.1:{ui_port}:8080", frontend_image)
        except ApplicationError as error:
            # If startup fails, save useful logs and remove partial containers.
            logs = {suffix: self._log_tail(f"{preview_id}-{suffix}") for suffix in ("db", "api", "web")}
            self._cleanup(preview_id)
            event = {"event": "PREVIEW_FAILED", "preview_id": preview_id, "run_id": run_id, "at_utc": _now(),
                     "error": error.errors[0].message, "container_logs": logs}
            self._record(run_id, event)
            raise

        # HEALTH CHECK AFTER STARTUP
        # Do not return preview URLs until the frontend, API, and database work.
        health = self._wait_healthy(api_url, ui_url)
        if not (health["api_healthy"] and health["frontend_healthy"]):
            # Remove an unhealthy preview and keep evidence explaining the failure.
            logs = {suffix: self._log_tail(f"{preview_id}-{suffix}") for suffix in ("db", "api", "web")}
            self._cleanup(preview_id)
            self._record(run_id, {"event": "PREVIEW_UNHEALTHY", "preview_id": preview_id, "run_id": run_id,
                                  "at_utc": _now(), "health": health, "container_logs": logs})
            raise _error("PREVIEW_UNHEALTHY",
                         f"Containers started but health checks failed (api={health['api_healthy']}, "
                         f"frontend={health['frontend_healthy']}); the preview was removed. See preview-events.jsonl.",
                         status.HTTP_502_BAD_GATEWAY)

        # Return the healthy preview details and record the successful start.
        session = self.status(preview_id)
        session["health"] = health
        session["startup_seconds"] = round(time.monotonic() - started, 1)
        self._record(run_id, {"event": "PREVIEW_STARTED", "preview_id": preview_id, "run_id": run_id, "at_utc": _now(),
                              "frontend_url": ui_url, "api_url": api_url, "health": health,
                              "startup_seconds": session["startup_seconds"]})
        return session

    # FIND PREVIEW CONTAINERS
    # Uses Docker labels to find one preview or every preview after an API restart.
    def _containers(self, preview_id: str | None = None) -> list[dict[str, Any]]:
        selector = f"label={LABEL}={preview_id}" if preview_id else f"label={LABEL}"
        result = self._docker("ps", "-a", "--filter", selector, "--format", "{{json .}}", check=False)
        rows = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    # PREVIEW STATUS
    # Reports container state, local URLs, artifact identity, and security controls.
    def status(self, preview_id: str) -> dict[str, Any]:
        rows = self._containers(preview_id)
        if not rows:
            return {"preview_id": preview_id, "status": "STOPPED", "execution": EXECUTION_LABEL, "containers": []}
        labels = dict(item.split("=", 1) for item in rows[0].get("Labels", "").split(",") if "=" in item)
        containers = [{"name": row.get("Names"), "state": row.get("State"), "status": row.get("Status")} for row in rows]
        running = all(row.get("State") == "running" for row in rows) and len(rows) == 3
        api_port, ui_port = labels.get("intelise.c3.api-port"), labels.get("intelise.c3.ui-port")
        return {
            "preview_id": preview_id,
            "status": "RUNNING" if running else "DEGRADED",
            "execution": EXECUTION_LABEL,
            "generation_run_id": labels.get("intelise.c3.run"),
            "artifact_digest_sha256": labels.get("intelise.c3.artifact"),
            "frontend_url": f"http://127.0.0.1:{ui_port}" if running else None,
            "api_url": f"http://127.0.0.1:{api_port}" if running else None,
            "api_health_url": f"http://127.0.0.1:{api_port}/api/health" if running else None,
            "started_at_utc": labels.get("intelise.c3.started"),
            "containers": containers,
            "container_name": f"{preview_id}-web / {preview_id}-api / {preview_id}-db",
            "database_exposure": "NOT_PUBLISHED (internal Docker network only)",
            "isolation": ["non-root users", "loopback-only published ports", "no Docker socket mount", "no privileged mode",
                          "no host-source bind mounts", "cap-drop ALL", "no-new-privileges", "read-only app filesystems",
                          "database on an --internal network", "ephemeral database credentials (not recorded)"],
        }

    # PREVIEW HEALTH CHECK
    # Returns current frontend, backend, and database health for a running preview.
    def health(self, preview_id: str) -> dict[str, Any]:
        session = self.status(preview_id)
        if session["status"] != "RUNNING":
            return {**session, "health": {"api_healthy": False, "frontend_healthy": False}}
        return {**session, "health": self._wait_once(session["api_url"], session["frontend_url"])}

    # SINGLE HEALTH REQUEST
    # Performs one immediate API and frontend check without the startup retry loop.
    def _wait_once(self, api_url: str, ui_url: str) -> dict[str, Any]:
        result: dict[str, Any] = {"checked_at_utc": _now()}
        try:
            response = self._get(f"{api_url}/api/health")
            result["api_health_body"] = response.json()
            result["api_healthy"] = response.status_code == 200 and result["api_health_body"].get("database") == "UP"
        except Exception as error:  # noqa: BLE001
            result["api_healthy"], result["api_error"] = False, type(error).__name__
        try:
            response = self._get(f"{ui_url}/")
            result["frontend_healthy"] = response.status_code == 200
        except Exception as error:  # noqa: BLE001
            result["frontend_healthy"], result["frontend_error"] = False, type(error).__name__
        return result

    # KNOWN GPA SMOKE CHECK
    # Sends a known GPA example to the generated API and compares the returned
    # value with the expected result. This is a quick preview check, not C4 evidence.
    def gpa_check(self, preview_id: str) -> dict[str, Any]:
        session = self.status(preview_id)
        if session["status"] != "RUNNING":
            raise _error("PREVIEW_NOT_RUNNING", f"Preview {preview_id} is not running.")
        response = self._post(f"{session['api_url']}/api/v1/gpa/calculations", {"modules": KNOWN_GPA_CHECK["modules"]})
        body = response.json()
        observed = body.get("gpaText") if isinstance(body, dict) else None
        result = {
            "classification": "C3_GENERATED_APP_SMOKE_CHECK (not Component 4 evidence)",
            "request_modules": KNOWN_GPA_CHECK["modules"],
            "derivation": KNOWN_GPA_CHECK["derivation"],
            "expected_gpa_text": KNOWN_GPA_CHECK["expected_gpa_text"],
            "observed_http_status": response.status_code,
            "observed_gpa_text": observed,
            "observed_policy": f"{body.get('policyId')} v{body.get('policyVersion')} ({body.get('policyAuthorityStatus')})" if isinstance(body, dict) else None,
            "passed": response.status_code == 201 and observed == KNOWN_GPA_CHECK["expected_gpa_text"],
            "checked_at_utc": _now(),
        }
        if session.get("generation_run_id"):
            self._record(session["generation_run_id"], {"event": "PREVIEW_GPA_CHECK", "preview_id": preview_id, **result})
        return result

    # STOP APPLICATION PREVIEW
    # Removes the disposable containers, networks, and temporary build context.
    def stop(self, preview_id: str) -> dict[str, Any]:
        before = self.status(preview_id)
        self._cleanup(preview_id)
        shutil.rmtree(PREVIEW_ROOT / preview_id, ignore_errors=True)
        after = self.status(preview_id)
        if before.get("generation_run_id"):
            self._record(before["generation_run_id"], {"event": "PREVIEW_STOPPED", "preview_id": preview_id, "at_utc": _now(),
                                                       "remaining_containers": len(after["containers"])})
        return {**after, "removed_containers": [c["name"] for c in before["containers"]]}

    # LIST RUNNING PREVIEWS
    # Finds preview IDs from Docker labels and returns the status of each preview.
    def list(self) -> list[dict[str, Any]]:
        ids = sorted({dict(item.split("=", 1) for item in row.get("Labels", "").split(",") if "=" in item).get(LABEL)
                      for row in self._containers()} - {None})
        return [self.status(preview_id) for preview_id in ids]
