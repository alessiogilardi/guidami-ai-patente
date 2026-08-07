from commons.clients import PostgresClient
from domain.entities.quiz import QuizQuestionEntity

from ._upsert_store_repository import UpsertStoreRepository

_QUIZ_QUESTION_TABLE_COLUMNS = (
    "number",
    "question_id",
    "topic",
    "text",
    "correct_answer",
    "image_filename",
    "core_concepts",
    "exact_keywords",
    "rule_explanation",
    "embedding",
)
_QUIZ_QUESTION_CONFLICT_COLUMNS = ("number",)


class QuizQuestionStoreRepository(UpsertStoreRepository[QuizQuestionEntity]):
    """Full-reload write to `quiz_questions` (truncate + bulk insert)."""

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_QUIZ_QUESTION_TABLE_COLUMNS,
            conflict_columns=_QUIZ_QUESTION_CONFLICT_COLUMNS,
            client=client,
        )

    @staticmethod
    def _to_db_row(item: QuizQuestionEntity) -> tuple[object, ...]:
        return (
            item.number,
            item.question_id,
            item.topic,
            item.text,
            item.correct_answer,
            item.image_filename,
            item.core_concepts,
            item.exact_keywords,
            item.rule_explanation,
            item.embedding,
        )
