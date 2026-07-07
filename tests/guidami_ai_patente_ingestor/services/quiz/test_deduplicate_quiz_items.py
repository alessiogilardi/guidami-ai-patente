"""Test per DeduplicateQuizItems (UseCase generico che deduplica quiz item flat).

Chiave di unicità: (testo normalizzato, risposta corretta, identità immagine),
condivisa da `build_quiz_cleaning_flow` (CleanedQuizModel) e
`build_quiz_indexing_flow` (EnrichedQuizModel).
"""

from guidami_ai_patente_ingestor.models.quiz import CleanedQuizModel, EnrichedQuizModel
from guidami_ai_patente_ingestor.services.quiz import DeduplicateQuizItems


def _cleaned(
    number: str,
    text: str = "Domanda.",
    correct_answer: bool = True,
    image: str | None = None,
) -> CleanedQuizModel:
    return CleanedQuizModel(
        question_id=100,
        topic="Segnaletica",
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
    )


def _enriched(
    number: str,
    text: str = "Domanda.",
    correct_answer: bool = True,
    image: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=100,
        topic="Segnaletica",
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
        image_description=None,
    )


def test_empty_input_returns_empty_list() -> None:
    dedup = DeduplicateQuizItems()
    assert dedup.execute([]) == []


def test_no_duplicates_all_preserved() -> None:
    items = [_cleaned("1", "Prima domanda."), _cleaned("2", "Seconda domanda.")]
    dedup = DeduplicateQuizItems()

    assert dedup.execute(items) == items


def test_duplicates_by_stripped_text_answer_image_are_removed() -> None:
    items = [
        _cleaned("1", "  Domanda  ", correct_answer=True, image="img.jpeg"),
        _cleaned("2", "Domanda", correct_answer=True, image="img.jpeg"),
        _cleaned("3", "Altra domanda.", correct_answer=False),
    ]
    dedup = DeduplicateQuizItems()

    result = dedup.execute(items)

    numbers = [item.number for item in result]
    assert numbers == ["1", "3"]


def test_same_text_different_image_both_kept() -> None:
    items = [
        _cleaned("1", "Domanda", correct_answer=True, image="img-a.jpeg"),
        _cleaned("2", "Domanda", correct_answer=True, image="img-b.jpeg"),
    ]
    dedup = DeduplicateQuizItems()

    assert len(dedup.execute(items)) == 2


def test_same_text_different_correct_answer_both_kept() -> None:
    items = [
        _cleaned("1", "Domanda", correct_answer=True),
        _cleaned("2", "Domanda", correct_answer=False),
    ]
    dedup = DeduplicateQuizItems()

    assert len(dedup.execute(items)) == 2


def test_works_on_cleaned_quiz_model() -> None:
    """Il componente deduplica CleanedQuizModel senza subclassing model-specific."""
    items = [
        _cleaned("1", "Domanda", correct_answer=True, image="img.jpeg"),
        _cleaned("2", "Domanda", correct_answer=True, image="img.jpeg"),
    ]
    dedup = DeduplicateQuizItems()

    result = dedup.execute(items)

    assert len(result) == 1
    assert all(isinstance(item, CleanedQuizModel) for item in result)


def test_works_on_enriched_quiz_model() -> None:
    """Lo stesso componente, senza modifiche, deduplica anche EnrichedQuizModel."""
    items = [
        _enriched("1", "Domanda", correct_answer=True, image="img.jpeg"),
        _enriched("2", "Domanda", correct_answer=True, image="img.jpeg"),
    ]
    dedup = DeduplicateQuizItems()

    result = dedup.execute(items)

    assert len(result) == 1
    assert all(isinstance(item, EnrichedQuizModel) for item in result)


def test_logs_warning_with_item_number_on_duplicate(caplog) -> None:
    """Il messaggio di log unificato riporta solo item.number (no question_id)."""
    items = [_cleaned("1", "Domanda"), _cleaned("2", "Domanda")]
    dedup = DeduplicateQuizItems()

    with caplog.at_level("WARNING"):
        dedup.execute(items)

    assert any(
        record.levelname == "WARNING" and "2" in record.getMessage() for record in caplog.records
    ), "expected a WARNING log entry naming the duplicate item's number"
