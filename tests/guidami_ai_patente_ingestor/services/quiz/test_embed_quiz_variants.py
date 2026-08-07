"""Tests for EmbedQuizVariants (UseCase computing every enabled variant's embedding)."""

import pytest

from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel, QuizMetadata
from guidami_ai_patente_ingestor.services.quiz import EmbedQuizVariants


class _RecordingFakeEmbeddingService:
    """Fake EmbeddingService double: returns one vector per text, records every call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def execute(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]


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


def test_embeds_one_row_per_enabled_variant_per_question() -> None:
    with_metadata = _question(number="1", quiz_metadata=_metadata())
    without_metadata = _question(number="2", quiz_metadata=None)
    fake_service = _RecordingFakeEmbeddingService()
    use_case = EmbedQuizVariants(["text", "search_queries"], fake_service)  # type: ignore[arg-type]

    result = use_case.execute([with_metadata, without_metadata])

    assert len(result.variants) == 3
    text_rows = {row.question_number for row in result.variants if row.variant == "text"}
    search_rows = {
        row.question_number for row in result.variants if row.variant == "search_queries"
    }
    assert text_rows == {"1", "2"}
    assert search_rows == {"1"}
    assert result.omitted_counts == {"text": 0, "search_queries": 1}


def test_dedups_image_description_by_filename_one_embedding_call_per_distinct_image() -> None:
    shared_image_items = [
        _question(number=str(i), image_filename="stop.jpeg", image_description="Segnale di stop.")
        for i in range(3)
    ]
    other_image_item = _question(
        number="99", image_filename="give_way.jpeg", image_description="Dare la precedenza."
    )
    fake_service = _RecordingFakeEmbeddingService()
    use_case = EmbedQuizVariants(["image_description"], fake_service)  # type: ignore[arg-type]

    result = use_case.execute([*shared_image_items, other_image_item])

    assert len(fake_service.calls) == 1
    assert len(fake_service.calls[0]) == 2  # 2 distinct images, not 4 questions
    vectors_by_question = {row.question_number: row.embedding for row in result.variants}
    assert vectors_by_question["0"] == vectors_by_question["1"] == vectors_by_question["2"]
    assert vectors_by_question["99"] != vectors_by_question["0"]


def test_unknown_variant_name_raises_key_error() -> None:
    fake_service = _RecordingFakeEmbeddingService()

    with pytest.raises(KeyError):
        EmbedQuizVariants(["not_a_variant"], fake_service)  # type: ignore[arg-type]
