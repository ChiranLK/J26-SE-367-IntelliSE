"""Lifespan-owned async MongoDB client; no fallback storage or sensitive logs."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from intelise_c1.core.config import Settings
from intelise_c1.repositories.projects import ProjectRepository
from intelise_c1.repositories.extractions import ExtractionRepository
from intelise_c1.repositories.classifications import ClassificationRepository
from intelise_c1.repositories.reviews import ReviewRepository
from intelise_c1.repositories.srs import SrsRepository
from intelise_c1.repositories.transcriptions import TranscriptionRepository
from intelise_c1.audio.worker import AudioWorker

UNAVAILABLE_DETAIL = "Project persistence is unavailable. Check MongoDB configuration and availability."


def database_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        client = None
        application.state.audio_worker = None
        application.state.extractions = None
        application.state.projects = None
        application.state.classifications = None
        application.state.label_reviews = None
        application.state.srs = None
        uri = settings.mongodb_uri.get_secret_value() if settings.mongodb_uri else ""
        try:
            if uri.strip():
                try:
                    client = AsyncMongoClient(
                        uri,
                        connect=False,
                        tz_aware=True,
                        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
                        connectTimeoutMS=settings.mongodb_timeout_ms,
                        socketTimeoutMS=settings.mongodb_timeout_ms,
                        timeoutMS=settings.mongodb_timeout_ms,
                    )
                    collection = client[settings.mongodb_database].get_collection(
                        "projects", write_concern=WriteConcern(w="majority")
                    )
                    transcriptions = TranscriptionRepository(client[settings.mongodb_database].get_collection(
                        "transcription_jobs", write_concern=WriteConcern(w="majority")
                    ))
                    application.state.projects = ProjectRepository(collection, transcriptions)
                    application.state.extractions = ExtractionRepository(
                        client[settings.mongodb_database].get_collection(
                            "extraction_runs", write_concern=WriteConcern(w="majority")
                        )
                    )
                    application.state.classifications = ClassificationRepository(
                        client[settings.mongodb_database].get_collection(
                            "classification_runs", write_concern=WriteConcern(w="majority")
                        )
                    )
                    application.state.label_reviews = ReviewRepository(client[settings.mongodb_database].get_collection(
                        'classification_reviews', write_concern=WriteConcern(w='majority')))
                    application.state.srs = SrsRepository(client[settings.mongodb_database].get_collection(
                        'srs_projects', write_concern=WriteConcern(w='majority')))
                    application.state.audio_worker = AudioWorker(
                        transcriptions, settings,
                    )
                    application.state.audio_worker.start()
                except (PyMongoError, ValueError):
                    # Invalid URI/configuration must not prevent the health API starting.
                    # Do not echo driver exceptions, which can contain connection details.
                    application.state.projects = None
                    application.state.extractions = None
                    application.state.classifications = None
                    application.state.label_reviews = None
                    application.state.srs = None
            yield
        finally:
            if application.state.audio_worker is not None:
                await application.state.audio_worker.stop()
            application.state.audio_worker = None
            application.state.projects = None
            application.state.extractions = None
            application.state.classifications = None
            application.state.label_reviews = None
            application.state.srs = None
            if client is not None:
                await client.close()

    return lifespan


def get_project_repository(request: Request) -> ProjectRepository:
    repository = getattr(request.app.state, "projects", None)
    if repository is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    return repository
