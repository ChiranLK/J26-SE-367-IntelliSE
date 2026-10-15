"""FastAPI application factory for Component 3."""

from fastapi import FastAPI

from intelise_c3.api.router import api_router
from intelise_c3.core.config import get_settings
from intelise_c3.core.errors import register_exception_handlers


def create_app() -> FastAPI:
    """Build and configure the Component 3 API application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.service_name,
        version=settings.api_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    application.state.settings = settings
    application.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


app = create_app()
