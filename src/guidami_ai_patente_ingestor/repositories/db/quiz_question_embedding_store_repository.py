from commons.clients import PostgresClient
from domain.entities.quiz import QuizQuestionEmbeddingEntity

from ._upsert_store_repository import UpsertStoreRepository

_QUIZ_QUESTION_EMBEDDING_TABLE_COLUMNS = ("quiz_question_id", "variant", "embedding_3_small")
_QUIZ_QUESTION_EMBEDDING_CONFLICT_COLUMNS = ("quiz_question_id", "variant")


class QuizQuestionEmbeddingStoreRepository(UpsertStoreRepository[QuizQuestionEmbeddingEntity]):
    """Writes to `quiz_question_embeddings` via upsert on `(quiz_question_id, variant)`.

    No `delete_missing` (PD-6) — deferred with spec 0008's own Open Question on whether
    losing variants are reconciled away.
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_QUIZ_QUESTION_EMBEDDING_TABLE_COLUMNS,
            conflict_columns=_QUIZ_QUESTION_EMBEDDING_CONFLICT_COLUMNS,
            client=client,
        )

    @staticmethod
    def _to_db_row(item: QuizQuestionEmbeddingEntity) -> tuple[object, ...]:
        return (item.quiz_question_id, item.variant, item.embedding_3_small)
