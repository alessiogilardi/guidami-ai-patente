from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import QuizEvaluationRow
from retrieval_evaluation.models import CandidateComma

from .question_lexeme_service import QuestionLexemeService


class CandidateSetService:
    """Builds the two-arm candidate union for a quiz question (FR-5, FR-9).

    Unions the dense and text arms' results, keyed by comma id, carrying each arm's
    one-based rank on the matching `CandidateComma`. The result is not truncated,
    sorted or fused (AD-3): its length is that of the full union, in dict insertion
    order (dense arm first, then text-only commas) — no ordering contract beyond
    determinism is promised here.
    """

    def __init__(
        self,
        dense_k: int,
        text_k: int,
        corpus_repository: CorpusReadRepository,
        lexeme_service: QuestionLexemeService,
    ) -> None:
        """Injects the arm depths and the retrieval collaborators."""
        self._dense_k = dense_k
        self._text_k = text_k
        self._corpus_repository = corpus_repository
        self._lexeme_service = lexeme_service

    def build(self, row: QuizEvaluationRow) -> list[CandidateComma]:
        """Returns every comma retrieved by either arm for `row`, each with its ranks."""
        dense_results = self._corpus_repository.dense_top_k(row.embedding, self._dense_k)
        lexemes = self._lexeme_service.build(row)
        text_results = (
            self._corpus_repository.text_match_top_k(lexemes, self._text_k) if lexemes else []
        )

        merged: dict[int, CandidateComma] = {}
        for index, comma in enumerate(dense_results):
            merged[comma.id] = CandidateComma(comma=comma, dense_rank=index + 1)
        for index, comma in enumerate(text_results):
            existing = merged.get(comma.id)
            if existing is not None:
                merged[comma.id] = existing.model_copy(update={"text_rank": index + 1})
            else:
                merged[comma.id] = CandidateComma(comma=comma, text_rank=index + 1)

        return list(merged.values())
