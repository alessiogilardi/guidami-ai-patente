import random

from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from domain.models.retrieval import QuizEvaluationRow
from retrieval_evaluation.agents import RetrievalJudgeAgent
from retrieval_evaluation.agents.dto.retrieval_judge import RetrievalJudgeRequest
from retrieval_evaluation.models import RetrievalJudgeItemResult


class RetrievalJudgeEvaluationService:
    """Samples random quiz questions and judges retrieval quality for each.

    For every sampled question, retrieves the `k` closest commas by dense retrieval and
    asks `RetrievalJudgeAgent` whether they clearly and unambiguously justify the
    question's correct answer.
    """

    def __init__(
        self,
        k: int,
        variant: str,
        quiz_repository: QuizReadRepository,
        corpus_repository: CorpusReadRepository,
        agent: RetrievalJudgeAgent,
    ) -> None:
        """Injects the run parameters and the two read repositories plus the judge agent."""
        self._k = k
        self._variant = variant
        self._quiz_repository = quiz_repository
        self._corpus_repository = corpus_repository
        self._agent = agent

    def evaluate(self, n: int, rng: random.Random) -> list[RetrievalJudgeItemResult]:
        """Judges a random sample of `n` quiz questions (capped at the available rows).

        `rng` is caller-supplied so each invocation of the harness can draw an
        independent, seedable sample.
        """
        rows = self._quiz_repository.fetch_with_vectors(self._variant)
        sample = rng.sample(rows, k=min(n, len(rows)))
        return [self._judge_one(row) for row in sample]

    def _judge_one(self, row: QuizEvaluationRow) -> RetrievalJudgeItemResult:
        commas = self._corpus_repository.dense_top_k(row.embedding, self._k)
        request = RetrievalJudgeRequest(
            quiz_text=row.text, correct_answer=row.correct_answer, commas=commas
        )
        response = self._agent.run_sync(request)
        return RetrievalJudgeItemResult(
            quiz_number=row.number, is_clear=response.is_clear, rationale=response.rationale
        )
