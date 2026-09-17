"""HTTP adapter to the guidami-ai-patente API — one method per endpoint shape (AD-1)."""

from http import HTTPStatus
from typing import Any, Self

import httpx
from pywire import Autowired

from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.exceptions import QuizApiError, UnauthorizedError
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion


class QuizApiClient:
    """Thin async adapter over `guidami_ai_patente`'s HTTP API (AD-1, AD-8, spec 0016 AD-13).

    Registered explicitly by `main.py::_run` (see the class's original docstring in
    ADR 0032/ADR 0033 for the full async-component-lifecycle rationale — unchanged by
    this plan).
    """

    config: Autowired[BotConfig]

    async def __aenter__(self) -> Self:
        """Opens the underlying `httpx.AsyncClient` (entered by `container.lifespan()`)."""
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self.config.api_base_url, timeout=self.config.request_timeout_seconds
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Closes the underlying `httpx.AsyncClient` (exited by `container.lifespan()`)."""
        await self._http.aclose()

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        """Calls `GET /me` (spec 0016, FR-2).

        Never raises `UnauthorizedError`: `/me` never 403s.
        """
        response = await self._request("GET", "/me", telegram_user_id)
        return bool(response.json()["registered"])

    async def propose_question(self, telegram_user_id: int, seed: str, index: int) -> QuizQuestion:
        """Calls `GET /quiz-questions/random` (FR-1, FR-4)."""
        response = await self._request(
            "GET",
            "/quiz-questions/random",
            telegram_user_id,
            params={"seed": seed, "index": index},
        )
        return QuizQuestion.model_validate(response.json())

    async def download_image(self, telegram_user_id: int, image_url: str) -> bytes:
        """Downloads the bytes at `image_url`, the exact path the API returned (FR-1)."""
        response = await self._request("GET", image_url, telegram_user_id)
        return response.content

    async def check_answer(
        self, telegram_user_id: int, number: str, answer: bool, session_id: str
    ) -> bool:
        """Calls `POST /quiz-questions/{number}/check` (FR-2, spec 0016 FR-5)."""
        response = await self._request(
            "POST",
            f"/quiz-questions/{number}/check",
            telegram_user_id,
            json={"answer": answer, "session_id": session_id},
        )
        return bool(response.json()["correct"])

    async def get_explanation(
        self, telegram_user_id: int, number: str, submitted: bool
    ) -> QuizExplanation:
        """Calls `GET /quiz-questions/{number}/explanation` (FR-2)."""
        response = await self._request(
            "GET",
            f"/quiz-questions/{number}/explanation",
            telegram_user_id,
            params={"submitted": submitted},
        )
        return QuizExplanation.model_validate(response.json())

    async def _request(
        self, method: str, url: str, telegram_user_id: int, **kwargs: Any
    ) -> httpx.Response:
        """Issues one HTTP call, attaching identity and wrapping any failure.

        Covers FR-5, FR-6, FR-10.
        """
        headers = {"X-Telegram-User-Id": str(telegram_user_id)}
        try:
            response = await self._http.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == HTTPStatus.FORBIDDEN:
                raise UnauthorizedError(f"{method} {url} failed: {exc}") from exc
            raise QuizApiError(f"{method} {url} failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise QuizApiError(f"{method} {url} failed: {exc}") from exc
        return response
