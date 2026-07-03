from psycopg.types.json import Jsonb

from commons.clients import PostgresClient
from domain.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.repositories.db._bulk_insert_store_repository import (
    BulkInsertStoreRepository,
)

_QUIZ_QUESTION_TABLE_COLUMNS = (
    "number",
    "question_id",
    "topic",
    "text",
    "correct_answer",
    "image_filename",
    "quiz_metadata",
    "embedding",
)


class QuizQuestionStoreRepository(BulkInsertStoreRepository[QuizQuestion]):
    """Scrittura full-reload su `quiz_questions` (truncate + bulk insert)."""

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        super().__init__(
            client=client,
            table_name=table_name,
            columns=_QUIZ_QUESTION_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
        )

    @staticmethod
    def _to_db_row(item: QuizQuestion) -> tuple[object, ...]:
        return (
            item.number,
            item.question_id,
            item.topic,
            item.text,
            item.correct_answer,
            item.image_filename,
            Jsonb(item.quiz_metadata.model_dump()) if item.quiz_metadata is not None else None,
            item.embedding,
        )
