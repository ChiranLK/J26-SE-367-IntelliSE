"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from intelise_c1.api.router import api_router
from intelise_c1.core.config import Settings
from intelise_c1.core.database import UNAVAILABLE_DETAIL, database_lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(
        title="Component 01 — Requirement Engineering",
        version="0.1.0",
        description="Backend foundation. Health reports application availability only.",
        lifespan=database_lifespan(settings),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(PyMongoError)
    async def persistence_unavailable(_request, _error):
        return JSONResponse(status_code=503, content={"detail": UNAVAILABLE_DETAIL})

    application.include_router(api_router)
    return application


app = create_app()
