"""GET /quiz-answers/summary: a session's answered/correct counts (spec 0016, FR-9)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pywire import Autowired

from domain.entities.users import UserEntity
from guidami_ai_patente.models import SessionSummaryRequest
from guidami_ai_patente.services import SessionSummaryService

from ..dependencies.user_identity import require_registered_user
from ..schemas.quiz_answers import SessionSummaryResponse

router = APIRouter(prefix="/quiz-answers", tags=["quiz-answers"])


@router.get("/summary", response_model=SessionSummaryResponse)
async def get_session_summary(
    user: Annotated[UserEntity, Depends(require_registered_user)],
    service: Autowired[SessionSummaryService],
    session_id: str = Query(description="The bot's per-QuizSession seed."),
) -> SessionSummaryResponse:
    """Returns the session's answered/correct counts, scoped by both user and session.

    Plain `await`, not `asyncio.to_thread`: `SessionSummaryService` is an
    `AsyncUseCase` (see its own docstring) — the sync-to-thread crossing already
    happened inside `execute`, so the router just awaits it, unlike every other
    `UseCase`-backed route in this package (AD-25). Scoped by `telegram_user_id` too,
    not just `session_id` (AD-16): a caller can never read another user's session
    summary by guessing/reusing a `session_id`.

    `user` is declared before `service`: pywire's `_wire_endpoint` gives a bare
    `Autowired[T]` parameter a real Python-level default, while `user`'s
    `Annotated[X, Depends(...)]` form has none — see `quiz_questions.py::list_topics`
    for the full explanation of why this ordering is required.
    """
    summary = await service(
        SessionSummaryRequest(telegram_user_id=user.telegram_user_id, session_id=session_id)
    )
    return SessionSummaryResponse(answered=summary.answered, correct=summary.correct)
