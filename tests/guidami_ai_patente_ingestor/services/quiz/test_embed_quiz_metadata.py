"""Tests for EmbedQuizMetadata (UseCase that computes the embedding from quiz_metadata)."""

from unittest.mock import MagicMock

from commons.ai.embedding import EmbeddingService
from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel, QuizMetadata
from guidami_ai_patente_ingestor.services.quiz import EmbedQuizMetadata


def _metadata(**kwargs) -> QuizMetadata:
    defaults = dict(
        core_concepts=["Obbligo di precedenza"],
        exact_keywords=["preavviso di incrocio"],
        vector_search_queries=["prima query di ricerca", "seconda query di ricerca"],
        rule_explanation="Il segnale preavvisa un incrocio regolato.",
    )
    return QuizMetadata(**{**defaults, **kwargs})


def _question(**kwargs) -> EmbeddedQuizModel:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Il segnale raffigurato preavvisa un incrocio.",
        correct_answer=True,
    )
    return EmbeddedQuizModel(**{**defaults, **kwargs})


def test_embeds_vector_search_queries() -> None:
    """The text passed to EmbeddingService is vector_search_queries via quiz_metadata."""
    metadata = _metadata(vector_search_queries=["query uno", "query due"])
    item = _question(quiz_metadata=metadata)
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.return_value = [[1.0, 2.0]]
    use_case = EmbedQuizMetadata(embedding_service)

    result = use_case.execute([item])

    embedding_service.assert_called_once()
    (passed,), _ = embedding_service.call_args
    assert [entry.embedded_text for entry in passed] == ["query uno\nquery due"]
    assert result[0].embedding == [1.0, 2.0]


def test_skips_quiz_without_metadata() -> None:
    """Item con quiz_metadata=None restano invariati: nessuna chiamata a EmbeddingService."""
    item = _question(quiz_metadata=None)
    embedding_service = MagicMock(spec=EmbeddingService)
    use_case = EmbedQuizMetadata(embedding_service)

    result = use_case.execute([item])

    embedding_service.assert_not_called()
    assert result[0].embedding is None


def test_embedding_failure_skips_batch(caplog) -> None:
    """Se EmbeddingService solleva, tutti gli item restano invariati con warning."""
    item = _question(quiz_metadata=_metadata())
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.side_effect = RuntimeError("embedding backend unavailable")
    use_case = EmbedQuizMetadata(embedding_service)

    with caplog.at_level("WARNING"):
        result = use_case.execute([item])

    assert result[0].embedding is None
    assert any(record.levelname == "WARNING" for record in caplog.records), (
        "expected a WARNING log entry when EmbeddingService raises"
    )
