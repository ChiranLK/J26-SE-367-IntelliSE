"""Explicit real-ASR/HTTP/Mongo check. No downloads; never logs full transcripts.

Uses only a generated disposable database, a dedicated temporary upload root,
and a separately launched server. Leaves existing servers and records alone.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import wave

import httpx
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/api/v1/component-1'


class CheckFailure(Exception):
    """Only locally authored, safe diagnostic messages."""


def stop(server):
    if server and server.poll() is None:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def start(environment, client):
    # Exercise the documented normal installed-package entry point.
    server = subprocess.Popen([sys.executable, '-m', 'intelise_c1'],
                              cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None: raise CheckFailure('Disposable backend startup failed')
            try:
                if client.get(PREFIX + '/health').status_code == 200: return server
            except httpx.HTTPError: pass
            time.sleep(.1)
        raise CheckFailure('Disposable backend startup timed out')
    except Exception:
        stop(server)
        raise


def post(client, path):
    with path.open('rb') as audio:
        response = client.post(PREFIX + '/transcriptions', files={'audio': (path.name, audio, 'application/octet-stream')})
    if response.status_code != 202:
        raise CheckFailure(f'Upload returned HTTP {response.status_code}; inspect prepared model/runtime and database')
    accepted = response.json()
    assert accepted['status'] == 'queued'
    return accepted['transcription_id']


def wait(client, identifier, health_times=None):
    deadline = time.monotonic() + 330
    statuses = set()
    while time.monotonic() < deadline:
        response = client.get(PREFIX + '/transcriptions/' + identifier)
        assert response.status_code == 200
        row = response.json()
        statuses.add(row['status'])
        if row['status'] in ['completed', 'failed']: return row, statuses
        started = time.monotonic()
        health = client.get(PREFIX + '/health')
        elapsed = time.monotonic() - started
        assert health.status_code == 200
        if health_times is not None: health_times.append(elapsed)
        time.sleep(.05)
    raise CheckFailure('Job did not reach a terminal state within the bounded check')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', required=True, type=Path, help='Real short English recording: WAV/MP3/M4A')
    parser.add_argument('--whisper-python', required=True, type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--model', default='tiny.en')
    parser.add_argument('--verify-project-provenance', action='store_true',
                        help='Explicitly save an edited review project and verify its provenance across restart')
    args = parser.parse_args()
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri: parser.error('Set TEST_MONGODB_URI for a generated disposable database')
    database = 'intellise_c1_audio_smoke_' + uuid4().hex
    server = None
    mongo = MongoClient(uri, timeoutMS=2000, serverSelectionTimeoutMS=2000)
    # Bounded ping before starting any process or writing records.
    mongo.admin.command('ping')
    try:
        with tempfile.TemporaryDirectory(prefix='intellise-audio-smoke-') as temporary:
            base = Path(temporary)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            environment = dict(os.environ, MONGODB_URI=uri, C1_BACKEND_HOST='127.0.0.1',
                               MONGODB_DATABASE=database, C1_BACKEND_PORT=str(port),
                               # Resolving a venv's Python symlink selects the
                               # global interpreter and loses its dependencies.
                               C1_WHISPER_PYTHON=str(args.whisper_python.absolute()),
                               C1_WHISPER_MODEL_DIR=str(args.model_dir.resolve()), C1_WHISPER_MODEL=args.model,
                               C1_AUDIO_TEMP_DIR=str(base / 'uploads'), C1_AUDIO_QUEUE_SIZE='0',
                               C1_AUDIO_MAX_BYTES='10000000', C1_AUDIO_MAX_SECONDS='120',
                               C1_AUDIO_PROCESSING_TIMEOUT_SECONDS='300', C1_AUDIO_DECODE_TIMEOUT_SECONDS='20')
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10) as client:
                server = start(environment, client)
                contract = client.get('/openapi.json').json()
                assert PREFIX + '/transcriptions' in contract['paths']
                assert 'transcription_id' in contract['components']['schemas']['ProjectCreate']['properties']
                started = time.monotonic()
                identifier = post(client, args.sample)
                # The one-slot prototype rejects another upload while occupied.
                saturated = client.post(PREFIX + '/transcriptions', files={'audio': ('second.wav', b'x')})
                assert saturated.status_code == 429
                health_times = []
                saved, statuses = wait(client, identifier, health_times)
                wall = time.monotonic() - started
                if saved['status'] != 'completed':
                    raise CheckFailure('Real ASR failed: ' + str(saved['error_code']))
                assert saved['asr_performed'] and saved['outcome'] == 'review_required'
                assert saved['original_transcript'].strip() and saved['segments']
                assert saved['reviewed_text'] is None and saved['review_status'] == 'needs_review'
                assert saved['model'] == args.model and saved['language'] == 'en'
                assert 'processing' in statuses and health_times
                record = mongo[database].transcription_jobs.find_one({'transcription_id': identifier})
                assert record['original_transcript'] == saved['original_transcript']
                assert record['model'] == args.model
                digest = sha256(saved['original_transcript'].encode()).hexdigest()
                project = None
                if args.verify_project_provenance:
                    assert client.get(PREFIX + '/projects').json()['items'] == []
                    reviewed = saved['original_transcript'] + '\nUser-edited verification draft.'
                    response = client.post(PREFIX + '/projects', json={
                        'name': 'Disposable reviewed audio project', 'description': 'Explicit provenance verification',
                        'discussion_text': reviewed, 'transcription_id': identifier,
                    })
                    assert response.status_code == 201
                    project = response.json()
                    provenance = project['transcription_provenance']
                    assert project['discussion_text'] == reviewed != saved['original_transcript']
                    assert provenance['original_transcript'] == saved['original_transcript']
                    assert provenance['original_transcript_hash'] == digest
                    assert provenance['reviewed_discussion_hash'] == sha256(reviewed.encode()).hexdigest()
                    assert provenance['model'] == saved['model'] and provenance['transcription_id'] == identifier
                    assert provenance['review_status'] == 'user_reviewed'
                    assert client.get(PREFIX + '/projects/' + project['id']).json() == project
                    assert mongo[database].transcription_jobs.find_one({'transcription_id': identifier}) == record
                    assert mongo[database].projects.find_one({'transcription_provenance.transcription_id': identifier})['discussion_text'] == reviewed
                # Validate real decoder failures and reviewable silence using non-speech PCM fixtures.
                outcomes = {}
                for name, frames in [('silence', 16000), ('overlong', 16000 * 121)]:
                    path = base / (name + '.wav')
                    with wave.open(str(path), 'wb') as audio:
                        audio.setparams((1, 2, 16000, frames, 'NONE', 'not compressed'))
                        audio.writeframes(b'\0\0' * frames)
                    row, _ = wait(client, post(client, path))
                    outcomes[name] = row['outcome'] if row['status'] == 'completed' else row['error_code']
                    assert row['original_transcript'] is None
                assert outcomes == {'silence': 'silence_detected', 'overlong': 'audio_too_long'}
                corrupt = base / 'corrupt.mp3'
                corrupt.write_bytes(b'This is not audio')
                row, _ = wait(client, post(client, corrupt))
                assert row['status'] == 'failed' and row['error_code'] == 'invalid_audio'
                response = client.post(PREFIX + '/transcriptions', files={'audio': ('large.wav', b'x' * 10000001)})
                assert response.status_code == 413
                stop(server)
                server = None
                assert not list((base / 'uploads').glob('*'))
                environment['C1_WHISPER_PYTHON'] = ''
                server = start(environment, client)
                fetched = client.get(PREFIX + '/transcriptions/' + identifier)
                assert fetched.status_code == 200 and fetched.json() == saved
                page = client.get(PREFIX + '/projects').json()['items']
                if project:
                    assert client.get(PREFIX + '/projects/' + project['id']).json() == project
                    assert len(page) == 1 and 'transcription_provenance' not in page[0]
                    assert 'discussion_text' not in page[0]
                    assert mongo[database].transcription_jobs.find_one({'transcription_id': identifier}) == record
                else:
                    assert page == []
                assert client.post(PREFIX + '/transcriptions', files={'audio': ('a.wav', b'audio')}).status_code == 503
                report = dict(check='real ASR + HTTP + MongoDB + controlled restart', model=saved['model'],
                              transcription_id=identifier, audio_duration_seconds=saved['audio_duration_seconds'],
                              processing_seconds=saved['processing_seconds'], upload_to_completion_seconds=wall,
                              transcript_characters=len(saved['original_transcript']), transcript_sha256=digest,
                              segment_count=len(saved['segments']), observed_statuses=sorted(statuses),
                              health_requests=len(health_times), maximum_health_seconds=max(health_times),
                              decoder_checks=outcomes, corrupt_mp3='invalid_audio', oversized_http=413,
                              saturation_http=429, retrieval_after_restart=True, original_preserved=True,
                              temporary_files_cleaned=True, automatic_projects=0,
                              normal_startup='python -m intelise_c1',
                              reviewed_project_verified=bool(project), projects_explicitly_created=int(bool(project)))
                print(json.dumps(report, indent=2))  # Metadata only; no full transcript.
    finally:
        stop(server)
        mongo.drop_database(database)  # Only the generated smoke database.
        mongo.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Driver/provider exceptions may contain secrets: do not print them.
        print(json.dumps({'check': 'failed', 'error_type': type(error).__name__,
                          'detail': str(error) if isinstance(error, CheckFailure) else 'Isolated check failed; no sensitive exception details emitted.',
                          'action': 'Check isolated DB, prepared model, sample and environment; no generation retry.'}))
        raise SystemExit(1) from None
