"""Domain exceptions become status codes in one place (spec 0012, AD-17)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guidami_ai_patente.api.exception_handlers import register_exception_handlers
from guidami_ai_patente.exceptions import (
    GuidamiApiError,
    QuestionNotFoundError,
    QuizImageNotFoundError,
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
