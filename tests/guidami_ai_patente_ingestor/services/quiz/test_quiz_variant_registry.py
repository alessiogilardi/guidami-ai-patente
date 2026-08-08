"""Tests for QUIZ_VARIANT_REGISTRY (AD-7/AD-8): one text builder + dedup key per variant."""

from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel, QuizMetadata
from guidami_ai_patente_ingestor.services.quiz.quiz_variant_registry import QUIZ_VARIANT_REGISTRY


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


def test_registry_has_exactly_six_entries() -> None:
    assert len(QUIZ_VARIANT_REGISTRY) == 6
    assert set(QUIZ_VARIANT_REGISTRY) == {
        "text",
        "topic_text",
        "search_queries",
        "combined",
        "combined_description",
        "image_description",
    }


def test_topic_text_omits_missing_image_description() -> None:
    imageless = _question(topic="Segnaletica", text="Testo domanda", image_description=None)
    imaged = _question(
        topic="Segnaletica", text="Testo domanda", image_description="Segnale di stop."
    )

    composer = QUIZ_VARIANT_REGISTRY["topic_text"].text_composer

    assert composer.compose_or_none(imageless) == "Segnaletica\nTesto domanda"
    assert composer.compose_or_none(imaged) == "Segnaletica\nTesto domanda\nSegnale di stop."


def test_search_queries_returns_none_without_metadata() -> None:
    item = _question(quiz_metadata=None)

    assert QUIZ_VARIANT_REGISTRY["search_queries"].text_composer.compose_or_none(item) is None


def test_search_queries_joins_vector_search_queries() -> None:
    item = _question(quiz_metadata=_metadata(vector_search_queries=["query uno", "query due"]))

    assert (
        QUIZ_VARIANT_REGISTRY["search_queries"].text_composer.compose_or_none(item)
        == "query uno\nquery due"
    )


def test_combined_joins_topic_text_and_search_queries() -> None:
    item = _question(
        topic="Segnaletica",
        text="Testo domanda",
        quiz_metadata=_metadata(vector_search_queries=["query uno", "query due"]),
    )

    result = QUIZ_VARIANT_REGISTRY["combined"].text_composer.compose_or_none(item)

    assert result == "Segnaletica\nTesto domanda\nquery uno\nquery due"


def test_combined_returns_none_without_metadata() -> None:
    item = _question(quiz_metadata=None)

    assert QUIZ_VARIANT_REGISTRY["combined"].text_composer.compose_or_none(item) is None


def test_combined_description_appends_image_description_when_present() -> None:
    item = _question(
        topic="Segnaletica",
        text="Testo domanda",
        image_description="Segnale di stop.",
        quiz_metadata=_metadata(vector_search_queries=["query uno"]),
    )

    result = QUIZ_VARIANT_REGISTRY["combined_description"].text_composer.compose_or_none(item)

    assert result == "Segnaletica\nTesto domanda\nSegnale di stop.\nquery uno"


def test_combined_description_equals_combined_when_no_image() -> None:
    item = _question(
        topic="Segnaletica",
        text="Testo domanda",
        image_description=None,
        quiz_metadata=_metadata(vector_search_queries=["query uno"]),
    )

    combined = QUIZ_VARIANT_REGISTRY["combined"].text_composer.compose_or_none(item)
    combined_description = QUIZ_VARIANT_REGISTRY[
        "combined_description"
    ].text_composer.compose_or_none(item)

    assert combined_description == combined


def test_image_description_dedup_key_is_image_filename() -> None:
    item = _question(image_filename="stop.jpeg", image_description="Segnale di stop.")

    spec = QUIZ_VARIANT_REGISTRY["image_description"]

    assert spec.text_composer.compose_or_none(item) == "Segnale di stop."
    assert spec.dedup_key(item) == "stop.jpeg"


def test_image_description_returns_none_without_image() -> None:
    item = _question(image_filename=None, image_description=None)

    assert QUIZ_VARIANT_REGISTRY["image_description"].text_composer.compose_or_none(item) is None


def test_text_variant_dedup_key_defaults_to_question_number() -> None:
    item = _question(number="42")

    assert QUIZ_VARIANT_REGISTRY["text"].dedup_key(item) == "42"
