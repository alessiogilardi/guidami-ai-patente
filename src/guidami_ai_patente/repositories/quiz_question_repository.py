"""Read access to the quiz bank for the API's no-LLM endpoints."""

from psycopg import sql
from pywire import Autowired, repository

# Direct file import (not the `guidami_ai_patente.clients` package re-export): avoids a
# clients<->repositories package-init circular import, since `clients/__init__` imports
# `AgentConfigRepository` from this package.
from guidami_ai_patente.clients.postgres_client_provider import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import QuizQuestionSummary, TopicCount


@repository
class QuizQuestionRepository:
    """Every read the quiz endpoints make against `quiz_questions`.

    Deliberately lean and app-local rather than an extension of
    `commons.QuizReadRepository`, which is shaped for the evaluation harness (it
    inner-joins the embeddings table and returns whole `QuizEvaluationRow`s carrying
    the correct answer and the query vector). The API needs four narrow projections
    and none of that payload — AD-17 carried this choice forward from the superseded
    quiz-check spec.

    Synchronous by construction: psycopg is, and the routers cross the boundary with
    `asyncio.to_thread` (AD-25). Absence is returned as `None`/`False`/`[]`, never
    raised: FR-4's status rule branches on the absence itself, so turning it into an
    exception here would force the caller to catch its way back to the same
    information.
    """

    config: Autowired[AppConfig]
    postgres: Autowired[PostgresClientProvider]

    def find_by_permutation(
        self, seed: str, index: int, topic: str | None
    ) -> QuizQuestionSummary | None:
        """Returns the question at `index` of the permutation `seed` induces (FR-1).

        The ordering is `md5(id::text || seed)` — the mechanism
        `CorpusReadRepository.random_top_k` already proved — with `id` as the
        tie-break so the permutation is total. The filter is expressed as
        `(%s::text IS NULL OR topic = %s)` so one statement serves both the filtered
        and the unfiltered case.

        Returns `None` when `index` is at or past the number of matching questions,
        which the caller renders as a 404 (FR-1). The permutation is derived from the
        *current* id set, so a re-ingestion reshuffles it — an accepted limitation
        (AD-18), not a defect.
        """
        query = sql.SQL(
            "SELECT number, topic, text, image_filename FROM {table} "
            "WHERE (%s::text IS NULL OR topic = %s) "
            "ORDER BY md5(id::text || %s), id OFFSET %s LIMIT 1"
        ).format(table=sql.Identifier(self.config.quiz_questions_table))
        rows = self.postgres.client.fetch(query, [topic, topic, seed, index])
        return self._to_summary(rows)

    def find_by_number(self, number: str) -> QuizQuestionSummary | None:
        """Returns the question with this `number`, or `None` (FR-2).

        Same projection as `find_by_permutation`, deliberately: a client that
        restarts and re-fetches must get the identical shape it was proposed.
        """
        query = sql.SQL(
            "SELECT number, topic, text, image_filename FROM {table} WHERE number = %s"
        ).format(table=sql.Identifier(self.config.quiz_questions_table))
        rows = self.postgres.client.fetch(query, [number])
        return self._to_summary(rows)

    def find_correct_answer(self, number: str) -> bool | None:
        """Returns the stored answer for `number`, or `None` when no row matches (FR-3).

        A single indexed lookup on `UNIQUE (number)`. `None` means "no such question",
        never "the answer is unknown": the column is `NOT NULL`.
        """
        query = sql.SQL("SELECT correct_answer FROM {table} WHERE number = %s").format(
            table=sql.Identifier(self.config.quiz_questions_table)
        )
        rows = self.postgres.client.fetch(query, [number])
        return bool(rows[0][0]) if rows else None

    def list_topics(self) -> list[TopicCount]:
        """Returns every distinct topic with its question count, ascending (FR-16).

        Ordered by `topic` so the client renders a stable menu, and empty rather than
        absent on an empty bank — "no topics yet" is a successful answer (AD-31).
        """
        query = sql.SQL(
            "SELECT topic, count(*) AS question_count FROM {table} GROUP BY topic ORDER BY topic"
        ).format(table=sql.Identifier(self.config.quiz_questions_table))
        rows = self.postgres.client.fetch(query)
        return [TopicCount(topic=row[0], question_count=int(row[1])) for row in rows]

    def image_is_referenced(self, filename: str) -> bool:
        """Reports whether any question references this image filename (FR-12).

        The authorisation check AD-24 requires **before** any filesystem access: the
        endpoint serves exactly the images the database names and nothing else, so a
        traversal attempt is rejected by the absence of a matching row rather than by
        string sanitising.
        """
        query = sql.SQL("SELECT EXISTS (SELECT 1 FROM {table} WHERE image_filename = %s)").format(
            table=sql.Identifier(self.config.quiz_questions_table)
        )
        rows = self.postgres.client.fetch(query, [filename])
        return bool(rows[0][0])

    def has_embedding(self, number: str, variant: str) -> bool:
        """Reports whether a query vector exists for this question and variant (FR-4).

        Only reached on a cache miss: a current labeling needs no retrieval and
        therefore no vector, so a missing embedding can never downgrade a cache hit
        (FR-4, FR-7).
        """
        query = sql.SQL(
            "SELECT EXISTS (SELECT 1 FROM {embeddings} e JOIN {questions} q "
            "ON q.id = e.quiz_question_id WHERE q.number = %s AND e.variant = %s)"
        ).format(
            embeddings=sql.Identifier(self.config.quiz_question_embeddings_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
        rows = self.postgres.client.fetch(query, [number, variant])
        return bool(rows[0][0])

    @staticmethod
    def _to_summary(rows: list[tuple]) -> QuizQuestionSummary | None:
        """Maps the shared four-column projection, or `None` for an empty result."""
        if not rows:
            return None
        number, topic, text, image_filename = rows[0]
        return QuizQuestionSummary(
            number=number, topic=topic, text=text, image_filename=image_filename
        )
