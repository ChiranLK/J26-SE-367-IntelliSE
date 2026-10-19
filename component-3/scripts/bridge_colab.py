"""
InteliSE Component 3 - Colab GPU Reverse Bridge
Connects local Component 3 to a remote Google Colab GPU tunnel.
Default local port: 11435 (avoids conflicting with local Ollama on 11434).

Usage:
    python scripts/bridge_colab.py https://your-tunnel-url.trycloudflare.com [--port 11435] [--no-switch]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = COMPONENT_ROOT / ".env"


def parse_args():
    parser = argparse.ArgumentParser(description="InteliSE Component 3 - Colab GPU Reverse Bridge")
    parser.add_argument("url", nargs="?", default="", help="Colab Tunnel URL (e.g. https://...trycloudflare.com)")
    parser.add_argument("--port", type=int, default=11435, help="Local port to listen on (default: 11435)")
    parser.add_argument("--no-switch", action="store_true", help="Do not update .env configuration")
    return parser.parse_args()


ARGS = parse_args()


def get_target_url() -> str:
    url = ARGS.url.strip()
    if not url:
        print("=" * 60)
        print("InteliSE Component 3 - Google Colab Bridge")
        print("=" * 60)
        url = input("Enter your Colab Tunnel URL (e.g. https://...trycloudflare.com): ").strip()

    url = url.rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url


COLAB_TARGET_URL = get_target_url()
PORT = ARGS.port


def update_env(updates: dict[str, str]) -> None:
    lines = []
    keys_found = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in updates:
                    lines.append(f"{k}={updates[k]}")
                    keys_found.add(k)
                    continue
            lines.append(line)

    for k, v in updates.items():
        if k not in keys_found:
            lines.append(f"{k}={v}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def notify_backend_reload() -> None:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/demo/engine-reload",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            pass
    except Exception:
        pass


class ColabProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(
            f"[ColabBridge] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n"
        )

    def do_HEAD(self):
        self._proxy("HEAD")

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _proxy(self, method: str):
        target = f"{COLAB_TARGET_URL}{self.path}"
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


def main():
    print(f"\n[ColabBridge] Local endpoint:  http://127.0.0.1:{PORT}")
    print(f"[ColabBridge] Remote endpoint: {COLAB_TARGET_URL}")

    if not ARGS.no_switch:
        print(f"[ColabBridge] Auto-switching .env to Colab GPU (http://127.0.0.1:{PORT}, qwen2.5-coder:7b)...")
        update_env({
            "OLLAMA_BASE_URL": f"http://127.0.0.1:{PORT}",
            "OLLAMA_MODEL": "qwen2.5-coder:7b",
        })
        notify_backend_reload()

    print("[ColabBridge] Ready! Component 3 will route LLM requests through Colab GPU.\n")
    print("[ColabBridge] Press Ctrl+C to stop and revert to Local 3B model.\n")

    server = HTTPServer(("127.0.0.1", PORT), ColabProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ColabBridge] Stopping bridge...")
        server.server_close()
        if not ARGS.no_switch:
            print("[ColabBridge] Restoring .env to Local 3B model (http://127.0.0.1:11434, qwen2.5-coder:3b)...")
            update_env({
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                "OLLAMA_MODEL": "qwen2.5-coder:3b",
            })
            notify_backend_reload()
            print("[ColabBridge] Restored to Local 3B successfully.")


if __name__ == "__main__":
    main()
