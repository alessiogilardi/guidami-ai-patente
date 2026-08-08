from psycopg import sql

from commons.clients import PostgresClient
from domain.models.retrieval import QuizEvaluationRow

_MODEL_COLUMN_PATTERN = "embedding\\_%"  # noqa: matches literal "embedding_" prefix (AD-6); ESCAPE '\' below stops the underscore acting as a single-char wildcard


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
        quiz_images_table: str,
        client: PostgresClient,
    ) -> None:
        """Injects the table names and the `PostgresClient`."""
        self._client = client
        self._quiz_question_embeddings_table = quiz_question_embeddings_table
        self._from_clause = sql.SQL(
            "{questions} q JOIN {embeddings} e ON e.quiz_question_id = q.id "
            "LEFT JOIN {images} i ON i.filename = q.image_filename"
        ).format(
            questions=sql.Identifier(quiz_questions_table),
            embeddings=sql.Identifier(quiz_question_embeddings_table),
            images=sql.Identifier(quiz_images_table),
        )

    def fetch_with_vectors(self, variant: str, model_column: str) -> list[QuizEvaluationRow]:
        """Returns every question that has an embedding for `variant`, ordered by number.

        The join is an `INNER JOIN` filtered on `e.variant = %s AND
        e.{model_column} IS NOT NULL`: a question with no vector for the requested
        variant/model is absent from the result, never present with a null embedding.
        `model_column` is caller-selected (FR-3/AD-6, see `populated_model_columns`), not
        hardcoded. Does not select `q.embedding` — that column no longer exists on
        `quiz_questions`. `quiz_images` is joined with a `LEFT JOIN` (not every question
        has an image), so `image_description` is `None` for image-less questions.
        """
        query = sql.SQL(
            "SELECT q.id, q.number, q.topic, q.text, q.correct_answer, "
            "q.exact_keywords, q.image_filename, i.description, e.{model_column} "
            "FROM {from_clause} "
            "WHERE e.variant = %s AND e.{model_column} IS NOT NULL "
            "ORDER BY q.number"
        ).format(from_clause=self._from_clause, model_column=sql.Identifier(model_column))
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
                image_description=row[7],
                embedding=row[8],
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

    def populated_model_columns(self) -> list[str]:
        """Returns the `embedding_*` columns holding >= 1 non-null vector (FR-3, AD-6).

        Two-step, both driven by the schema/data rather than a hardcoded model list: first
        lists every column matching AD-6's `embedding_` naming convention via
        `information_schema.columns`, then checks each for at least one non-null value in
        one aggregate query. Adding a model column (AD-6) needs no change here.
        """
        candidates = self._candidate_model_columns()
        if not candidates:
            return []
        query = sql.SQL("SELECT {aggs} FROM {table}").format(
            aggs=sql.SQL(", ").join(
                sql.SQL("bool_or({col} IS NOT NULL)").format(col=sql.Identifier(col))
                for col in candidates
            ),
            table=sql.Identifier(self._quiz_question_embeddings_table),
        )
        row = self._client.fetch(query)[0]
        return [col for col, populated in zip(candidates, row, strict=True) if populated]

    def _candidate_model_columns(self) -> list[str]:
        query = sql.SQL(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND column_name LIKE %s ESCAPE '\\' "
            "ORDER BY column_name"
        )
        rows = self._client.fetch(
            query, [self._quiz_question_embeddings_table, _MODEL_COLUMN_PATTERN]
        )
        return [row[0] for row in rows]
