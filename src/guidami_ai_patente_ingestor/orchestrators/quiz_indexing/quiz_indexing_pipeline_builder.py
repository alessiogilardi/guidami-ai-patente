from typing import Self

from commons.clients import EmbeddingClient, PostgresClient, SentenceTransformerEmbeddingClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    QuizBankRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services.quiz import QuizQuestionMapper

from .quiz_indexing_pipeline import QuizIndexingPipeline


class QuizIndexingPipelineBuilder:
    """Valida `IngestorConfig` e assembla `QuizIndexingPipeline` con le dipendenze concrete.

    Le dipendenze concrete possono essere sovrascritte tramite i metodi `with_*`
    (fluent), ad es. per iniettare fake/mock nei test senza toccare i moduli interni.
    """

    def __init__(self, config: IngestorConfig) -> None:
        """Memorizza la configurazione da cui costruire la pipeline."""
        self._config = config
        self._quiz_bank_repository: QuizBankRepository | None = None
        self._quiz_question_mapper: QuizQuestionMapper | None = None
        self._quiz_question_store_repository: QuizQuestionStoreRepository | None = None
        self._embedding_client: EmbeddingClient | None = None

    def with_quiz_bank_repository(self, quiz_bank_repository: QuizBankRepository) -> Self:
        """Sostituisce il `QuizBankRepository` di default."""
        self._quiz_bank_repository = quiz_bank_repository
        return self

    def with_quiz_question_mapper(self, quiz_question_mapper: QuizQuestionMapper) -> Self:
        """Sostituisce il `QuizQuestionMapper` di default."""
        self._quiz_question_mapper = quiz_question_mapper
        return self

    def with_quiz_question_store_repository(
        self, quiz_question_store_repository: QuizQuestionStoreRepository
    ) -> Self:
        """Sostituisce il `QuizQuestionStoreRepository` di default."""
        self._quiz_question_store_repository = quiz_question_store_repository
        return self

    def with_embedding_client(self, embedding_client: EmbeddingClient) -> Self:
        """Sostituisce l'`EmbeddingClient` di default (`SentenceTransformerEmbeddingClient`)."""
        self._embedding_client = embedding_client
        return self

    def build(self) -> QuizIndexingPipeline:
        """Verifica il path sorgente e assembla la pipeline."""
        self._validate_source_path()
        return QuizIndexingPipeline(
            quiz_bank_repository=(
                self._quiz_bank_repository
                if self._quiz_bank_repository is not None
                else QuizBankRepository()
            ),
            quiz_question_mapper=(
                self._quiz_question_mapper
                if self._quiz_question_mapper is not None
                else QuizQuestionMapper()
            ),
            quiz_question_store_repository=(
                self._quiz_question_store_repository
                if self._quiz_question_store_repository is not None
                else QuizQuestionStoreRepository(
                    PostgresClient(self._config.postgres), self._config.quiz_questions_table
                )
            ),
            embedding_client=(
                self._embedding_client
                if self._embedding_client is not None
                else SentenceTransformerEmbeddingClient(self._config.embedding)
            ),
            config=self._config,
        )

    def _validate_source_path(self) -> None:
        if not self._config.quiz_bank_path.exists():
            raise FileNotFoundError(f"File sorgente non trovato: {self._config.quiz_bank_path}")
