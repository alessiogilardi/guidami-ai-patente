from collections.abc import Sequence

from psycopg import sql

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
    "vector_search_queries",
)
_QUIZ_QUESTION_CONFLICT_COLUMNS = ("number",)


class QuizQuestionStoreRepository(UpsertStoreRepository[QuizQuestionEntity]):
    """Writes to `quiz_questions` via upsert on `number`, plus whole-table reconciliation.

    Quiz has a single source, so reconciliation is not scoped like
    `ArticleStoreRepository.delete_missing`'s per-source variant.
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_QUIZ_QUESTION_TABLE_COLUMNS,
            conflict_columns=_QUIZ_QUESTION_CONFLICT_COLUMNS,
            client=client,
        )

    def delete_missing(self, present: Sequence[QuizQuestionEntity]) -> None:
        """Deletes rows whose `number` is not among `present`.

        An empty `present` deletes every row — the run legitimately produced nothing, and
        the table must mirror that (quiz has a single source, so this scopes the whole
        table, unlike ArticleStoreRepository.delete_missing's per-source scope).
        """
        query = sql.SQL("DELETE FROM {table} WHERE NOT (number = ANY(%s))").format(
            table=sql.Identifier(self._table_name)
        )
        self._client.execute(query, [[question.number for question in present]])

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
            item.vector_search_queries,
        )
