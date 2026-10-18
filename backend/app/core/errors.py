"""Domain error types mapped to HTTP responses by the API error handlers."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "domain_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundErr(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class AuthErr(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenErr(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictErr(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationErr(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class SimulationErr(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "simulation_error"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError):  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message, "details": exc.details},
        )
