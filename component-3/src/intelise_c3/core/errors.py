"""Reusable application-error primitives for API layers."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Machine-readable error detail returned by Component 3."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail


class ApplicationError(Exception):
    """Expected application failure that can be safely exposed to API clients."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def register_exception_handlers(application: FastAPI) -> None:
    """Register handlers for known, intentionally exposed application errors."""

    @application.exception_handler(ApplicationError)
    async def handle_application_error(
        _request: Request, exception: ApplicationError
    ) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(code=exception.code, message=exception.message)
        )
        return JSONResponse(
            status_code=exception.status_code,
            content=response.model_dump(),
        )
