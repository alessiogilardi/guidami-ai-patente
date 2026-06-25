from commons.clients import PostgresClient
from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.repositories.db._bulk_insert_store_repository import (
    BulkInsertStoreRepository,
)


class QuizQuestionStoreRepository(BulkInsertStoreRepository[QuizQuestion]):
    """Scrittura full-reload su `quiz_questions` (truncate + bulk insert)."""

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        super().__init__(
            client=client,
            table_name=table_name,
            columns=(
                "number",
                "question_id",
                "topic",
                "text",
                "correct_answer",
                "image_filename",
                "embedding",
            ),
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
            item.embedding,
        )
