from collections.abc import Sequence

from commons.repositories.db import CorpusReadRepository
from domain.enums import LexemeField
from domain.models.retrieval import QuizEvaluationRow


class QuestionLexemeService:
    """Builds the lexeme list a quiz question's text arm is matched against (FR-4).

    Composes and concatenates the configured `QuizEvaluationRow` fields, then delegates
    extraction to `CorpusReadRepository.extract_lexemes` so both extraction and search
    share the same `italian` dictionary (PD-5).
    """

    def __init__(
        self, lexeme_fields: Sequence[LexemeField], repository: CorpusReadRepository
    ) -> None:
        """Injects the configured lexeme sources and the corpus read repository."""
        self._lexeme_fields = lexeme_fields
        self._repository = repository

    def build(self, row: QuizEvaluationRow) -> list[str]:
        """Returns `row`'s lexemes, quoted for `to_tsquery` (PD-6).

        Reads each configured field off `row`, drops blank/`None` values, and joins
        the survivors with a newline before extraction. Returns `[]` without calling
        the repository when nothing survives.
        """
        values = [getattr(row, field.value) for field in self._lexeme_fields]
        survivors = [value.strip() for value in values if value is not None and value.strip()]
        if not survivors:
            return []
        lexemes = self._repository.extract_lexemes("\n".join(survivors))
        return [f"'{lexeme.replace(chr(39), chr(39) * 2)}'" for lexeme in lexemes]
