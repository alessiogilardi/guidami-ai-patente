import asyncio
import logging
import random
from collections.abc import Sequence

import httpx
from pydantic_ai.exceptions import ModelHTTPError

from commons.repositories.db import QuizReadRepository
from commons.use_cases import AsyncUseCase
from domain.entities.evaluation import QuizCommaLabelEntity, QuizLabelingEntity
from domain.models.retrieval import QuizEvaluationRow
from labeling.agents import CommaLabelerAgent
from labeling.agents.comma_labeler.dto import CommaLabelerRequest, CommaLabelerResponse
from labeling.constants import EMBEDDING_MODEL_COLUMN
from labeling.exceptions import CandidateNumberOutOfRangeError
from labeling.models import CandidateComma
from labeling.repositories import GoldenSetWriteRepository

from .candidate_set_service import CandidateSetService

logger = logging.getLogger(__name__)

# Retried transport-level failures only (PD-17): a network blip is recoverable, a
# hallucinated ordinal or a permanent 4xx is not.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_NO_CANDIDATES_RATIONALE = "Nessun candidato recuperato per questa domanda."


class GoldenSetLabelingService(AsyncUseCase[int, int]):
    """Runs the labeling pass over every quiz question with a query vector (FR-6, FR-7, FR-10).

    For each question, builds the two-arm candidate union, shuffles it into a
    presentation order seeded per-question (PD-8), asks `CommaLabelerAgent` which
    candidates justify the correct answer, and writes the resulting labeling. Judge
    calls run concurrently under `asyncio.gather`, bounded by a semaphore built inside
    `execute` — never on `self` (a semaphore binds to the event loop of its first
    use). The candidate set is built inside that same semaphore (PD-16), so at most
    `max_concurrency` candidate sets are ever alive at once.

    An out-of-range candidate number, or any non-transport failure, propagates and
    aborts the whole run (PD-9): `asyncio.gather` is never called with
    `return_exceptions=True`, so an incomplete run cannot look complete.

    `topics`, when given, restricts *which* questions are labeled to those whose
    `topic` is in the set (FR-18) — it is applied before `question_limit`, so
    `--limit N --topic t` means "N questions of topic t", not "the first N of the
    bank, of which some happen to be topic t". It is purely a selection criterion:
    it never reaches `labeling_runs` and is not part of the judge's configuration
    epoch, since it changes which questions are judged, not how they are judged.
    """

    def __init__(
        self,
        candidate_variant: str,
        shuffle_seed: int,
        max_concurrency: int,
        transport_retries: int,
        retry_backoff_seconds: float,
        question_limit: int | None,
        topics: Sequence[str] | None,
        quiz_repository: QuizReadRepository,
        candidate_set_service: CandidateSetService,
        write_repository: GoldenSetWriteRepository,
        agent: CommaLabelerAgent,
    ) -> None:
        """Injects the run parameters and the read/write collaborators."""
        self._candidate_variant = candidate_variant
        self._shuffle_seed = shuffle_seed
        self._max_concurrency = max_concurrency
        self._transport_retries = transport_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._question_limit = question_limit
        self._topics = frozenset(topics) if topics else None
        self._quiz_repository = quiz_repository
        self._candidate_set_service = candidate_set_service
        self._write_repository = write_repository
        self._agent = agent

    async def execute(self, request: int) -> int:
        """Labels every question with a vector for the configured variant.

        `request` is the batch/live run id. Restricted to `self._topics` when set
        (FR-18), applied before `self._question_limit`. Then restricted to
        `self._question_limit` questions when set, selected by a seeded shuffle so
        the same limit and seed always select the same subset (PD-18); unrestricted
        (the default) labels every question (FR-10).

        Returns:
            The number of questions labeled (before any labeling could fail).
        """
        rows = self._quiz_repository.fetch_with_vectors(
            self._candidate_variant, EMBEDDING_MODEL_COLUMN
        )
        if self._topics is not None:
            # Filters before the limit, so `--limit N --topic t` means "N questions
            # of t", not "the first N of the bank, of which some are t" (FR-18).
            rows = [row for row in rows if row.topic in self._topics]
        if self._question_limit is not None:
            shuffled = list(rows)
            random.Random(f"limit:{self._shuffle_seed}").shuffle(shuffled)
            rows = shuffled[: self._question_limit]

        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        await asyncio.gather(*(self._label_one(row, request, semaphore) for row in rows))
        return len(rows)

    async def _label_one(
        self, row: QuizEvaluationRow, run_id: int, semaphore: asyncio.Semaphore
    ) -> None:
        async with semaphore:
            candidates = self._candidate_set_service(row)
            if not candidates:
                labeling_id = self._write_repository.insert_labeling(
                    QuizLabelingEntity(
                        run_id=run_id,
                        quiz_question_id=row.id,
                        rationale=_NO_CANDIDATES_RATIONALE,
                    ),
                    [],
                )
                if labeling_id is None:
                    # D6: in the batch path `insert_run` just created this run_id and
                    # each question is visited once, so a conflict is a defect, not a
                    # race. It is a `warning`, and the discarded write is NOT counted
                    # as a labeling. `debug`-and-continue belongs to the API caller in
                    # plan 3, where losing the race is the designed outcome (AD-19).
                    logger.warning(
                        "Unexpected: labeling for quiz %s already existed under batch "
                        "run %d, write discarded",
                        row.number,
                        run_id,
                    )
                return

            presented = list(candidates)
            random.Random(f"{self._shuffle_seed}:{row.id}").shuffle(presented)

            request = CommaLabelerRequest(
                quiz_text=row.text,
                correct_answer=row.correct_answer,
                candidates=[candidate.comma for candidate in presented],
                image_description=row.image_description
                or "Nessuna immagine allegata a questa domanda.",
            )
            logger.debug("Labeling quiz %s with %d candidate(s)", row.number, len(presented))
            response = await self._call_agent(row.number, request)

            labels = self._resolve_labels(row.number, response, presented)
            labeling_id = self._write_repository.insert_labeling(
                QuizLabelingEntity(
                    run_id=run_id, quiz_question_id=row.id, rationale=response.rationale
                ),
                labels,
            )
            if labeling_id is None:
                # D6: in the batch path `insert_run` just created this run_id and each
                # question is visited once, so a conflict is a defect, not a race. It is
                # a `warning`, and the discarded write is NOT counted as a labeling.
                # `debug`-and-continue belongs to the API caller in plan 3, where losing
                # the race is the designed outcome (AD-19).
                logger.warning(
                    "Unexpected: labeling for quiz %s already existed under batch run %d, "
                    "write discarded",
                    row.number,
                    run_id,
                )
            else:
                logger.info("Labeled quiz %s with %d comma(s)", row.number, len(labels))

    @staticmethod
    def _resolve_labels(
        quiz_number: str, response: CommaLabelerResponse, presented: list[CandidateComma]
    ) -> list[QuizCommaLabelEntity]:
        """Resolves each returned ordinal to its presented candidate (AD-12).

        Raises:
            CandidateNumberOutOfRangeError: A returned ordinal is outside the
                presented range — the run fails for this question rather than
                recording a label (FR-7, PD-9).
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

        Retries `httpx.TransportError` and a `ModelHTTPError` whose `status_code` is
        in `_RETRYABLE_STATUS_CODES`, up to `transport_retries` attempts, sleeping
        `retry_backoff_seconds * 2 ** attempt` between attempts. Every other
        exception — including a permanent `ModelHTTPError`, `UnexpectedModelBehavior`
        and `pydantic.ValidationError` — propagates immediately. On the final failed
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
