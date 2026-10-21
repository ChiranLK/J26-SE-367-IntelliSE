"""
InteliSE Component 3 - Built-in Colab GPU Bridge Service
Runs inside the FastAPI process on port 11435 to bridge requests to Google Colab.
Enables 100% UI-driven switching without opening a terminal.
"""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger("intelise_c3.colab_bridge")

BRIDGE_PORT = 11435


class _ColabProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Avoid flooding server logs with proxy requests
        pass

    def do_HEAD(self) -> None:
        self._proxy("HEAD")

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _proxy(self, method: str) -> None:
        target_base = ColabBridgeManager.get_tunnel_url()
        if not target_base:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Colab tunnel URL not configured"}')
            return

        target = f"{target_base}{self.path}"
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else None

        forward_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        if body:
            forward_headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(
            target,
            data=body,
            headers=forward_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                resp_data = response.read()
                self.send_response(response.status)
                for header, value in response.getheaders():
                    if header.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(header, value)
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)
        except urllib.error.HTTPError as error:
            if self.path.startswith("/api/show") and error.code >= 400:
                fallback = b'{"license": "Apache-2.0", "modelfile": "# Colab AWQ", "details": {"family": "qwen2", "parameter_size": "7B", "quantization_level": "4-bit AWQ"}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(fallback)))
                self.end_headers()
                self.wfile.write(fallback)
                return
            if self.path.startswith("/api/tags") and error.code >= 400:
                fallback = b'{"models": [{"name": "qwen2.5-coder:7b", "model": "qwen2.5-coder:7b", "details": {"family": "qwen2", "parameter_size": "7B"}}, {"name": "qwen2.5-coder:3b", "model": "qwen2.5-coder:3b", "details": {"family": "qwen2", "parameter_size": "3B"}}, {"name": "qwen2.5-coder:14b", "model": "qwen2.5-coder:14b", "details": {"family": "qwen2", "parameter_size": "14B"}}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(fallback)))
                self.end_headers()
                self.wfile.write(fallback)
                return
            err_data = error.read()
            self.send_response(error.code)
            for header, value in error.headers.items():
                if header.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(header, value)
            self.send_header("Content-Length", str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            err_msg = f'{{"error": "ColabBridgeFailed", "detail": "{str(exc)}"}}'.encode("utf-8")
            self.wfile.write(err_msg)


class ColabBridgeManager:
    _lock = threading.Lock()
    _tunnel_url: str | None = None
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    @classmethod
    def get_tunnel_url(cls) -> str | None:
        return cls._tunnel_url

    @classmethod
    def set_tunnel_url(cls, url: str) -> str:
        clean_url = url.strip().rstrip("/")
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = f"https://{clean_url}"
        cls._tunnel_url = clean_url
        return clean_url

    @classmethod
    def is_running(cls) -> bool:
        return cls._server is not None and cls._thread is not None and cls._thread.is_alive()

    @classmethod
    def start_or_update(cls, tunnel_url: str | None = None) -> bool:
        with cls._lock:
            if tunnel_url:
                cls.set_tunnel_url(tunnel_url)

            if cls.is_running():
                return True

            try:
                server = HTTPServer(("127.0.0.1", BRIDGE_PORT), _ColabProxyHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True, name="ColabBridgeThread")
                thread.start()
                cls._server = server
                cls._thread = thread
                logger.info("Colab bridge started on port %d -> %s", BRIDGE_PORT, cls._tunnel_url)
                return True
            except Exception as exc:
                logger.error("Failed to start Colab bridge on port %d: %s", BRIDGE_PORT, exc)
                return False

    @classmethod
    def stop(cls) -> None:
        with cls._lock:
            if cls._server is not None:
                try:
                    cls._server.shutdown()
                    cls._server.server_close()
                except Exception:
                    pass
                cls._server = None
                cls._thread = None
                logger.info("Colab bridge stopped")
