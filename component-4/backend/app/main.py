from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handles startup and shutdown events."""
    setup_logging()
    logger.info("==================================================")
    logger.info("Starting %s v%s", settings.PROJECT_NAME, settings.VERSION)
    logger.info("Environment: %s | Debug: %s", settings.ENVIRONMENT, settings.DEBUG)
    logger.info("Storage Backend: %s", settings.STORAGE_BACKEND)
    if settings.STORAGE_BACKEND.lower() == "memory":
        logger.warning(
            "*** EPHEMERAL STORAGE NOTICE: Data is held strictly in memory. "
            "All submissions and verification runs will be lost when the server restarts. ***"
        )
    logger.info("Allowed CORS Origins: %s", settings.ALLOWED_ORIGINS)
    logger.info("Swagger documentation available at /docs")
    logger.info("==================================================")
    yield
    logger.info("Shutting down %s", settings.PROJECT_NAME)


def create_application() -> FastAPI:
    """Application factory for Component 4."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS with explicitly configured allowed origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Register custom exception handlers
    register_exception_handlers(app)

    # Root health endpoint and API v1 router
    app.include_router(health_router, prefix="", tags=["Health"])
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["Root"], summary="API Root")
    async def root_info():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "phase": "Phase 1 - Backend Foundation",
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "api_v1": settings.API_V1_STR,
        }

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
