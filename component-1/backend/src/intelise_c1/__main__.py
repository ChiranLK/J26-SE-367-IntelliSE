"""Run Uvicorn with configured host and port."""

import uvicorn

from intelise_c1.core.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("intelise_c1.main:app", host=settings.backend_host, port=settings.backend_port)


if __name__ == "__main__":
    main()
