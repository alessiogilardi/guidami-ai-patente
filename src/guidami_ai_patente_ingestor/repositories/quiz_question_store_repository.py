from psycopg import sql

from commons.clients import PostgresClient
from commons.entities.quiz import QuizQuestion


class QuizQuestionStoreRepository:
    """Scrittura full-reload su `quiz_questions` (truncate + bulk insert)."""

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        self._client = client
        self._table_name = table_name

    def truncate(self) -> None:
        """Svuota la tabella in vista di un full reload."""
        self._client.truncate(self._table_name)

    def bulk_insert(self, questions: list[QuizQuestion]) -> None:
        """Inserisce in batch le domande del quiz bank."""
        if not questions:
            return

        query = sql.SQL(
            "INSERT INTO {table} "
            "(number, question_id, topic, text, correct_answer, image_filename, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        ).format(table=sql.Identifier(self._table_name))

        self._client.execute_many(
            query,
            [
                (
                    question.number,
                    question.question_id,
                    question.topic,
                    question.text,
                    question.correct_answer,
                    question.image_filename,
                    question.embedding,
                )
                for question in questions
            ],
        )
