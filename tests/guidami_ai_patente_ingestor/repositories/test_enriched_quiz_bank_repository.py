from pathlib import Path

from guidami_ai_patente_ingestor.models.quiz import (
    EnrichedQuizItemModel,
    EnrichedQuizModel,
)
from guidami_ai_patente_ingestor.repositories import EnrichedQuizBankRepository


def _main_question(
    question_id: int = 1,
    image_description: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=question_id,
        topic="Segnaletica",
        sub_questions=[
            EnrichedQuizItemModel(
                number="1",
                text="Domanda di esempio.",
                correct_answer=True,
                image="img.jpeg",
                image_description=image_description,
            )
        ],
    )


def test_write_then_load_round_trips_questions(tmp_path: Path) -> None:
    path = tmp_path / "enriched" / "quiz.json"
    questions = [_main_question(question_id=100, image_description="Segnale di stop.")]

    repo = EnrichedQuizBankRepository()
    repo.write(questions, path)
    loaded = repo.load(path)

    assert len(loaded) == 1
    assert loaded[0].question_id == 100
    assert loaded[0].sub_questions[0].image_description == "Segnale di stop."


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "quiz.json"
    repo = EnrichedQuizBankRepository()
    repo.write([_main_question()], path)
    assert path.exists()


def test_load_returns_empty_list_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    repo = EnrichedQuizBankRepository()
    assert repo.load(path) == []


def test_write_preserves_none_image_description(tmp_path: Path) -> None:
    path = tmp_path / "quiz.json"
    questions = [_main_question(image_description=None)]
    repo = EnrichedQuizBankRepository()
    repo.write(questions, path)
    loaded = repo.load(path)
    assert loaded[0].sub_questions[0].image_description is None
