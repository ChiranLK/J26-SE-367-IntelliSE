"""Read local settings and check existing assets without logging secret values.

The config response is a PRIVATE parent/child pipe, never application output.
No package installation, model download, training or application DB writes.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def absolute_path(base, value):
    # A venv's python is often a symlink. Keep that path, not its base target.
    return Path(os.path.abspath(base / value))


def configuration(root, backend):
    import intelise_c1
    from intelise_c1.core.config import Settings
    from pydantic import SecretStr

    if not Path(intelise_c1.__file__).resolve().is_relative_to(backend.resolve()):
        raise RuntimeError("wrong_backend_install")
    settings = Settings(_env_file=[root / "component-1/backend/.env", backend / ".env"])
    # Explicit local launcher profile, honoring an explicitly selected provider.
    if "llm_provider" not in settings.model_fields_set:
        settings.llm_provider = "ollama"
    if not settings.mongodb_uri or not settings.mongodb_uri.get_secret_value().strip():
        settings.mongodb_uri = SecretStr("mongodb://127.0.0.1:27017")
    if settings.classifier_model_dir is None:
        settings.classifier_model_dir = backend / "research/models/dcai-v1/lr-c10"
    if settings.whisper_python is None:
        candidates = [backend / ".venv-whisper/bin/python", root / "component-1/backend/.venv-whisper/bin/python", Path("/private/tmp/intellise-c1-whisper-env/bin/python")]
        settings.whisper_python = next((path for path in candidates if path.is_file()), None)
    if "whisper_model_dir" not in settings.model_fields_set:
        candidates = [backend / "models/whisper", root / "component-1/backend/models/whisper", Path("/private/tmp/intellise-c1-whisper-models")]
        settings.whisper_model_dir = next((path for path in candidates if (path / f"{settings.whisper_model}.json").is_file()), candidates[0])
    for field in ["classifier_model_dir", "whisper_python", "whisper_model_dir"]:
        value = getattr(settings, field)
        if value is not None:
            # Preserve venv interpreter symlinks: resolving them selects the base
            # Python and loses the isolated environment's dependencies.
            setattr(settings, field, absolute_path(backend, value))
    environment = {}
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if value is None:
            continue
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        alias = type(settings).model_fields[name].validation_alias
        environment[alias if isinstance(alias, str) else "C1_" + name.upper()] = str(value)
    return {"env": environment, "temporary_asr": any(str(getattr(settings, name)).startswith(("/private/tmp/", "/tmp/")) for name in ["whisper_python", "whisper_model_dir"])}


def ping():
    from pymongo import MongoClient
    with MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=2000, connectTimeoutMS=2000, socketTimeoutMS=2000, timeoutMS=2500) as client:
        client.admin.command("ping")
    return {"ok": True}


def classifier():
    from intelise_c1.services.classifier import LocalClassifier
    labels, model, version = LocalClassifier(Path(os.environ["C1_CLASSIFIER_MODEL_DIR"])).predict([])
    return {"ok": labels == [], "model": model, "version": version}


def asr(directory, name):
    import whisper
    import torch
    import imageio_ffmpeg
    manifest = json.loads((directory / f"{name}.json").read_text())
    expected = whisper._MODELS[name].split("/")[-2]
    if hashlib.sha256((directory / f"{name}.pt").read_bytes()).hexdigest() != expected or manifest["checkpoint_sha256"] != expected:
        raise RuntimeError("invalid_checkpoint")
    executable = manifest["ffmpeg"]
    if not Path(executable).is_file() or not Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file():
        raise RuntimeError("missing_ffmpeg")
    result = subprocess.run([executable, "-hide_banner", "-decoders"], capture_output=True, check=True, timeout=10)
    if not all(codec in result.stdout.decode() for codec in ["pcm_s16le", "mp3", "aac"]):
        raise RuntimeError("missing_decoders")
    return {"ok": True, "model": name, "torch": torch.__version__}


if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        if mode == "config":
            result = configuration(Path(sys.argv[2]), Path(sys.argv[3]))
        elif mode == "ping":
            result = ping()
        elif mode == "classifier":
            result = classifier()
        elif mode == "asr":
            result = asr(Path(sys.argv[2]), sys.argv[3])
        elif mode == "azure":
            from intelise_c1.audio.azure import AzureSpeech
            from intelise_c1.core.config import Settings
            AzureSpeech(Settings(_env_file=None)).check_ready()
            result = {"ok": True, "model": "azure-speech-fast"}
        else:
            raise RuntimeError("unknown_check")
        print(json.dumps(result))
    except Exception:
        # Do not print driver/validation exceptions: they can contain credentials.
        print(json.dumps({"ok": False, "error": "preflight_failed"}))
        sys.exit(1)
