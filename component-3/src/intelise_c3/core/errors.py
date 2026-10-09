"""Structured application and request-validation errors for API layers."""

from collections.abc import Sequence

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Machine-readable error detail returned by Component 3."""

    code: str
    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    errors: tuple[ErrorDetail, ...]


class ApplicationError(Exception):
    """Expected application failure that can be safely exposed to API clients."""

    def __init__(
        self,
        errors: Sequence[ErrorDetail],
        *,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        normalized_errors = tuple(errors)
        if not normalized_errors:
            raise ValueError("ApplicationError requires at least one error detail.")
        super().__init__(normalized_errors[0].message)
        self.errors = normalized_errors
        self.status_code = status_code


def register_exception_handlers(application: FastAPI) -> None:
    """Register handlers for known, intentionally exposed application errors."""

    @application.exception_handler(ApplicationError)
    async def handle_application_error(
        _request: Request, exception: ApplicationError
    ) -> JSONResponse:
        response = ErrorResponse(errors=exception.errors)
        return JSONResponse(
            status_code=exception.status_code,
            content=response.model_dump(exclude_none=True),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        errors = tuple(_request_error_detail(error) for error in exception.errors())
        response = ErrorResponse(errors=errors)
        return JSONResponse(
            status_code=422,
            content=response.model_dump(exclude_none=True),
        )


def _request_error_detail(error: dict[str, object]) -> ErrorDetail:
    """Convert a FastAPI/Pydantic error into the public field-aware shape."""
    error_type = str(error.get("type", "schema_validation"))
    location = error.get("loc", ())
    if isinstance(location, (tuple, list)):
        field_parts = [str(part) for part in location if part != "body"]
    else:
        field_parts = [str(location)]
    field = ".".join(field_parts) or "body"

    if error_type == "missing":
        code = "MISSING_REQUIRED_FIELD"
    elif error_type == "json_invalid":
        code = "MALFORMED_INPUT"
    else:
        code = "SCHEMA_VALIDATION_ERROR"

    return ErrorDetail(
        code=code,
        field=field,
        message=str(error.get("msg", "Invalid request payload.")),
    )
