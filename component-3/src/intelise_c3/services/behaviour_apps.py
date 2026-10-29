"""Start/stop behaviour-generated apps on fresh loopback ports (explicit researcher action).

Before starting, every file is re-hashed against ``behaviour-manifest.json`` so a
tampered workspace never runs. The React frontend is built once from the verified
``frontend/`` folder into ``runtime/behaviour-apps/builds/<run>/dist`` (``npm install
--ignore-scripts`` + ``vite build``, outside the workspace). The backend then runs as
``node --permission`` with read access only inside its own workspace and that build
folder (no file writes, child processes or workers), bound to 127.0.0.1 on a free
port. Output goes to a log file under the gitignored ``runtime/`` folder.
"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import subprocess
import threading
import time
import urllib.request

from fastapi import status

from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.behaviour import BehaviourAppSession, BehaviourManifest
from intelise_c3.generation.behaviour_validation import node_permission_args
from intelise_c3.services.behaviour_generation import BEHAVIOUR_WORKSPACE_DIR

_STARTUP_SECONDS = 15
_INSTALL_SECONDS = 300
_BUILD_SECONDS = 180
#: Only what npm and Windows need; nothing else from the backend's environment reaches the build.
_BUILD_ENV_KEYS = ("PATH", "SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME", "ProgramData", "ComSpec")


def _fail(code: str, field: str, message: str, status_code: int) -> None:
    raise ApplicationError([ErrorDetail(code=code, field=field, message=message)], status_code=status_code)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class BehaviourAppRunner:
    _lock = threading.Lock()
    _processes: dict[str, tuple[subprocess.Popen, BehaviourAppSession]] = {}

    def __init__(self, workspace_root: Path, log_root: Path, *, build_frontend: bool = True) -> None:
        self._root = workspace_root.resolve()
        self._log_root = log_root
        self._build_frontend_enabled = build_frontend

    def _resolve(self, relative: str) -> tuple[Path, BehaviourManifest]:
        path = PurePosixPath(relative)
        if (
            "\\" in relative
            or path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != BEHAVIOUR_WORKSPACE_DIR
            or path.as_posix() != relative
        ):
            _fail("UNSAFE_WORKSPACE_PATH", "workspace_relative_path", "Expected a behaviour/<name>/<run> path.", status.HTTP_422_UNPROCESSABLE_CONTENT)
        run_dir = self._root.joinpath(*path.parts).resolve()
        manifest_path = run_dir / "behaviour-manifest.json"
        if not run_dir.is_relative_to(self._root) or not manifest_path.is_file():
            _fail("BEHAVIOUR_WORKSPACE_NOT_FOUND", "workspace_relative_path", "No behaviour workspace with a manifest exists there.", status.HTTP_404_NOT_FOUND)
        manifest = BehaviourManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        for record in manifest.files:
            target = run_dir.joinpath(*PurePosixPath(record.relative_path).parts)
            if not target.is_file() or sha256(target.read_bytes()).hexdigest() != record.sha256:
                _fail(
                    "BEHAVIOUR_WORKSPACE_TAMPERED",
                    "workspace_relative_path",
                    f"'{record.relative_path}' does not match its manifest hash; the app is not started.",
                    status.HTTP_409_CONFLICT,
                )
        return run_dir, manifest

    def workspace(self, relative: str) -> tuple[Path, BehaviourManifest]:
        """Hash-verified run directory and manifest (raises on a tampered workspace)."""
        return self._resolve(relative)

    def _build_frontend(self, run_dir: Path, manifest: BehaviourManifest) -> Path:
        """Build the verified React frontend into a folder outside the workspace; reused on later starts."""
        build_dir = self._log_root / "builds" / manifest.generation_run_id
        dist = build_dir / "dist"
        if (dist / "index.html").is_file():
            return dist
        npm = shutil.which("npm")
        if npm is None:
            _fail("NPM_NOT_FOUND", "npm", "npm is not on PATH; the React frontend cannot be built.", status.HTTP_503_SERVICE_UNAVAILABLE)
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.copytree(run_dir / "frontend", build_dir)
        env = {key: os.environ[key] for key in _BUILD_ENV_KEYS if key in os.environ}
        for label, args, seconds in (
            ("npm install", ["install", "--ignore-scripts", "--no-audit", "--no-fund"], _INSTALL_SECONDS),
            ("vite build", ["run", "build"], _BUILD_SECONDS),
        ):
            try:
                result = subprocess.run(
                    [npm, *args],
                    cwd=build_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=seconds,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired:
                shutil.rmtree(build_dir, ignore_errors=True)
                _fail("BEHAVIOUR_FRONTEND_BUILD_TIMEOUT", "frontend", f"{label} did not finish within {seconds} s.", status.HTTP_504_GATEWAY_TIMEOUT)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "")[-300:].strip()
                shutil.rmtree(build_dir, ignore_errors=True)
                _fail("BEHAVIOUR_FRONTEND_BUILD_FAILED", "frontend", f"{label} failed: {tail}", status.HTTP_502_BAD_GATEWAY)
        return dist

    def start(self, relative: str) -> BehaviourAppSession:
        run_dir, manifest = self._resolve(relative)
        node = shutil.which("node")
        if node is None:
            _fail("NODE_NOT_FOUND", "node", "Node.js is not on PATH; the behaviour app cannot start.", status.HTTP_503_SERVICE_UNAVAILABLE)
        # The (slow, first-time) frontend build runs outside the lock so other requests are not blocked by it.
        dist = self._build_frontend(run_dir, manifest) if self._build_frontend_enabled else run_dir / "frontend" / "dist"
        with self._lock:
            existing = self._processes.get(relative)
            if existing and existing[0].poll() is None:
                return existing[1]
            port = _free_port()
            self._log_root.mkdir(parents=True, exist_ok=True)
            log_path = self._log_root / f"{manifest.generation_run_id}.log"
            log = log_path.open("wb")
            process = subprocess.Popen(
                [
                    node,
                    *node_permission_args(run_dir, dist),
                    str(run_dir / "backend" / "server.mjs"),
                    "--port",
                    str(port),
                    "--static",
                    str(dist),
                ],
                cwd=run_dir / "backend",
                stdout=log,
                stderr=subprocess.STDOUT,
                env={"PATH": os.environ.get("PATH", ""), "SystemRoot": os.environ.get("SystemRoot", "")},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            url = f"http://127.0.0.1:{port}/"
            deadline = time.monotonic() + _STARTUP_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(f"{url}api/state", timeout=1) as response:
                        if response.status == 200:
                            session = BehaviourAppSession(
                                workspace_relative_path=relative,
                                generation_run_id=manifest.generation_run_id,
                                status="RUNNING",
                                url=url,
                                port=port,
                                pid=process.pid,
                            )
                            self._processes[relative] = (process, session)
                            return session
                except OSError:
                    time.sleep(0.3)
            process.kill()
            log.close()
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-400:]
            error_line = next((line for line in tail.splitlines() if "Error" in line), "no error line in the log")
            _fail("BEHAVIOUR_APP_START_FAILED", "workspace_relative_path", f"The app did not start: {error_line[:200]}", status.HTTP_502_BAD_GATEWAY)

    def stop(self, relative: str) -> BehaviourAppSession:
        with self._lock:
            entry = self._processes.pop(relative, None)
        if entry is None:
            _, manifest = self._resolve(relative)
            return BehaviourAppSession(workspace_relative_path=relative, generation_run_id=manifest.generation_run_id, status="STOPPED")
        process, session = entry
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return session.model_copy(update={"status": "STOPPED", "pid": None})

    def list(self) -> tuple[BehaviourAppSession, ...]:
        with self._lock:
            return tuple(
                session if process.poll() is None else session.model_copy(update={"status": "STOPPED"})
                for process, session in self._processes.values()
            )
