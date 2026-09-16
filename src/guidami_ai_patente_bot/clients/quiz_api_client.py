"""HTTP adapter to the guidami-ai-patente API — one method per endpoint shape (AD-1)."""

from typing import Any, Self

import httpx
from pywire import Autowired, async_component

from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.exceptions import QuizApiError
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion


@async_component
class QuizApiClient:
    """Thin async adapter over `guidami_ai_patente`'s HTTP API (AD-1, AD-8).

    An `@async_component` (pywire 0.9.0): the container builds `self.config` first
    (ordinary field injection), then enters this bean via `__aenter__` inside
    `container.lifespan()` (Task 6's `main.py`), and exits it via `__aexit__` on the
    same container's `aclose()`, in reverse registration order. This supersedes
    ADR 0032's original v0.8.0-era workaround (a hand-called `await client.aclose()`
    from `main.py`, with no pywire teardown hook at all) now that pywire ships
    real async-component support.
    """

    config: Autowired[BotConfig]

    async def __aenter__(self) -> Self:
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self.config.api_base_url, timeout=self.config.request_timeout_seconds
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._http.aclose()

    async def propose_question(self, seed: str, index: int) -> QuizQuestion:
        """Calls `GET /quiz-questions/random` (FR-1, FR-4)."""
        response = await self._request(
            "GET", "/quiz-questions/random", params={"seed": seed, "index": index}
        )
        return QuizQuestion.model_validate(response.json())

    async def download_image(self, image_url: str) -> bytes:
        """Downloads the bytes at `image_url`, the exact path the API returned (FR-1)."""
        response = await self._request("GET", image_url)
        return response.content

    async def check_answer(self, number: str, answer: bool) -> bool:
        """Calls `POST /quiz-questions/{number}/check` (FR-2)."""
        response = await self._request(
            "POST", f"/quiz-questions/{number}/check", json={"answer": answer}
        )
        return bool(response.json()["correct"])

    async def get_explanation(self, number: str, submitted: bool) -> QuizExplanation:
        """Calls `GET /quiz-questions/{number}/explanation` (FR-2)."""
        response = await self._request(
            "GET", f"/quiz-questions/{number}/explanation", params={"submitted": submitted}
        )
        return QuizExplanation.model_validate(response.json())

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Issues one HTTP call, wrapping any failure into a single `QuizApiError` (FR-5)."""
        try:
            response = await self._http.request(method, url, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QuizApiError(f"{method} {url} failed: {exc}") from exc
        return response
