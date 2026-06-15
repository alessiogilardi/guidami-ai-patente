from pathlib import Path
from unittest.mock import Mock, call

from commons.configs import PostgresConnectionConfig
from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.entities import QuizMainQuestion, QuizSubQuestion
from guidami_ai_patente_ingestor.orchestrators.quiz_indexing import QuizIndexingPipeline
from guidami_ai_patente_ingestor.repositories import (
    QuizBankRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services.quiz import QuizQuestionMapper


def _build_config(quiz_bank_path: Path) -> IngestorConfig:
    return IngestorConfig(
        quiz_bank_path=quiz_bank_path,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def test_run_loads_maps_and_reloads_quiz_questions(tmp_path: Path) -> None:
    config = _build_config(tmp_path / "quiz-bank.json")

    main_questions = [
        QuizMainQuestion(
            question_id=100,
            topic="Segnaletica",
            sub_questions=[QuizSubQuestion(number="1", text="Domanda", correct_answer=True)],
        )
    ]
    mapped_questions = [
        QuizQuestion(
            number="1", question_id=100, topic="Segnaletica", text="Domanda", correct_answer=True
        )
    ]

    quiz_bank_repository = Mock(spec=QuizBankRepository)
    quiz_bank_repository.load.return_value = main_questions

    quiz_question_mapper = Mock(spec=QuizQuestionMapper)
    quiz_question_mapper.map.return_value = mapped_questions

    quiz_question_store_repository = Mock(spec=QuizQuestionStoreRepository)

    pipeline = QuizIndexingPipeline(
        quiz_bank_repository=quiz_bank_repository,
        quiz_question_mapper=quiz_question_mapper,
        quiz_question_store_repository=quiz_question_store_repository,
        config=config,
    )

    pipeline.run()

    quiz_bank_repository.load.assert_called_once_with(config.quiz_bank_path)
    quiz_question_mapper.map.assert_called_once_with(main_questions)
    assert quiz_question_store_repository.method_calls[0] == call.truncate()
    assert quiz_question_store_repository.method_calls[1] == call.bulk_insert(mapped_questions)
