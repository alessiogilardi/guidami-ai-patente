"""The one implementation of "judge this question and record the verdict"."""

import asyncio
import logging
import random

import httpx
from pydantic_ai.exceptions import ModelHTTPError

from commons.use_cases import AsyncUseCase
from domain.entities.evaluation import QuizCommaLabelEntity, QuizLabelingEntity
from labeling.agents import CommaLabelerAgent
from labeling.agents.comma_labeler.dto import CommaLabelerRequest, CommaLabelerResponse
from labeling.exceptions import CandidateNumberOutOfRangeError
from labeling.models import CandidateComma, QuestionLabelingRequest
from labeling.repositories import GoldenSetWriteRepository

from .candidate_set_service import CandidateSetService

logger = logging.getLogger(__name__)

# Retried transport-level failures only (PD-17): a network blip is recoverable, a
# hallucinated ordinal or a permanent 4xx is not.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_NO_CANDIDATES_RATIONALE = "Nessun candidato recuperato per questa domanda."
_NO_IMAGE_DESCRIPTION = "Nessuna immagine allegata a questa domanda."


class QuestionLabelingService(AsyncUseCase[QuestionLabelingRequest, int | None]):
    """Labels one question: retrieve, shuffle, judge, resolve ordinals, write (FR-6).

    Extracted out of `GoldenSetLabelingService` so the batch pass and the API's live
    cache fill run **one** implementation (AD-12). That is not tidiness: the epoch key
    records the model, the prompt hash, the arm depths, the variant and the lexeme
    fields, but not the presentation order, the exact prompt text or the retry policy.
    Three details here are inputs the judge reads — the per-question shuffle seed, the
    absent-image fallback and the no-candidate rationale — so a second implementation
    would let one epoch key cover two different judges, undetectably.

    Synchronous collaborators are crossed with `asyncio.to_thread` (AD-25): the API
    must not block its event loop, and the batch gains genuinely parallel DB work under
    its semaphore, which is what the pooled client was introduced for (AD-26).

    The returned id is `None` when another writer already holds
    `(run_id, quiz_question_id)`. That is not an error (AD-19) and the interpretation
    is deliberately left to the caller: for the batch it is a defect worth a `warning`
    (it visits each question once under a run it just created), for the API it is the
    designed outcome of two concurrent misses.

    An out-of-range ordinal, or any non-transport failure, propagates: nothing is
    written and no run id is resolved (FR-13, PD-9).
    """

    def __init__(
        self,
        shuffle_seed: int,
        transport_retries: int,
        retry_backoff_seconds: float,
        candidate_set_service: CandidateSetService,
        write_repository: GoldenSetWriteRepository,
        agent: CommaLabelerAgent,
    ) -> None:
        """Injects the run mechanics and the retrieval/judge/write collaborators."""
        self._shuffle_seed = shuffle_seed
        self._transport_retries = transport_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._candidate_set_service = candidate_set_service
        self._write_repository = write_repository
        self._agent = agent

    async def execute(self, request: QuestionLabelingRequest) -> int | None:
        """Judges `request.row` and writes its labeling.

        Returns:
            The new labeling's id, or `None` when another writer got there first.
        """
        row = request.row
        candidates = await asyncio.to_thread(self._candidate_set_service, row)
        if not candidates:
            logger.debug("No candidate retrieved for quiz %s", row.number)
            return await self._write(request, _NO_CANDIDATES_RATIONALE, [])

        presented = list(candidates)
        random.Random(f"{self._shuffle_seed}:{row.id}").shuffle(presented)

        judge_request = CommaLabelerRequest(
            quiz_text=row.text,
            correct_answer=row.correct_answer,
            candidates=[candidate.comma for candidate in presented],
            image_description=row.image_description or _NO_IMAGE_DESCRIPTION,
        )
        logger.debug("Labeling quiz %s with %d candidate(s)", row.number, len(presented))
        response = await self._call_agent(row.number, judge_request)

        labels = self._resolve_labels(row.number, response, presented)
        labeling_id = await self._write(request, response.rationale, labels)
        if labeling_id is not None:
            logger.info("Labeled quiz %s with %d comma(s)", row.number, len(labels))
        return labeling_id

    async def _write(
        self,
        request: QuestionLabelingRequest,
        rationale: str,
        labels: list[QuizCommaLabelEntity],
    ) -> int | None:
        """Resolves the run id and writes the labeling with its children.

        The run id is resolved **here**, after the judge has answered, so a failed
        judge leaves no `labeling_runs` row behind (AD-20, FR-13).
        """
        run_id = await asyncio.to_thread(request.resolve_run_id)
        return await asyncio.to_thread(
            self._write_repository.insert_labeling,
            QuizLabelingEntity(
                run_id=run_id, quiz_question_id=request.row.id, rationale=rationale
            ),
            labels,
        )

    @staticmethod
    def _resolve_labels(
        quiz_number: str, response: CommaLabelerResponse, presented: list[CandidateComma]
    ) -> list[QuizCommaLabelEntity]:
        """Resolves each returned ordinal to its presented candidate (AD-12).

        Raises:
            CandidateNumberOutOfRangeError: A returned ordinal is outside the presented
                range — this question fails rather than recording a label (FR-7, PD-9).
        """
        labels: list[QuizCommaLabelEntity] = []
        for judge_rank, number in enumerate(response.comma_numbers, start=1):
            if not 1 <= number <= len(presented):
                raise CandidateNumberOutOfRangeError(
                    f"judge returned candidate number {number} for quiz {quiz_number}, "
                    f"but only {len(presented)} candidates were presented"
                )
            candidate = presented[number - 1]
            labels.append(
                QuizCommaLabelEntity(
                    article_comma_id=candidate.comma.id,
                    judge_rank=judge_rank,
                    dense_rank=candidate.dense_rank,
                    text_rank=candidate.text_rank,
                )
            )
        return labels

    async def _call_agent(
        self, quiz_number: str, request: CommaLabelerRequest
    ) -> CommaLabelerResponse:
        """Calls the agent, retrying only transport-level failures (PD-17).

        Retries `httpx.TransportError` and a `ModelHTTPError` whose `status_code` is in
        `_RETRYABLE_STATUS_CODES`, up to `transport_retries` attempts, sleeping
        `retry_backoff_seconds * 2 ** attempt` between attempts. Every other exception
        — including a permanent `ModelHTTPError`, `UnexpectedModelBehavior` and
        `pydantic.ValidationError` — propagates immediately. On the final failed
        attempt the exception propagates unchanged.
        """
        last_exception: BaseException | None = None
        for attempt in range(self._transport_retries):
            try:
                return await self._agent.run(request)
            except httpx.TransportError as exc:
                last_exception = exc
            except ModelHTTPError as exc:
                if exc.status_code not in _RETRYABLE_STATUS_CODES:
                    raise
                last_exception = exc

            if attempt < self._transport_retries - 1:
                logger.warning(
                    "Transport error calling comma labeler for quiz %s (attempt %d/%d), retrying",
                    quiz_number,
                    attempt + 1,
                    self._transport_retries,
                    exc_info=True,
                )
                await asyncio.sleep(self._retry_backoff_seconds * 2**attempt)

        assert last_exception is not None
        raise last_exception
