from psycopg import sql

from commons.clients import PostgresClient
from domain.models.retrieval import QuizEvaluationRow


class QuizReadRepository:
    """Read-only repository over `quiz_questions` joined to `quiz_question_embeddings`.

    Scoped per aggregate (AD-7): a question is only usable together with its query
    vector, so `fetch_with_vectors` returns the two joined rather than a question list
    plus a separate id-to-vector map for the caller to stitch together.
    """

    def __init__(
        self,
        quiz_questions_table: str,
        quiz_question_embeddings_table: str,
        client: PostgresClient,
    ) -> None:
        """Injects the table names and the `PostgresClient`."""
        self._client = client
        self._quiz_question_embeddings_table = quiz_question_embeddings_table
        self._from_clause = sql.SQL(
            "{questions} q JOIN {embeddings} e ON e.quiz_question_id = q.id"
        ).format(
            questions=sql.Identifier(quiz_questions_table),
            embeddings=sql.Identifier(quiz_question_embeddings_table),
        )

    def fetch_with_vectors(self, variant: str) -> list[QuizEvaluationRow]:
        """Returns every question that has an embedding for `variant`, ordered by number.

        The join is an `INNER JOIN` filtered on `e.variant = %s AND
        e.embedding_3_small IS NOT NULL`: a question with no vector for the requested
        variant is absent from the result, never present with a null embedding. Does
        not select `q.embedding` — that column no longer exists on `quiz_questions`.
        """
        query = sql.SQL(
            "SELECT q.id, q.number, q.topic, q.text, q.correct_answer, "
            "q.exact_keywords, q.image_filename, e.embedding_3_small "
            "FROM {from_clause} "
            "WHERE e.variant = %s AND e.embedding_3_small IS NOT NULL "
            "ORDER BY q.number"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [variant])
        return [
            QuizEvaluationRow(
                id=row[0],
                number=row[1],
                topic=row[2],
                text=row[3],
                correct_answer=row[4],
                exact_keywords=row[5],
                image_filename=row[6],
                embedding=row[7],
            )
            for row in rows
        ]

    def available_variants(self) -> list[str]:
        """Returns the distinct `variant` values actually present, ordered alphabetically.

        Used to build an operator-facing error message (T-10) when the configured
        variant has no rows.
        """
        query = sql.SQL("SELECT DISTINCT variant FROM {table} ORDER BY variant").format(
            table=sql.Identifier(self._quiz_question_embeddings_table)
        )
        rows = self._client.fetch(query)
        return [row[0] for row in rows]
