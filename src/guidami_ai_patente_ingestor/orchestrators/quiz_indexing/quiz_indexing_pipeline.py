import logging

from commons.clients import EmbeddingClient
from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    QuizBankRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services.quiz import QuizQuestionMapper

logger = logging.getLogger(__name__)


class QuizIndexingPipeline:
    """Pipeline batch: legge il quiz bank, lo appiattisce in righe e ricostruisce la tabella."""

    def __init__(
        self,
        quiz_bank_repository: QuizBankRepository,
        quiz_question_mapper: QuizQuestionMapper,
        quiz_question_store_repository: QuizQuestionStoreRepository,
        embedding_client: EmbeddingClient,
        config: IngestorConfig,
    ) -> None:
        """Inietta le dipendenze della pipeline e la configurazione."""
        self._quiz_bank_repository = quiz_bank_repository
        self._quiz_question_mapper = quiz_question_mapper
        self._quiz_question_store_repository = quiz_question_store_repository
        self._embedding_client = embedding_client
        self._config = config

    def run(self) -> None:
        """Esegue il full reload di `quiz_questions` dal quiz bank."""
        main_questions = self._quiz_bank_repository.load(self._config.quiz_bank_path)
        logger.info(f"loaded {len(main_questions)} main questions")

        questions = self._quiz_question_mapper.map(main_questions)
        logger.info(f"mapped {len(questions)} quiz questions")

        self._assign_embeddings(questions)

        logger.info(f"truncating quiz_questions, inserting {len(questions)} questions")
        self._quiz_question_store_repository.truncate()
        self._quiz_question_store_repository.bulk_insert(questions)
        logger.info("insertion completed")

    def _assign_embeddings(self, questions: list[QuizQuestion]) -> None:
        batch_size = self._config.embedding_batch_size
        total_batches = -(-len(questions) // batch_size)  # ceil division
        for start in range(0, len(questions), batch_size):
            batch = questions[start : start + batch_size]
            batch_number = start // batch_size + 1
            logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} questions)")
            vectors = self._embedding_client.embed_passages([q.text for q in batch])
            for question, vector in zip(batch, vectors, strict=True):
                question.embedding = vector
