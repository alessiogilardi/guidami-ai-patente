"""Quiz question endpoints: propose, list topics, fetch, check."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pywire import Autowired

from domain.entities.users import UserEntity
from guidami_ai_patente.mappers import ExplanationMapper, QuizQuestionMapper
from guidami_ai_patente.models import ExplanationRequest, QuizAnswerCheckRequest
from guidami_ai_patente.services import ExplanationService, QuizAnswerChecker, QuizProposalService

from ..dependencies.user_identity import require_registered_user
from ..schemas.quiz_check import QuizCheckRequest, QuizCheckResponse
from ..schemas.quiz_explanation import QuizExplanationResponse
from ..schemas.quiz_question import QuizQuestionResponse
from ..schemas.quiz_topics import QuizTopicResponse, QuizTopicsResponse

router = APIRouter(prefix="/quiz-questions", tags=["quiz-questions"])

_RequireRegisteredUser = Annotated[UserEntity, Depends(require_registered_user)]


@router.get("/topics", response_model=QuizTopicsResponse)
async def list_topics(
    user: _RequireRegisteredUser, service: Autowired[QuizProposalService]
) -> QuizTopicsResponse:
    """Lists the distinct topics with their question counts (FR-16).

    Declared before `/{number}` on purpose: FastAPI matches in declaration order, so
    the parameterised route would otherwise swallow this literal path and answer 404
    for a question numbered "topics".

    `user` is declared before `service` in the signature — not merely a style choice:
    pywire's `_wire_endpoint` rewrites a bare `Autowired[T]` parameter into one with a
    real Python-level default (`Depends(...)`), while `user`'s `Annotated[X,
    Depends(...)]` form carries no such default at the raw signature level. Since
    FastAPI/pywire resolves every dependency by name, not position, reordering is
    behavior-preserving — but Python itself refuses a signature where a required
    (no-default) parameter follows one that has a default, so every route in this
    file puts `user` ahead of any `Autowired[T]` parameter.
    """
    topics = await asyncio.to_thread(service.topics)
    return QuizTopicsResponse(
        topics=[
            QuizTopicResponse(topic=topic.topic, question_count=topic.question_count)
            for topic in topics
        ]
    )


@router.get("/random", response_model=QuizQuestionResponse)
async def propose_question(
    user: _RequireRegisteredUser,
    service: Autowired[QuizProposalService],
    seed: str = Query(description="Client-owned seed; the same seed yields the same permutation."),
    index: int = Query(ge=0, description="Position within the seeded permutation."),
    topic: str | None = Query(default=None, description="Restrict to one topic (see /topics)."),
) -> QuizQuestionResponse:
    """Proposes the question at `index` of the permutation `seed` induces (FR-1)."""
    summary = await asyncio.to_thread(service.propose, seed, index, topic)
    return QuizQuestionMapper.from_summary_to_response(summary)


@router.get("/{number}", response_model=QuizQuestionResponse)
async def fetch_question(
    number: str, user: _RequireRegisteredUser, service: Autowired[QuizProposalService]
) -> QuizQuestionResponse:
    """Returns one question by its number, in the proposal's shape (FR-2)."""
    summary = await asyncio.to_thread(service.fetch, number)
    return QuizQuestionMapper.from_summary_to_response(summary)


@router.post("/{number}/check", response_model=QuizCheckResponse)
async def check_answer(
    number: str,
    request: QuizCheckRequest,
    user: _RequireRegisteredUser,
    checker: Autowired[QuizAnswerChecker],
) -> QuizCheckResponse:
    """Grades the submitted answer, records it, and advertises the explanation status."""
    correct, explanation_status = await asyncio.to_thread(
        checker,
        QuizAnswerCheckRequest(
            number=number,
            submitted_answer=request.answer,
            session_id=request.session_id,
            telegram_user_id=user.telegram_user_id,
        ),
    )
    return QuizCheckResponse(correct=correct, explanation_status=explanation_status)


@router.get("/{number}/explanation", response_model=QuizExplanationResponse)
async def explain_answer(
    number: str,
    user: _RequireRegisteredUser,
    service: Autowired[ExplanationService],
    submitted: bool | None = Query(
        default=None,
        description=(
            "The answer the user submitted, so the explanation can address a wrong "
            "answer directly. Omit for a neutral explanation."
        ),
    ),
) -> QuizExplanationResponse:
    """Explains why the correct answer is what it is, grounded in the corpus (FR-5, FR-11).

    No `asyncio.to_thread` here: the service is genuinely async — it awaits the judge
    and the writer, and crosses into the synchronous SQL stack itself (AD-25).

    A cache miss runs retrieval plus the judge before answering, so this call can take
    seconds; `POST /{number}/check`'s `explanation_status` is what lets a client decide
    which affordance to offer beforehand (FR-4).
    """
    explanation = await service(ExplanationRequest(number=number, submitted=submitted))
    return ExplanationMapper.from_explanation_to_response(explanation)
