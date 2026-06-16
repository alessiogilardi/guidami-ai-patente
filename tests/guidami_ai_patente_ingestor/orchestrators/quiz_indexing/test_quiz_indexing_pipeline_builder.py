from pathlib import Path
from unittest.mock import Mock

import pytest

from commons.clients import EmbeddingClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.quiz_indexing import (
    QuizIndexingPipeline,
    QuizIndexingPipelineBuilder,
)
from guidami_ai_patente_ingestor.repositories import (
    QuizBankRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services.quiz import QuizQuestionMapper

MODULE = "guidami_ai_patente_ingestor.orchestrators.quiz_indexing.quiz_indexing_pipeline_builder"


def _build_config(quiz_bank_path: Path) -> IngestorConfig:
    return IngestorConfig(
        quiz_bank_path=quiz_bank_path,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def test_build_raises_before_instantiating_client_when_source_path_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.PostgresClient",
        lambda config: pytest.fail("non deve essere istanziato se il path sorgente è invalido"),
    )

    quiz_bank_path = tmp_path / "missing-quiz-bank.json"
    config = _build_config(quiz_bank_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        QuizIndexingPipelineBuilder(config).build()

    assert str(quiz_bank_path) in str(exc_info.value)


def test_build_uses_overridden_dependencies_instead_of_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.PostgresClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )
    monkeypatch.setattr(
        f"{MODULE}.LiteLLMEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )

    quiz_bank_path = tmp_path / "quiz-bank.json"
    quiz_bank_path.write_text("[]", encoding="utf-8")

    quiz_bank_repository = Mock(spec=QuizBankRepository)
    quiz_question_mapper = Mock(spec=QuizQuestionMapper)
    quiz_question_store_repository = Mock(spec=QuizQuestionStoreRepository)
    embedding_client = Mock(spec=EmbeddingClient)

    pipeline = (
        QuizIndexingPipelineBuilder(_build_config(quiz_bank_path))
        .with_quiz_bank_repository(quiz_bank_repository)
        .with_quiz_question_mapper(quiz_question_mapper)
        .with_quiz_question_store_repository(quiz_question_store_repository)
        .with_embedding_client(embedding_client)
        .build()
    )

    assert isinstance(pipeline, QuizIndexingPipeline)
    assert pipeline._quiz_bank_repository is quiz_bank_repository
    assert pipeline._quiz_question_mapper is quiz_question_mapper
    assert pipeline._quiz_question_store_repository is quiz_question_store_repository
    assert pipeline._embedding_client is embedding_client
