"""Domain exceptions become status codes in one place (spec 0012, AD-17)."""

import asyncio
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guidami_ai_patente.api.exception_handlers import register_exception_handlers
from guidami_ai_patente.exceptions import (
    ExplanationUnavailableError,
    GuidamiApiError,
    QuestionNotFoundError,
    QuizImageNotFoundError,
    UnregisteredUserError,
    UnsupportedLanguageError,
)


def _client_raising(error: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


def test_an_unknown_question_number_is_a_404() -> None:
    response = _client_raising(QuestionNotFoundError("9999")).get("/boom")

    assert response.status_code == 404
    assert "9999" in response.json()["detail"]


def test_an_index_past_the_end_of_the_filtered_bank_is_a_404() -> None:
    response = _client_raising(QuestionNotFoundError.at_index("abc", 7)).get("/boom")

    assert response.status_code == 404
    assert response.json()["detail"] != ""


def test_an_unreferenced_image_is_a_404() -> None:
    response = _client_raising(QuizImageNotFoundError("../../.env")).get("/boom")

    assert response.status_code == 404


def test_every_api_error_inherits_the_shared_base() -> None:
    assert issubclass(QuestionNotFoundError, GuidamiApiError)
    assert issubclass(QuizImageNotFoundError, GuidamiApiError)


def test_an_unavailable_explanation_is_a_503(api_client: TestClient) -> None:
    """FR-13: an outage is reported as a transient failure, never as a corpus gap."""
    app = api_client.app
    handler = app.exception_handlers[ExplanationUnavailableError]  # type: ignore[attr-defined]

    response = asyncio.run(handler(None, ExplanationUnavailableError("il giudice non risponde")))

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert b"il giudice non risponde" in response.body


def test_the_503_body_carries_no_insufficient_knowledge_reason(api_client: TestClient) -> None:
    """FR-13: the response must not be mistakable for FR-7's vocabulary."""
    app = api_client.app
    handler = app.exception_handlers[ExplanationUnavailableError]  # type: ignore[attr-defined]

    response = asyncio.run(handler(None, ExplanationUnavailableError("timeout")))

    assert b"no_supporting_norm" not in response.body
    assert b"not_indexed" not in response.body


def test_an_unregistered_caller_is_a_403() -> None:
    response = _client_raising(UnregisteredUserError(42)).get("/boom")

    assert response.status_code == 403
    assert "42" in response.json()["detail"]


def test_an_unregistered_user_error_inherits_the_shared_base() -> None:
    assert issubclass(UnregisteredUserError, GuidamiApiError)


def test_an_unsupported_language_is_a_400() -> None:
    response = _client_raising(UnsupportedLanguageError("en")).get("/boom")

    assert response.status_code == 400
    assert "en" in response.json()["detail"]
