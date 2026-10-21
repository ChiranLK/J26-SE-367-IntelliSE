"""Standalone Whisper process: run ONLY with the isolated ASR interpreter.

Stdout is a private bounded JSON protocol, never an application log. No backend
imports, no inference downloads, no training, and no translation.
"""
import argparse
from contextlib import redirect_stdout
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import wave


class AudioFailure(Exception):
    pass


def ffmpeg_binary():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def prepare(directory, name):
    import whisper
    import torch
    torch.set_num_threads(2)
    executable = ffmpeg_binary()
    decoders = subprocess.run([executable, '-hide_banner', '-decoders'], capture_output=True,
                              timeout=10, check=True).stdout.decode()
    if not all(codec in decoders for codec in ['pcm_s16le', 'mp3', 'aac']):
        raise AudioFailure('unsupported_decoder')
    # Verify actual container/codec decoding, not filename acceptance alone.
    with tempfile.TemporaryDirectory(prefix='intellise-decoder-check-') as temporary:
        base = Path(temporary)
        wav = base / 'check.wav'
        with wave.open(str(wav), 'wb') as audio:
            audio.setparams((1, 2, 16000, 1600, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * 1600)
        for extension, codec in [('wav', None), ('mp3', 'libmp3lame'), ('m4a', 'aac')]:
            source = base / f'check.{extension}'
            if codec:
                subprocess.run([executable, '-nostdin', '-loglevel', 'error', '-i', str(wav),
                                '-c:a', codec, str(source)], capture_output=True, timeout=10, check=True)
            decode(executable, str(source), extension, base / 'check.pcm', 2, 10)
    directory.mkdir(parents=True, exist_ok=True)
    # This is the ONLY path allowed to download; inference passes a local path.
    with redirect_stdout(sys.stderr):
        whisper.load_model(name, device='cpu', download_root=str(directory))
    checkpoint = directory / f'{name}.pt'
    expected = whisper._MODELS[name].split('/')[-2]
    actual = sha256(checkpoint.read_bytes()).hexdigest()
    if actual != expected:
        raise AudioFailure('invalid_model_hash')
    manifest = {'model': name, 'checkpoint_sha256': actual, 'ffmpeg': executable,
                'formats': ['wav', 'mp3', 'm4a'], 'device': 'cpu', 'fp16': False,
                'language': 'en', 'task': 'transcribe'}
    (directory / f'{name}.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'prepared': True, 'model': name, 'directory': str(directory), 'ffmpeg': executable,
                      'formats': manifest['formats']}))


def decode(executable, upload, extension, pcm, duration_limit, timeout):
    demuxer = {'wav': 'wav', 'mp3': 'mp3', 'm4a': 'mov'}[extension]
    try:
        subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-protocol_whitelist', 'file,pipe', '-f', demuxer, '-i', upload,
                        '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
                        '-t', str(duration_limit + .1), '-f', 's16le', '-y', str(pcm)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout, check=True)
    except subprocess.TimeoutExpired:
        raise AudioFailure('decode_timeout') from None
    except (subprocess.CalledProcessError, OSError):
        raise AudioFailure('invalid_audio') from None
    size = pcm.stat().st_size
    if size > int(duration_limit * 16000) * 2:
        raise AudioFailure('audio_too_long')
    if size == 0 or size % 2:
        raise AudioFailure('invalid_audio')
    return size / 32000


def serve(directory, name):
    import numpy as np
    manifest = json.loads((directory / f'{name}.json').read_text())
    executable = manifest['ffmpeg']
    checkpoint = directory / f'{name}.pt'
    model = None
    os.environ['NUMBA_NUM_THREADS'] = '1'
    for line in sys.stdin:
        started = time.monotonic()
        duration = None
        try:
            data = json.loads(line)
            pcm = Path(data['pcm'])
            duration = decode(executable, data['upload'], data['extension'], pcm,
                              data['duration_limit'], data['decode_timeout'])
            samples = np.fromfile(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples ** 2)))
            if rms <= data['silence_rms']:
                result = {'original_transcript': None, 'segments': [], 'outcome': 'silence_detected',
                          'asr_performed': False}
            else:
                if model is None:
                    if sha256(checkpoint.read_bytes()).hexdigest() != manifest['checkpoint_sha256']:
                        raise AudioFailure('invalid_model_hash')
                    import torch
                    import whisper
                    torch.set_num_threads(2)
                    with redirect_stdout(sys.stderr):
                        model = whisper.load_model(str(checkpoint), device='cpu')
                with redirect_stdout(sys.stderr):
                    generated = model.transcribe(samples, language='en', task='transcribe', fp16=False,
                                                 verbose=None, temperature=0.0, condition_on_previous_text=False)
                text = generated['text']  # Never strip, rewrite or replace the generated original.
                segments = [{'start': float(s['start']), 'end': float(s['end']), 'text': s['text']}
                            for s in generated.get('segments', [])]
                result = {'original_transcript': text, 'segments': segments,
                          'outcome': 'review_required' if text.strip() else 'no_intelligible_speech',
                          'asr_performed': True}
            result.update(audio_duration_seconds=duration,
                          processing_seconds=time.monotonic() - started)
            print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False), flush=True)
        except Exception as error:
            code = str(error) if isinstance(error, AudioFailure) else 'transcription_failed'
            print(json.dumps({'error': code, 'audio_duration_seconds': duration,
                              'processing_seconds': time.monotonic() - started}), flush=True)


def main():
    parser = argparse.ArgumentParser(description='Isolated CPU Whisper runtime')
    parser.add_argument('command', choices=['prepare', 'serve'])
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--model', default='tiny.en')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.model_dir.resolve(), args.model)
    else:
        serve(args.model_dir.resolve(), args.model)


if __name__ == '__main__':
    main()
