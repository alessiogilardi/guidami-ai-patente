"""Quiz question endpoints: propose, list topics, fetch, check."""

import asyncio

from fastapi import APIRouter, Query
from pywire import Autowired

from guidami_ai_patente.mappers import QuizQuestionMapper
from guidami_ai_patente.services import QuizAnswerChecker, QuizProposalService

from ..schemas.quiz_check import QuizCheckRequest, QuizCheckResponse
from ..schemas.quiz_question import QuizQuestionResponse
from ..schemas.quiz_topics import QuizTopicResponse, QuizTopicsResponse

router = APIRouter(prefix="/quiz-questions", tags=["quiz-questions"])


@router.get("/topics", response_model=QuizTopicsResponse)
async def list_topics(service: Autowired[QuizProposalService]) -> QuizTopicsResponse:
    """Lists the distinct topics with their question counts (FR-16).

    Declared before `/{number}` on purpose: FastAPI matches in declaration order, so
    the parameterised route would otherwise swallow this literal path and answer 404
    for a question numbered "topics".
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
    number: str, service: Autowired[QuizProposalService]
) -> QuizQuestionResponse:
    """Returns one question by its number, in the proposal's shape (FR-2)."""
    summary = await asyncio.to_thread(service.fetch, number)
    return QuizQuestionMapper.from_summary_to_response(summary)


@router.post("/{number}/check", response_model=QuizCheckResponse)
async def check_answer(
    number: str, request: QuizCheckRequest, checker: Autowired[QuizAnswerChecker]
) -> QuizCheckResponse:
    """Grades the submitted answer and advertises the explanation status (FR-3, FR-4)."""
    correct, explanation_status = await asyncio.to_thread(checker.check, number, request.answer)
    return QuizCheckResponse(correct=correct, explanation_status=explanation_status)
