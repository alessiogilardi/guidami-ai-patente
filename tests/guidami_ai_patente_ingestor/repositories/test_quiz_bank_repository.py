from pathlib import Path

from guidami_ai_patente_ingestor.repositories import QuizBankRepository

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_load_maps_json_to_main_questions() -> None:
    repository = QuizBankRepository()

    main_questions = repository.load(FIXTURES_DIR / "quiz_bank_sample.json")

    assert len(main_questions) == 2

    first = main_questions[0]
    assert first.question_id == 100
    assert first.topic == "Segnaletica"
    assert [sub.number for sub in first.sub_questions] == ["1001", "1002", "1003"]
    assert first.sub_questions[0].image == "data/processed/quiz-patente-ab/images/abc123.jpeg"
    assert first.sub_questions[2].image is None
    assert first.sub_questions[1].correct_answer is False
