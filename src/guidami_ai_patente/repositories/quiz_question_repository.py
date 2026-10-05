"""Read access to the quiz bank for the API's no-LLM endpoints."""

from psycopg import sql
from pywire import Autowired, repository

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import (
    QuestionContext,
    QuestionVocabularyContext,
    QuizQuestionSummary,
    TopicCount,
)


@repository
class QuizQuestionRepository:
    """Every read the quiz endpoints make against `quiz_questions`.

    Deliberately lean and app-local rather than an extension of
    `commons.QuizReadRepository`, which is shaped for the evaluation harness (it
    inner-joins the embeddings table and returns whole `QuizEvaluationRow`s carrying
    the correct answer and the query vector). The API needs seven narrow projections
    and none of that payload — AD-17 carried this choice forward from the superseded
    quiz-check spec. `find_question_context` is the one projection among the seven
    that reaches beyond `quiz_questions`, `LEFT JOIN`ing `quiz_images` for the
    explanation writer (FR-10).

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

        Note: this only checks that an embedding ROW exists for the variant (an
        `EXISTS` over the join), not that any specific model column on it is
        non-NULL — unlike `commons/repositories/db/quiz_read_repository.py`'s
        `find_with_vector`, which additionally requires the given model column to be
        non-NULL. This is currently safe because `db/init.sql`'s
        `CHECK (num_nonnulls(embedding_3_small) > 0)` constraint prevents a row from
        existing with a NULL embedding column at all. If a second `embedding_*`
        column is ever added and that CHECK relaxed, this method would need to also
        check the specific column, the same way `find_with_vector` does.
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

    def find_question_context(self, number: str) -> QuestionContext | None:
        """Returns what the writer needs about a question, or `None` (FR-10).

        One read instead of `find_by_number` plus `find_correct_answer`, and the only
        place the API reaches `quiz_images.description`: the description is what lets
        the writer explain a sign-recognition question whose commas state the rule in
        the abstract. `LEFT JOIN` because most questions have no image.

        `None` means no such question, which the caller renders as a 404 — the same
        absence-not-exception convention as every other read here.
        """
        query = sql.SQL(
            "SELECT q.text, q.correct_answer, i.description FROM {questions} q "
            "LEFT JOIN {images} i ON i.filename = q.image_filename "
            "WHERE q.number = %s"
        ).format(
            questions=sql.Identifier(self.config.quiz_questions_table),
            images=sql.Identifier(self.config.quiz_images_table),
        )
        rows = self.postgres.client.fetch(query, [number])
        if not rows:
            return None
        text, correct_answer, image_description = rows[0]
        return QuestionContext(
            text=text, correct_answer=bool(correct_answer), image_description=image_description
        )

    def find_question_vocabulary_context(
        self, number: str, variant: str
    ) -> QuestionVocabularyContext | None:
        """Returns what the vocabulary stage needs about a question, or `None` (AD-4).

        Answer-blind by construction: the projection has no `correct_answer` column, not
        merely an unused one. `embedding` is `None` when no `variant` row exists for
        this question — `GlossaryReadRepository` (Task 5) degrades to its full-text arm
        in that case (FR-4), it does not fail. `variant` is the caller's choice (the live
        epoch's `candidate_variant`), never a literal here, so the glossary probe always
        reads the same stored representation as comma retrieval.
        """
        query = sql.SQL(
            "SELECT q.text, i.description, e.embedding_3_small FROM {questions} q "
            "LEFT JOIN {images} i ON i.filename = q.image_filename "
            "LEFT JOIN {embeddings} e ON e.quiz_question_id = q.id AND e.variant = %s "
            "WHERE q.number = %s"
        ).format(
            questions=sql.Identifier(self.config.quiz_questions_table),
            images=sql.Identifier(self.config.quiz_images_table),
            embeddings=sql.Identifier(self.config.quiz_question_embeddings_table),
        )
        rows = self.postgres.client.fetch(query, [variant, number])
        if not rows:
            return None
        text, image_description, embedding = rows[0]
        return QuestionVocabularyContext(
            text=text, image_description=image_description, embedding=embedding
        )

    @staticmethod
    def _to_summary(rows: list[tuple]) -> QuizQuestionSummary | None:
        """Maps the shared four-column projection, or `None` for an empty result."""
        if not rows:
            return None
        number, topic, text, image_filename = rows[0]
        return QuizQuestionSummary(
            number=number, topic=topic, text=text, image_filename=image_filename
        )
