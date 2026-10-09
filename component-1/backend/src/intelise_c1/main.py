"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelise_c1.api.router import api_router
from intelise_c1.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(
        title="Component 01 — Requirement Engineering",
        version="0.1.0",
        description="Backend foundation. Health reports application availability only.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[],
    )
    application.include_router(api_router)
    return application


app = create_app()
