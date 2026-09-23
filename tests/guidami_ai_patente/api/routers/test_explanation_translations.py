"""POST /explanations/translate, end to end (spec 0018)."""

from dataclasses import dataclass, field
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from pywire import get_default_container

from guidami_ai_patente.agents.explanation_translator.dto import (
    ExplanationTranslatorRequest,
    ExplanationTranslatorResponse,
)
from guidami_ai_patente.services import ExplanationTranslationService


@dataclass
class _TranslatorDouble:
    error: Exception | None = None
    requests: list[ExplanationTranslatorRequest] = field(default_factory=list)

    async def run(self, request: ExplanationTranslatorRequest) -> ExplanationTranslatorResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ExplanationTranslatorResponse(translated_text="Перевод.")


def _install_translator(monkeypatch: pytest.MonkeyPatch, translator: _TranslatorDouble) -> None:
    """Substitutes the agent on the resolved service singleton.

    Mirrors `_install_writer` in `test_quiz_explanation.py`: `register_instance`
    would refuse to displace the `@agent` registration, so the route's own singleton
    is patched directly.
    """
    service = get_default_container().resolve(ExplanationTranslationService)
    monkeypatch.setattr(service, "translator", translator)


@pytest.mark.integration
def test_a_valid_request_is_translated(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, registered_headers: dict[str, str]
) -> None:
    translator = _TranslatorDouble()
    _install_translator(monkeypatch, translator)

    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "La sosta è vietata perché la norma lo prevede."},
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["translated_text"] == "Перевод."
    assert translator.requests[0].text == "La sosta è vietata perché la norma lo prevede."
    assert translator.requests[0].hints == ()


@pytest.mark.integration
def test_hints_are_forwarded_to_the_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, registered_headers: dict[str, str]
) -> None:
    translator = _TranslatorDouble()
    _install_translator(monkeypatch, translator)

    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={
            "text": "La carreggiata è stretta.",
            "hints": [{"term": "carreggiata", "term_ru": "проезжая часть"}],
        },
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.OK
    forwarded = translator.requests[0].hints
    assert len(forwarded) == 1
    assert forwarded[0].term == "carreggiata"
    assert forwarded[0].term_ru == "проезжая часть"


@pytest.mark.integration
def test_more_than_ten_hints_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    hints = [{"term": f"termine{i}", "term_ru": f"термин{i}"} for i in range(11)]

    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "Testo.", "hints": hints},
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_a_hint_term_over_the_length_limit_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "Testo.", "hints": [{"term": "a" * 81, "term_ru": "термин"}]},
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_a_whitespace_only_hint_term_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "Testo.", "hints": [{"term": "   ", "term_ru": "термин"}]},
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_duplicate_hint_terms_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={
            "text": "La carreggiata è stretta.",
            "hints": [
                {"term": "carreggiata", "term_ru": "проезжая часть"},
                {"term": "Carreggiata", "term_ru": "дорога"},
            ],
        },
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_an_unsupported_language_is_a_400(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, registered_headers: dict[str, str]
) -> None:
    _install_translator(monkeypatch, _TranslatorDouble())

    response = api_client.post(
        "/explanations/translate?lang=en", json={"text": "Testo."}, headers=registered_headers
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.integration
def test_a_missing_text_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru", json={}, headers=registered_headers
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_a_text_over_the_length_limit_is_a_422(
    api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "a" * 6001},
        headers=registered_headers,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_an_unregistered_caller_is_a_403(api_client: TestClient) -> None:
    response = api_client.post(
        "/explanations/translate?lang=ru",
        json={"text": "Testo."},
        headers={"X-Telegram-User-Id": "918273"},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.integration
def test_a_translator_failure_is_a_503(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, registered_headers: dict[str, str]
) -> None:
    _install_translator(monkeypatch, _TranslatorDouble(error=RuntimeError("provider is down")))

    response = api_client.post(
        "/explanations/translate?lang=ru", json={"text": "Testo."}, headers=registered_headers
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
