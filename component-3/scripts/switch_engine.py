"""
InteliSE Component 3 - Inference Engine Switcher
Switches seamlessly between Local Machine (qwen2.5-coder:3b) and Google Colab GPU (qwen2.5-coder:7b).

Usage:
    python scripts/switch_engine.py status
    python scripts/switch_engine.py local
    python scripts/switch_engine.py colab [colab_tunnel_url]
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = COMPONENT_ROOT / ".env"

LOCAL_PORT = 11434
COLAB_PORT = 11435

LOCAL_MODEL = "qwen2.5-coder:3b"
COLAB_MODEL = "qwen2.5-coder:7b"


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    data = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip()
    return data


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


def probe_endpoint(port: int) -> tuple[bool, list[str]]:
    url = f"http://127.0.0.1:{port}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "InteliSE-Switcher"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
            return True, models
    except Exception:
        return False, []


def notify_backend_reload() -> bool:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/demo/engine-reload",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def cmd_status() -> None:
    env = read_env()
    current_url = env.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    current_model = env.get("OLLAMA_MODEL", "qwen2.5-coder:3b")

    local_ok, local_models = probe_endpoint(LOCAL_PORT)
    colab_ok, colab_models = probe_endpoint(COLAB_PORT)

    is_local = "11434" in current_url
    is_colab = "11435" in current_url

    print("=" * 60)
    print("InteliSE Component 3 - Inference Engine Status")
    print("=" * 60)
    print(f"Active Engine:        {'LOCAL (Machine)' if is_local else ('COLAB (Cloud GPU)' if is_colab else 'CUSTOM')}")
    print(f"Active Base URL:      {current_url}")
    print(f"Active Model:         {current_model}")
    print("-" * 60)
    print(f"1. Local Ollama (port {LOCAL_PORT}):")
    if local_ok:
        print(f"   Status:   REACHABLE")
        print(f"   Models:   {', '.join(local_models) if local_models else 'None'}")
    else:
        print(f"   Status:   NOT RUNNING (Run 'ollama serve' if needed)")

    print(f"\n2. Colab Bridge (port {COLAB_PORT}):")
    if colab_ok:
        print(f"   Status:   REACHABLE")
        print(f"   Models:   {', '.join(colab_models) if colab_models else 'Proxy connected'}")
    else:
        print(f"   Status:   NOT RUNNING (Run 'python scripts/bridge_colab.py <url>' to connect)")
    print("=" * 60)


def cmd_local() -> None:
    print("[Switcher] Switching to LOCAL machine engine (qwen2.5-coder:3b)...")
    update_env({
        "OLLAMA_BASE_URL": f"http://127.0.0.1:{LOCAL_PORT}",
        "OLLAMA_MODEL": LOCAL_MODEL,
    })
    ok, models = probe_endpoint(LOCAL_PORT)
    if ok:
        print(f"[Switcher] SUCCESS: Local Ollama on port {LOCAL_PORT} is reachable!")
        if LOCAL_MODEL in models:
            print(f"[Switcher] Model '{LOCAL_MODEL}' is installed and ready.")
        else:
            print(f"[Switcher] Note: Model '{LOCAL_MODEL}' not detected in {models}.")
    else:
        print(f"[Switcher] WARNING: Local Ollama on port {LOCAL_PORT} is not responding.")
        print("[Switcher] Starting 'ollama serve' in background is recommended.")

    backend_ok = notify_backend_reload()
    if backend_ok:
        print("[Switcher] Live backend settings reloaded instantly!")
    else:
        print("[Switcher] Settings written to .env.")


def cmd_colab(tunnel_url: str | None = None) -> None:
    print(f"[Switcher] Switching to GOOGLE COLAB GPU engine ({COLAB_MODEL})...")
    update_env({
        "OLLAMA_BASE_URL": f"http://127.0.0.1:{COLAB_PORT}",
        "OLLAMA_MODEL": COLAB_MODEL,
    })
    ok, _ = probe_endpoint(COLAB_PORT)
    if ok:
        print(f"[Switcher] SUCCESS: Colab bridge on port {COLAB_PORT} is reachable!")
    else:
        print(f"[Switcher] Colab bridge on port {COLAB_PORT} is not yet active.")
        if tunnel_url:
            print(f"[Switcher] To start bridge, run:\n   python scripts/bridge_colab.py {tunnel_url}")
        else:
            print("[Switcher] Run 'python scripts/bridge_colab.py <your-tunnel-url>' to bridge Colab.")

    backend_ok = notify_backend_reload()
    if backend_ok:
        print("[Switcher] Live backend settings reloaded instantly!")
    else:
        print("[Switcher] Settings written to .env.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/switch_engine.py status")
        print("  python scripts/switch_engine.py local")
        print("  python scripts/switch_engine.py colab [tunnel_url]")
        cmd_status()
        return

    mode = sys.argv[1].lower()
    if mode in ("status", "info"):
        cmd_status()
    elif mode in ("local", "offline", "3b"):
        cmd_local()
    elif mode in ("colab", "gpu", "7b"):
        tunnel = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_colab(tunnel)
    else:
        print(f"Unknown option '{mode}'. Choose 'status', 'local', or 'colab'.")


if __name__ == "__main__":
    main()
