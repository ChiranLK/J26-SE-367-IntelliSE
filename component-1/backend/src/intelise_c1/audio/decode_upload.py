"""Bounded local decoding for cloud transcription; stdlib and existing decoder only."""
from array import array
import argparse
import json
from pathlib import Path
import sys
import wave

from runtime import AudioFailure, decode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--upload', required=True)
    parser.add_argument('--extension', required=True, choices=['wav', 'mp3', 'm4a'])
    parser.add_argument('--pcm', required=True, type=Path)
    parser.add_argument('--maximum-seconds', required=True, type=float)
    parser.add_argument('--timeout', required=True, type=float)
    parser.add_argument('--silence-rms', required=True, type=float)
    args = parser.parse_args()
    try:
        duration = decode(args.ffmpeg, args.upload, args.extension, args.pcm, args.maximum_seconds, args.timeout)
        samples = array('h', args.pcm.read_bytes())
        if sys.byteorder != 'little':
            samples.byteswap()
        rms = (sum(int(value) ** 2 for value in samples) / len(samples)) ** .5 / 32768
        with wave.open(str(args.pcm.with_suffix('.wav')), 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(args.pcm.read_bytes())
        print(json.dumps({'duration': duration, 'silent': rms <= args.silence_rms}))
    except AudioFailure as error:
        print(json.dumps({'error': str(error)}))
    except Exception:
        print(json.dumps({'error': 'invalid_audio'}))


if __name__ == '__main__':
    main()
