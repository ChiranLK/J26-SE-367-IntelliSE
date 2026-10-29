"""Local hidden-input Azure setup. No network request or key in arguments/logs."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import warnings

from intelise_c1.audio.azure import AzureSpeech
from intelise_c1.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


def update_env(path, values):
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlinked .env')
    original_bytes = path.read_bytes() if path.exists() else b''
    original = original_bytes.decode('utf-8')
    if path.exists():
        backup = path.with_name('.env.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        with open(backup, 'xb', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            stream.write(original_bytes)
    remaining = dict(values)
    lines = []
    for line in original.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        name = match.group(1) if match else None
        if name in values:
            if name in remaining:
                lines.append(name + '=' + json.dumps(remaining.pop(name)))
        else:
            lines.append(line)
    lines.extend(name + '=' + json.dumps(value) for name, value in remaining.items())
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.env.', delete=False) as stream:
        temporary = Path(stream.name)
        os.chmod(temporary, 0o600)
        stream.write('\n'.join(lines) + '\n')
    os.replace(temporary, path)


def find_ffmpeg(settings):
    if settings.audio_ffmpeg_path:
        # Explicit broken configuration is not silently replaced.
        return settings.audio_ffmpeg_path
    installed = shutil.which('ffmpeg')
    if installed:
        return Path(installed)
    roots = [BACKEND / '.venv-whisper', BACKEND.parents[3] / 'component-1/backend/.venv-whisper',
             Path('/private/tmp/intellise-c1-whisper-env')]
    for root in roots:
        for executable in sorted(root.glob('lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*')):
            if executable.is_file() and os.access(executable, os.X_OK):
                # Retain a durable local decoder; do not depend on /tmp surviving.
                target = BACKEND / 'models/audio/ffmpeg'
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    with executable.open('rb') as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(0o700)
                return target
    raise ValueError('FFmpeg not found. Set C1_AUDIO_FFMPEG_PATH to your installed executable before setup.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Local readiness only; no Azure request')
    args = parser.parse_args()
    path = BACKEND / '.env'
    settings = Settings(_env_file=path)
    if args.check:
        AzureSpeech(settings).check_ready()
        print('Azure credentials and decoder are configured locally. No Azure request was sent.')
        return
    if not sys.stdin.isatty():
        raise ValueError('Run this command directly in Terminal for hidden key entry; do not pipe the key.')
    executable = find_ffmpeg(settings)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError('Configured FFmpeg executable is unavailable.')
    with warnings.catch_warnings():
        # Refuse getpass's echoed-input fallback if the terminal cannot disable echo.
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('Paste Azure Speech KEY 1 (hidden), then press Enter: ').strip()
    if not re.fullmatch(r'[A-Za-z0-9+/=_-]{16,256}', key):
        raise ValueError('Key has an unexpected format; no credentials were saved.')
    values = {'C1_TRANSCRIPTION_PROVIDER': 'azure', 'C1_AZURE_SPEECH_KEY': key,
              'C1_AZURE_SPEECH_ENDPOINT': 'https://southeastasia.api.cognitive.microsoft.com',
              'C1_AZURE_SPEECH_API_VERSION': '2025-10-15', 'C1_AZURE_SPEECH_LOCALE': 'en-US',
              'C1_AUDIO_FFMPEG_PATH': str(executable)}
    update_env(path, values)
    print('Saved Azure Speech configuration to the backend ignored .env (owner-only permissions).')
    print('Existing settings were preserved; an owner-only ignored backup was saved if .env existed.')
    print('Restart the application with ./start-component-1 from the main repository root.')
    print('This setup did not send audio, validate the key with Azure, or incur transcription usage.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt):
        # Never print validation values or provider/driver exception bodies.
        print('Azure setup did not complete. Check the local key, .env and FFmpeg settings; no secrets were printed.', file=sys.stderr)
        raise SystemExit(1) from None
