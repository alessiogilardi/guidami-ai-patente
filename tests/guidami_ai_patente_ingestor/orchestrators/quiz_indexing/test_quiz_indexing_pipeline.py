from pathlib import Path
from unittest.mock import Mock, call

from commons.clients import EmbeddingClient
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


def _make_pipeline(
    config: IngestorConfig,
    quiz_bank_repository: QuizBankRepository,
    quiz_question_mapper: QuizQuestionMapper,
    quiz_question_store_repository: QuizQuestionStoreRepository,
    embedding_client: EmbeddingClient,
) -> QuizIndexingPipeline:
    return QuizIndexingPipeline(
        quiz_bank_repository=quiz_bank_repository,
        quiz_question_mapper=quiz_question_mapper,
        quiz_question_store_repository=quiz_question_store_repository,
        embedding_client=embedding_client,
        config=config,
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

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.return_value = [[0.1, 0.2, 0.3]]

    pipeline = _make_pipeline(
        config,
        quiz_bank_repository,
        quiz_question_mapper,
        quiz_question_store_repository,
        embedding_client,
    )

    pipeline.run()

    quiz_bank_repository.load.assert_called_once_with(config.quiz_bank_path)
    quiz_question_mapper.map.assert_called_once_with(main_questions)
    embedding_client.embed_passages.assert_called_once_with(["Domanda"])
    assert quiz_question_store_repository.method_calls[0] == call.truncate()
    assert quiz_question_store_repository.method_calls[1] == call.bulk_insert(mapped_questions)


def test_run_assigns_embeddings_to_questions(tmp_path: Path) -> None:
    config = _build_config(tmp_path / "quiz-bank.json")

    mapped_questions = [
        QuizQuestion(number="1", question_id=1, topic="T", text="Prima domanda", correct_answer=True),
        QuizQuestion(number="2", question_id=1, topic="T", text="Seconda domanda", correct_answer=False),
    ]
    expected_vectors = [[0.1] * 4, [0.2] * 4]

    quiz_bank_repository = Mock(spec=QuizBankRepository)
    quiz_bank_repository.load.return_value = []

    quiz_question_mapper = Mock(spec=QuizQuestionMapper)
    quiz_question_mapper.map.return_value = mapped_questions

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.return_value = expected_vectors

    quiz_question_store_repository = Mock(spec=QuizQuestionStoreRepository)

    pipeline = _make_pipeline(
        config,
        quiz_bank_repository,
        quiz_question_mapper,
        quiz_question_store_repository,
        embedding_client,
    )

    pipeline.run()

    assert mapped_questions[0].embedding == expected_vectors[0]
    assert mapped_questions[1].embedding == expected_vectors[1]
    embedding_client.embed_passages.assert_called_once_with(["Prima domanda", "Seconda domanda"])
