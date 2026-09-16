"""QuizApiClient wraps HTTP calls to guidami_ai_patente and their failures (FR-5)."""

from collections.abc import Awaitable, Callable

import httpx
import pytest

from guidami_ai_patente_bot.clients import QuizApiClient
from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.exceptions import QuizApiError

_Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def _client(handler: _Handler) -> QuizApiClient:
    """Builds a QuizApiClient with a mock transport, sidestepping pywire's async lifecycle.

    `object.__new__` skips pywire's instrumentation and `__aenter__` (same
    sidestep pattern `tests/guidami_ai_patente/services/test_quiz_answer_checker.py::_checker`
    uses for a sync bean's `__init__`), so `config` and `_http` are set by hand here
    instead — no `container.astart()` involved.
    """
    api_client = object.__new__(QuizApiClient)
    api_client.config = BotConfig(  # type: ignore[assignment]
        telegram_bot_token="token",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    api_client._http = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url="http://api.test", transport=httpx.MockTransport(handler)
    )
    return api_client


@pytest.mark.asyncio
async def test_propose_question_parses_the_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/quiz-questions/random"
        assert request.url.params["seed"] == "abc"
        assert request.url.params["index"] == "2"
        return httpx.Response(
            200,
            json={"number": "0001", "topic": "segnaletica", "text": "...", "image_url": None},
        )

    client = _client(handler)

    question = await client.propose_question("abc", 2)

    assert question.number == "0001"
    assert question.image_url is None


@pytest.mark.asyncio
async def test_check_answer_returns_the_correctness_flag() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/quiz-questions/0001/check"
        return httpx.Response(200, json={"correct": True, "explanation_status": "cached"})

    client = _client(handler)

    correct = await client.check_answer("0001", True)

    assert correct is True


@pytest.mark.asyncio
async def test_get_explanation_parses_the_response_ignoring_extra_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["submitted"] == "true"
        return httpx.Response(
            200,
            json={
                "status": "explained",
                "explanation": "perché...",
                "citations": [],
                "provenance": None,
                "reason": None,
                "judge_rationale": None,
            },
        )

    client = _client(handler)

    explanation = await client.get_explanation("0001", submitted=True)

    assert explanation.explanation == "perché..."


@pytest.mark.asyncio
async def test_download_image_returns_the_raw_bytes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/quiz-images/abc.jpg"
        return httpx.Response(200, content=b"\x89PNG")

    client = _client(handler)

    content = await client.download_image("/quiz-images/abc.jpg")

    assert content == b"\x89PNG"


@pytest.mark.asyncio
async def test_a_non_2xx_response_raises_quiz_api_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)

    with pytest.raises(QuizApiError):
        await client.check_answer("9999", True)


@pytest.mark.asyncio
async def test_a_connection_failure_raises_quiz_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client(handler)

    with pytest.raises(QuizApiError):
        await client.propose_question("abc", 0)
