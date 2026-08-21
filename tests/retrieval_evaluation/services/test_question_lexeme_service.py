from unittest.mock import MagicMock

from commons.repositories.db import CorpusReadRepository
from domain.enums import LexemeField
from domain.models.retrieval import QuizEvaluationRow
from retrieval_evaluation.services import QuestionLexemeService


def _make_row(
    topic: str = "Segnaletica",
    text: str = "Il segnale indica obbligo di fermata.",
    image_description: str | None = "Un cartello triangolare con bordo rosso.",
) -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number="1",
        topic=topic,
        text=text,
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        image_description=image_description,
        embedding=[0.1, 0.2],
    )


def test_build_uses_all_three_configured_fields() -> None:
    repository = MagicMock(spec=CorpusReadRepository)
    repository.extract_lexemes.return_value = ["lexeme"]
    row = _make_row(
        topic="SENTINEL_TOPIC", text="SENTINEL_TEXT", image_description="SENTINEL_IMAGE"
    )
    service = QuestionLexemeService(
        lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT, LexemeField.IMAGE_DESCRIPTION),
        repository=repository,
    )

    service.build(row)

    repository.extract_lexemes.assert_called_once()
    (called_text,), _ = repository.extract_lexemes.call_args
    assert "SENTINEL_TOPIC" in called_text
    assert "SENTINEL_TEXT" in called_text
    assert "SENTINEL_IMAGE" in called_text


def test_build_skips_a_missing_image_description() -> None:
    repository = MagicMock(spec=CorpusReadRepository)
    repository.extract_lexemes.return_value = ["lexeme"]
    row = _make_row(topic="SENTINEL_TOPIC", text="SENTINEL_TEXT", image_description=None)
    service = QuestionLexemeService(
        lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT, LexemeField.IMAGE_DESCRIPTION),
        repository=repository,
    )

    service.build(row)

    (called_text,), _ = repository.extract_lexemes.call_args
    assert "SENTINEL_TOPIC" in called_text
    assert "SENTINEL_TEXT" in called_text
    assert "None" not in called_text


def test_build_quotes_each_returned_lexeme() -> None:
    repository = MagicMock(spec=CorpusReadRepository)
    repository.extract_lexemes.return_value = ["e-mail", "sosta"]
    service = QuestionLexemeService(lexeme_fields=(LexemeField.TEXT,), repository=repository)

    result = service.build(_make_row())

    assert result == ["'e-mail'", "'sosta'"]


def test_build_is_driven_by_the_configured_field_list() -> None:
    repository = MagicMock(spec=CorpusReadRepository)
    repository.extract_lexemes.return_value = ["lexeme"]
    row = _make_row(
        topic="SENTINEL_TOPIC", text="SENTINEL_TEXT", image_description="SENTINEL_IMAGE"
    )
    service = QuestionLexemeService(lexeme_fields=(LexemeField.TEXT,), repository=repository)

    service.build(row)

    (called_text,), _ = repository.extract_lexemes.call_args
    assert "SENTINEL_TEXT" in called_text
    assert "SENTINEL_TOPIC" not in called_text
    assert "SENTINEL_IMAGE" not in called_text
