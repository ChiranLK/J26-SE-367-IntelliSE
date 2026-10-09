from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelise_c1.api.health import router
from intelise_c1.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="InteliSE Component 01", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[],
    )
    app.include_router(router)
    return app


app = create_app()
