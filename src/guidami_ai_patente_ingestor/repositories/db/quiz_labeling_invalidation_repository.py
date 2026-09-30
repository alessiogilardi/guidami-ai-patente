from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient


class QuizLabelingInvalidationRepository:
    """Reads stored image descriptions and deletes labelings that depend on them.

    Owned by the ingestor on purpose (spec 0023, AD-4): the ingestor needs only these
    three statements over `quiz_images`/`quiz_questions`/`quiz_labelings`, so it does not
    depend on the labeling package's repositories or its epoch machinery. Deleting a
    labeling cascades to its `quiz_comma_labels` rows through the schema's foreign key.
    """

    def __init__(
        self,
        quiz_images_table: str,
        quiz_questions_table: str,
        quiz_labelings_table: str,
        client: PostgresClient,
    ) -> None:
        """Injects the three table names and the `PostgresClient`."""
        self._images = sql.Identifier(quiz_images_table)
        self._questions = sql.Identifier(quiz_questions_table)
        self._labelings = sql.Identifier(quiz_labelings_table)
        self._client = client

    def find_descriptions(self, filenames: Sequence[str]) -> dict[str, str | None]:
        """Returns the stored description of each of `filenames` that has a row."""
        if not filenames:
            return {}
        query = sql.SQL("SELECT filename, description FROM {images} WHERE filename = ANY(%s)")
        rows = self._client.fetch(query.format(images=self._images), [list(filenames)])
        return {filename: description for filename, description in rows}

    def count_validated_labelings(self, filenames: Sequence[str]) -> int:
        """Counts the human-validated labelings of questions that use any of `filenames`."""
        if not filenames:
            return 0
        query = sql.SQL(
            "SELECT ql.id FROM {labelings} AS ql "
            "JOIN {questions} AS q ON q.id = ql.quiz_question_id "
            "WHERE q.image_filename = ANY(%s) AND ql.validated_at IS NOT NULL"
        ).format(labelings=self._labelings, questions=self._questions)
        return len(self._client.fetch(query, [list(filenames)]))

    def delete_unvalidated_labelings(self, filenames: Sequence[str]) -> int:
        """Deletes the non-validated labelings (any run origin) of questions using `filenames`.

        Returns:
            The number of labelings deleted.
        """
        if not filenames:
            return 0
        query = sql.SQL(
            "DELETE FROM {labelings} AS ql USING {questions} AS q "
            "WHERE ql.quiz_question_id = q.id "
            "AND q.image_filename = ANY(%s) AND ql.validated_at IS NULL "
            "RETURNING ql.id"
        ).format(labelings=self._labelings, questions=self._questions)
        return len(self._client.fetch(query, [list(filenames)]))
