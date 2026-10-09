"""Lifespan-owned async MongoDB client; no fallback storage or sensitive logs."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from intelise_c1.core.config import Settings
from intelise_c1.repositories.projects import ProjectRepository

UNAVAILABLE_DETAIL = "Project persistence is unavailable. Check MongoDB configuration and availability."


def database_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        client = None
        application.state.projects = None
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
                    application.state.projects = ProjectRepository(collection)
                except (PyMongoError, ValueError):
                    # Invalid URI/configuration must not prevent the health API starting.
                    # Do not echo driver exceptions, which can contain connection details.
                    application.state.projects = None
            yield
        finally:
            application.state.projects = None
            if client is not None:
                await client.close()

    return lifespan


def get_project_repository(request: Request) -> ProjectRepository:
    repository = getattr(request.app.state, "projects", None)
    if repository is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    return repository
