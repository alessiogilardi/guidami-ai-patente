"""Test per ToEmbeddableQuiz (UseCase che converte il quiz bank enriched in embeddable)."""

from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel, EnrichedQuizModel


def _enriched(
    number: str,
    text: str = "Domanda.",
    correct_answer: bool = True,
    image: str | None = None,
    image_description: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=100,
        topic="Segnaletica",
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
        image_description=image_description,
    )


def test_empty_input_returns_empty_list() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    use_case = ToEmbeddableQuiz()
    result = use_case([])
    assert result == []


def test_no_duplicates_all_mapped_to_embeddable_quiz_model() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    items = [
        _enriched("1", "Prima domanda."),
        _enriched("2", "Seconda domanda."),
    ]
    use_case = ToEmbeddableQuiz()
    result = use_case(items)

    assert len(result) == 2
    assert all(isinstance(item, EmbeddableQuizModel) for item in result)


def test_duplicates_by_stripped_text_answer_image_are_deduplicated() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    items = [
        _enriched("1", "  Domanda  ", correct_answer=True, image="img.jpeg"),
        _enriched("2", "Domanda", correct_answer=True, image="img.jpeg"),
        _enriched("3", "Altra domanda.", correct_answer=False),
    ]
    use_case = ToEmbeddableQuiz()
    result = use_case(items)

    assert len(result) == 2
    numbers = [item.number for item in result]
    assert "1" in numbers
    assert "3" in numbers
    assert "2" not in numbers


def test_field_mapping_number_question_id_topic_text_answer_image_filename_description() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    item = _enriched(
        "42",
        text="  Domanda con spazi.  ",
        correct_answer=False,
        image="images/stop.jpeg",
        image_description="Segnale di stop.",
    )
    use_case = ToEmbeddableQuiz()
    result = use_case([item])
    mapped = result[0]

    assert mapped.number == "42"
    assert mapped.question_id == 100
    assert mapped.topic == "Segnaletica"
    assert mapped.text == "Domanda con spazi."
    assert mapped.correct_answer is False
    assert mapped.image_filename == "stop.jpeg"
    assert mapped.image_description == "Segnale di stop."


def test_same_text_different_image_both_kept() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    items = [
        _enriched("1", "Domanda", correct_answer=True, image="img-a.jpeg"),
        _enriched("2", "Domanda", correct_answer=True, image="img-b.jpeg"),
    ]
    use_case = ToEmbeddableQuiz()
    result = use_case(items)

    assert len(result) == 2


def test_same_text_different_correct_answer_both_kept() -> None:
    from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

    items = [
        _enriched("1", "Domanda", correct_answer=True),
        _enriched("2", "Domanda", correct_answer=False),
    ]
    use_case = ToEmbeddableQuiz()
    result = use_case(items)

    assert len(result) == 2
