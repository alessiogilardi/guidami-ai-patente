"""Tests for RoadSignDescriberMapper (many-quizzes-per-image request, dual-field response)."""

from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import RoadSignDescriberResponse
from guidami_ai_patente_ingestor.mappers.agents import RoadSignDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, ImageAnalysis


def _question(
    number: str,
    topic: str = "Segnaletica",
    text: str = "Domanda.",
    image: str | None = "stop.jpeg",
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=1,
        topic=topic,
        number=number,
        text=text,
        correct_answer=True,
        image=image,
    )


def test_from_enriched_quizzes_to_request_collapses_duplicate_topic_text() -> None:
    q1 = _question("1", topic="Segnaletica", text="Domanda.")
    q2_same_topic_text = _question("2", topic="Segnaletica", text="Domanda.")
    q3 = _question("3", topic="Precedenza", text="Altra domanda.")

    request = RoadSignDescriberMapper.from_enriched_quizzes_to_request(
        [q1, q2_same_topic_text, q3]
    )

    assert request.contexts == [
        "Argomento: Segnaletica — Testo: Domanda.",
        "Argomento: Precedenza — Testo: Altra domanda.",
    ]


def test_from_enriched_quizzes_to_request_preserves_first_seen_order() -> None:
    q1 = _question("1", topic="B", text="Seconda.")
    q2 = _question("2", topic="A", text="Prima.")

    request = RoadSignDescriberMapper.from_enriched_quizzes_to_request([q1, q2])

    assert request.contexts == [
        "Argomento: B — Testo: Seconda.",
        "Argomento: A — Testo: Prima.",
    ]


def test_from_response_to_enriched_quiz_sets_flat_description_and_analysis() -> None:
    question = _question("1")
    response = RoadSignDescriberResponse(
        visual_analysis="Segnale ottagonale rosso con scritta STOP.",
        name="Stop",
        description="Segnale di arresto obbligatorio.",
    )

    result = RoadSignDescriberMapper.from_response_to_enriched_quiz(question, response)

    assert result.image_description == "Stop. Segnale di arresto obbligatorio."
    assert result.image_analysis == ImageAnalysis(
        visual_analysis="Segnale ottagonale rosso con scritta STOP.",
        name="Stop",
        description="Segnale di arresto obbligatorio.",
    )


def test_from_response_to_enriched_quiz_leaves_other_fields_untouched() -> None:
    question = _question("1", topic="Segnaletica", text="Domanda originale.")
    response = RoadSignDescriberResponse(
        visual_analysis="Analisi.", name="Stop", description="Descrizione."
    )

    result = RoadSignDescriberMapper.from_response_to_enriched_quiz(question, response)

    assert result.topic == question.topic
    assert result.text == question.text
    assert result.number == question.number
    assert result.image == question.image
