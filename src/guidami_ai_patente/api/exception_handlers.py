"""The single place a domain exception becomes an HTTP status (spec 0012, AD-17)."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from guidami_ai_patente.exceptions import (
    ExplanationUnavailableError,
    QuestionNotFoundError,
    QuizImageNotFoundError,
)

from .schemas.api_error import ApiErrorResponse

logger = logging.getLogger(__name__)


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """Renders a domain 'does not exist' error as a 404 with its own message."""
    logger.debug("Resolving %r to 404: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=ApiErrorResponse(detail=str(exc)).model_dump(),
    )


async def _service_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Renders a transient domain failure as a 503 with its own message (FR-13).

    `warning`, not `debug` as the 404 path uses: a 404 is a client naming something
    that does not exist, while this is our own dependency failing and the operator
    wants it in the log.
    """
    logger.warning("Resolving %r to 503: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content=ApiErrorResponse(detail=str(exc)).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers every domain-exception → status mapping on `app`.

    Routers therefore carry no `try/except` and no status codes: they call a service,
    which raises a domain error, which lands here. Adding a status means adding an
    entry to this function, in one file, rather than a branch in every handler that
    can hit the condition.
    """
    app.add_exception_handler(QuestionNotFoundError, _not_found)
    app.add_exception_handler(QuizImageNotFoundError, _not_found)
    app.add_exception_handler(ExplanationUnavailableError, _service_unavailable)
