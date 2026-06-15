import logging

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
        config: IngestorConfig,
    ) -> None:
        """Inietta le dipendenze della pipeline e la configurazione."""
        self._quiz_bank_repository = quiz_bank_repository
        self._quiz_question_mapper = quiz_question_mapper
        self._quiz_question_store_repository = quiz_question_store_repository
        self._config = config

    def run(self) -> None:
        """Esegue il full reload di `quiz_questions` dal quiz bank."""
        main_questions = self._quiz_bank_repository.load(self._config.quiz_bank_path)
        logger.info(f"loaded {len(main_questions)} main questions")

        questions = self._quiz_question_mapper.map(main_questions)
        logger.info(f"mapped {len(questions)} quiz questions")

        logger.info(f"truncating quiz_questions, inserting {len(questions)} questions")
        self._quiz_question_store_repository.truncate()
        self._quiz_question_store_repository.bulk_insert(questions)
        logger.info("insertion completed")
