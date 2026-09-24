"""HTTP adapter to the guidami-ai-patente API — one method per endpoint shape (AD-1)."""

from http import HTTPStatus
from typing import Any, Self

import httpx
from pywire import Autowired

from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.enums import ExplanationStatus
from guidami_ai_patente_bot.exceptions import QuizApiError, UnauthorizedError
from guidami_ai_patente_bot.models import (
    CitedGlossaryTerm,
    QuizExplanation,
    QuizQuestion,
    SessionSummary,
)


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
    ) -> tuple[bool, ExplanationStatus]:
        """Calls `POST /quiz-questions/{number}/check` (FR-2, spec 0016 FR-5, spec 0017 FR-6)."""
        response = await self._request(
            "POST",
            f"/quiz-questions/{number}/check",
            telegram_user_id,
            json={"answer": answer, "session_id": session_id},
        )
        body = response.json()
        return bool(body["correct"]), ExplanationStatus(body["explanation_status"])

    async def label_question(self, telegram_user_id: int, number: str) -> None:
        """Calls `POST /quiz-questions/{number}/label` (spec 0017, FR-4).

        Passes an explicit timeout override: the server's own `labeling_deadline_s`
        defaults to 25.0s, longer than `request_timeout_seconds`'s 15.0s default,
        which is tuned for the other, fast endpoints (AD-10).
        """
        await self._request(
            "POST",
            f"/quiz-questions/{number}/label",
            telegram_user_id,
            timeout=self.config.label_request_timeout_seconds,
        )

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

    async def translate_explanation(
        self, telegram_user_id: int, text: str, hints: tuple[CitedGlossaryTerm, ...] = ()
    ) -> str:
        """Calls `POST /explanations/translate?lang=ru` (spec 0018 bot UX, spec 0020 FR-7).

        Only "ru" is wired today — the bot has no language picker yet, and the
        query parameter stays hardcoded until a second language is offered.
        Passes an explicit timeout override for the same reason `label_question`
        does: the server's own deadline is longer than the client's generic default.

        `hints` is forwarded as `{"term": ..., "term_ru": ...}` pairs, matching
        `ExplanationTranslationRequest.hints`'s `TranslationHintRequest` shape exactly —
        never `definition`, which is local render data only (FR-7) and has no
        equivalent field on the wire schema. A hint whose `term_ru` is `None` (no
        translation yet, spec 0019 AD-11) is silently omitted rather than forwarded as
        `"term_ru": null` — the wire schema's `min_length=1` would reject the whole
        request for that one untranslated hint.
        """
        response = await self._request(
            "POST",
            "/explanations/translate",
            telegram_user_id,
            params={"lang": "ru"},
            json={
                "text": text,
                "hints": [
                    {"term": h.term, "term_ru": h.term_ru} for h in hints if h.term_ru is not None
                ],
            },
            timeout=self.config.translation_request_timeout_seconds,
        )
        return str(response.json()["translated_text"])

    async def get_session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        """Calls `GET /quiz-answers/summary` (spec 0016, FR-9, AD-16)."""
        response = await self._request(
            "GET", "/quiz-answers/summary", telegram_user_id, params={"session_id": session_id}
        )
        return SessionSummary.model_validate(response.json())

    async def _request(
        self,
        method: str,
        url: str,
        telegram_user_id: int,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Issues one HTTP call, attaching identity and wrapping any failure.

        Covers FR-5, FR-6, FR-10. `timeout`, when given, overrides the client's
        default for this one call only (spec 0017, AD-10) — when omitted, the
        request kwarg is not passed at all, so httpx falls back to the client's own
        configured default rather than to `None`, which would mean "no timeout."
        """
        headers = {"X-Telegram-User-Id": str(telegram_user_id)}
        if timeout is not None:
            kwargs["timeout"] = timeout
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
