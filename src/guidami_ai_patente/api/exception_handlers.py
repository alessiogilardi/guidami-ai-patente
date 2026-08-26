"""The single place a domain exception becomes an HTTP status (spec 0012, AD-17)."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from guidami_ai_patente.exceptions import QuestionNotFoundError, QuizImageNotFoundError

from .schemas.api_error import ApiErrorResponse

logger = logging.getLogger(__name__)


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """Renders a domain 'does not exist' error as a 404 with its own message."""
    logger.debug("Resolving %r to 404: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.NOT_FOUND,
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
