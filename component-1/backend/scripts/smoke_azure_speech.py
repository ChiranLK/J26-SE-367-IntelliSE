"""Explicit billed Azure + HTTP + real MongoDB test with disposable records.

No full transcript/key is logged. Run only with an authorized sample and a
configured Azure key. Uses the existing smoke helpers and normal app entrypoint.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import tempfile
import time
from uuid import uuid4

import httpx
from pymongo import MongoClient

from intelise_c1.audio.azure import AzureSpeech
from intelise_c1.core.config import Settings
from smoke_transcription import start, stop, post, wait, CheckFailure, PREFIX, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',required=True,type=Path)
    args=parser.parse_args()
    settings=Settings(_env_file=ROOT/'.env')
    AzureSpeech(settings).check_ready()
    uri=os.environ.get('TEST_MONGODB_URI')
    if not uri:
        raise CheckFailure('Set TEST_MONGODB_URI for a generated isolated test database.')
    database='intellise_c1_azure_smoke_'+uuid4().hex
    mongo=MongoClient(uri,timeoutMS=2500,serverSelectionTimeoutMS=2000)
    mongo.admin.command('ping')
    server=None
    try:
        with tempfile.TemporaryDirectory(prefix='c1-azure-smoke-') as temporary:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            environment=dict(os.environ,MONGODB_URI=uri,MONGODB_DATABASE=database,C1_BACKEND_PORT=str(port),
                C1_BACKEND_HOST='127.0.0.1',C1_TRANSCRIPTION_PROVIDER='azure',
                C1_AZURE_SPEECH_KEY=settings.azure_speech_key.get_secret_value(),
                C1_AZURE_SPEECH_ENDPOINT=settings.azure_speech_endpoint,
                C1_AZURE_SPEECH_API_VERSION=settings.azure_speech_api_version,
                C1_AZURE_SPEECH_LOCALE=settings.azure_speech_locale,
                C1_AUDIO_TEMP_DIR=temporary,C1_AUDIO_FFMPEG_PATH=AzureSpeech(settings).ffmpeg())
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=10) as client:
                server=start(environment,client)
                schema=client.get('/openapi.json').json()
                assert PREFIX+'/transcriptions' in schema['paths']
                started=time.monotonic(); identifier=post(client,args.sample); health=[]
                job,_=wait(client,identifier,health); elapsed=time.monotonic()-started
                if job['status']!='completed': raise CheckFailure('Azure job failed: '+str(job['error_code']))
                assert job['provider']=='azure' and job['model']=='azure-speech-fast'
                assert job['api_version']==settings.azure_speech_api_version
                if job['outcome']!='review_required': raise CheckFailure('No intelligible speech returned; review the recording.')
                raw=mongo[database].transcription_jobs.find_one({'transcription_id':identifier})
                assert raw['original_transcript']==job['original_transcript']
                reviewed=job['original_transcript']+'\nHuman review pending: edited smoke-test copy.'
                response=client.post(PREFIX+'/projects',json={'name':'Disposable Azure smoke project',
                    'discussion_text':reviewed,'transcription_id':identifier})
                assert response.status_code==201
                project=response.json(); provenance=project['transcription_provenance']
                assert provenance['provider']=='azure' and provenance['api_version']==settings.azure_speech_api_version
                assert provenance['original_transcript']==job['original_transcript'] and project['discussion_text']==reviewed
                stop(server);server=None
                # Stored jobs/projects must remain retrievable without credentials.
                environment['C1_AZURE_SPEECH_KEY']=''
                server=start(environment,client)
                assert client.get(PREFIX+'/transcriptions/'+identifier).json()==job
                assert client.get(PREFIX+'/projects/'+project['id']).json()==project
                assert client.post(PREFIX+'/transcriptions',files={'audio':('new.wav',b'x')}).status_code==503
                stop(server);server=None
                assert not list(Path(temporary).iterdir())
                print(json.dumps({'provider':'azure','model':job['model'],'api_version':job['api_version'],
                    'locale':job['locale'],'duration_seconds':job['audio_duration_seconds'],
                    'processing_seconds':job['processing_seconds'],'upload_to_completion_seconds':elapsed,
                    'transcript_characters':len(job['original_transcript']),
                    'transcript_sha256':sha256(job['original_transcript'].encode()).hexdigest(),
                    'segments':len(job['segments']),'health_checks':len(health),
                    'maximum_health_seconds':max(health,default=0),'real_mongodb':True,
                    'retrievable_after_restart':True,'provenance_verified':True,
                    'review_note':'Smoke edit is not independently human-verified',
                    'temporary_files_cleaned':True,'test_database_removed_on_exit':True},indent=2))
    finally:
        stop(server)
        mongo.drop_database(database)
        mongo.close()


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'check':'failed','error_type':type(error).__name__,
                          'action':'Check Azure configuration, authorized sample and isolated MongoDB. No retry or fallback.',
                          'detail':str(error) if isinstance(error,CheckFailure) else 'Sensitive exception details withheld.'}))
        raise SystemExit(1) from None
