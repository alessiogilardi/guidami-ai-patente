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
    "core_concepts",
    "named_entities",
    "exact_keywords",
    "rule_explanation",
    "embedding",
)


class QuizQuestionStoreRepository(BulkInsertStoreRepository[QuizQuestion]):
    """Full-reload write to `quiz_questions` (truncate + bulk insert)."""

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_QUIZ_QUESTION_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
            client=client,
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
            item.core_concepts,
            item.named_entities,
            item.exact_keywords,
            item.rule_explanation,
            item.embedding,
        )
