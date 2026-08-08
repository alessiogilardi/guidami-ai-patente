import asyncio
import random

from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from domain.models.retrieval import QuizEvaluationRow
from retrieval_evaluation.agents import RetrievalJudgeAgent
from retrieval_evaluation.agents.retrieval_judge.dto import RetrievalJudgeRequest
from retrieval_evaluation.models import RetrievalJudgeItemResult


class RetrievalJudgeEvaluationService:
    """Samples random quiz questions and judges retrieval quality for each.

    For every sampled question, retrieves the `k` closest commas by dense retrieval and
    asks `RetrievalJudgeAgent` whether they clearly and unambiguously justify the
    question's correct answer. Judge calls run concurrently under `asyncio.gather`,
    bounded by a semaphore (`max_concurrency`) — same pattern as
    `NormReferenceEnricherService`/`ImageDescriptionEnricherService`.
    """

    def __init__(
        self,
        k: int,
        variant: str,
        max_concurrency: int,
        quiz_repository: QuizReadRepository,
        corpus_repository: CorpusReadRepository,
        agent: RetrievalJudgeAgent,
    ) -> None:
        """Injects the run parameters and the two read repositories plus the judge agent."""
        self._k = k
        self._variant = variant
        self._max_concurrency = max_concurrency
        self._quiz_repository = quiz_repository
        self._corpus_repository = corpus_repository
        self._agent = agent

    async def evaluate(self, n: int, rng: random.Random) -> list[RetrievalJudgeItemResult]:
        """Judges a random sample of `n` quiz questions (capped at the available rows).

        `rng` is caller-supplied so each invocation of the harness can draw an
        independent, seedable sample.
        """
        rows = self._load_rows()
        sample = rng.sample(rows, k=min(n, len(rows)))
        return await self._judge_all(sample)

    async def evaluate_all(self) -> list[RetrievalJudgeItemResult]:
        """Judges every quiz question with a query vector for the configured variant."""
        return await self._judge_all(self._load_rows())

    def _load_rows(self) -> list[QuizEvaluationRow]:
        # "embedding_3_small" is the only model column that exists today (AD-6); T-12
        # generalized fetch_with_vectors to take model_column explicitly, but this
        # service (outside plan 0008 Phase 2's Files list) has no second model to pick
        # between yet either.
        return self._quiz_repository.fetch_with_vectors(self._variant, "embedding_3_small")

    async def _judge_all(self, rows: list[QuizEvaluationRow]) -> list[RetrievalJudgeItemResult]:
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        return list(await asyncio.gather(*(self._judge_one(row, semaphore) for row in rows)))

    async def _judge_one(
        self, row: QuizEvaluationRow, semaphore: asyncio.Semaphore
    ) -> RetrievalJudgeItemResult:
        commas = self._corpus_repository.dense_top_k(row.embedding, self._k)
        request = RetrievalJudgeRequest(
            quiz_text=row.text,
            correct_answer=row.correct_answer,
            commas=commas,
            image_description=row.image_description
            or "Nessuna immagine allegata a questa domanda.",
        )
        async with semaphore:
            response = await self._agent.run(request)
        return RetrievalJudgeItemResult(
            quiz_number=row.number,
            topic=row.topic,
            text=row.text,
            correct_answer=row.correct_answer,
            image_filename=row.image_filename,
            image_description=row.image_description,
            retrieved_commas=commas,
            is_clear=response.is_clear,
            rationale=response.rationale,
        )
