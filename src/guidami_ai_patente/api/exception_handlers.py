"""The single place a domain exception becomes an HTTP status (spec 0012, AD-17)."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from guidami_ai_patente.exceptions import (
    ExplanationUnavailableError,
    LabelingNotReadyError,
    QuestionNotFoundError,
    QuizImageNotFoundError,
    UnregisteredUserError,
    UnsupportedLanguageError,
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


async def _forbidden(request: Request, exc: Exception) -> JSONResponse:
    """Renders an unapproved caller as a 403 with its own message (FR-3).

    `debug`, like the 404 path: a caller who has not yet been approved is an
    expected, routine condition — not an operator-actionable event — the same
    reasoning `_not_found` already applies to "client named something absent".
    """
    logger.debug("Resolving %r to 403: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.FORBIDDEN,
        content=ApiErrorResponse(detail=str(exc)).model_dump(),
    )


async def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    """Renders a malformed caller request as a 400 with its own message (spec 0018, FR-2).

    `debug`, like `_not_found`/`_forbidden`: a caller naming an unsupported language is
    an expected, routine condition, not an operator-actionable event.
    """
    logger.debug("Resolving %r to 400: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=ApiErrorResponse(detail=str(exc)).model_dump(),
    )


async def _conflict(request: Request, exc: Exception) -> JSONResponse:
    """Renders a contract violation as a 409 with its own message (spec 0017, AD-4).

    `warning`, like `_service_unavailable`: this means a caller skipped `POST
    /label` before `GET /explanation`, which should never happen from the bot's own
    orchestration — worth an operator's attention if it does.
    """
    logger.warning("Resolving %r to 409: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=HTTPStatus.CONFLICT,
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
    app.add_exception_handler(LabelingNotReadyError, _conflict)
    app.add_exception_handler(UnregisteredUserError, _forbidden)
    app.add_exception_handler(UnsupportedLanguageError, _bad_request)
