"""Records submitted answers, summarizes a session's results and exposes a user's history."""

from psycopg import sql
from pywire import Autowired, repository

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import (
    AnsweredQuestion,
    SessionSummary,
    TopicSummary,
    WrongQuestion,
)


@repository
class QuizAnswerRepository:
    """Every write/read the API makes against `quiz_answers` (spec 0016, FR-5, FR-9).

    Both `user_id` and `quiz_id` are surrogate foreign keys; neither is ever resolved
    to a Python value anywhere in this design (see this plan's Global Constraints) —
    `record_answer` resolves both server-side from the natural keys the caller
    actually has (`telegram_user_id`, `number`) in a single `INSERT ... SELECT`.
    Synchronous, like every repository here (AD-10).
    """

    config: Autowired[AppConfig]
    postgres: Autowired[PostgresClientProvider]

    def record_answer(
        self, telegram_user_id: int, number: str, session_id: str, user_answer: bool
    ) -> None:
        """Inserts one `quiz_answers` row (FR-5, AD-7).

        No deduplication: the same question answered twice in the same or different
        sessions produces two rows (FR-5's third acceptance criterion). Both callers
        of this method (`QuizAnswerChecker`, Task 6) have already validated that the
        user is registered and the question exists, so an empty `INSERT ... SELECT`
        here signals a genuine invariant violation, not a client-facing condition —
        it is surfaced as a plain `RuntimeError`, not a domain/HTTP-mapped exception.
        """
        query = sql.SQL(
            "INSERT INTO {answers} (user_id, quiz_id, session_id, user_answer) "
            "SELECT u.id, q.id, %s, %s FROM {users} u, {questions} q "
            "WHERE u.telegram_user_id = %s AND q.number = %s "
            "RETURNING id"
        ).format(
            answers=sql.Identifier(self.config.quiz_answers_table),
            users=sql.Identifier(self.config.users_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
        rows = self.postgres.client.fetch(
            query, [session_id, user_answer, telegram_user_id, number]
        )
        if not rows:
            raise RuntimeError(
                f"Could not record an answer for telegram_user_id={telegram_user_id!r}, "
                f"number={number!r}: no matching user/question row (invariant violation, "
                "caller should have validated both beforehand)."
            )

    def session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        """Returns a session's totals, per-topic breakdown and wrongly answered questions.

        Correctness is computed via a `JOIN` against `quiz_questions.correct_answer` on
        every call, never cached (same rule AD-3 already applies to every other
        correctness check in this spec) — `AD-16`. The totals are the sums of the
        per-topic rows, so the three parts can never disagree with each other.
        """
        params = [telegram_user_id, session_id]
        topic_rows = self.postgres.client.fetch(
            sql.SQL(
                "SELECT q.topic, count(*), "
                "count(*) FILTER (WHERE qa.user_answer = q.correct_answer) "
                "{scope} GROUP BY q.topic ORDER BY q.topic"
            ).format(scope=self._session_scope()),
            params,
        )
        wrong_rows = self.postgres.client.fetch(
            sql.SQL(
                "SELECT q.number, q.text {scope} AND qa.user_answer <> q.correct_answer "
                "GROUP BY q.number, q.text ORDER BY min(qa.id)"
            ).format(scope=self._session_scope()),
            params,
        )
        by_topic = [
            TopicSummary(topic=topic, answered=int(answered), correct=int(correct))
            for topic, answered, correct in topic_rows
        ]
        return SessionSummary(
            answered=sum(topic.answered for topic in by_topic),
            correct=sum(topic.correct for topic in by_topic),
            by_topic=by_topic,
            wrong_questions=[
                WrongQuestion(number=number, text=text) for number, text in wrong_rows
            ],
        )

    def user_history(self, telegram_user_id: int) -> list[AnsweredQuestion]:
        """Returns every answer the user ever recorded, oldest first (spec 0024, AD-2).

        Correctness is derived in SQL against `quiz_questions.correct_answer` on every
        call, never stored. Rows follow insertion order (`qa.id`), which callers rely on
        to replay the history chronologically. No mastery rule lives here: the repository
        only reads, `MasteryCalculator` interprets.
        """
        query = sql.SQL(
            "SELECT q.number, q.topic, qa.session_id, qa.user_answer = q.correct_answer "
            "FROM {answers} qa "
            "JOIN {users} u ON u.id = qa.user_id "
            "JOIN {questions} q ON q.id = qa.quiz_id "
            "WHERE u.telegram_user_id = %s ORDER BY qa.id"
        ).format(
            answers=sql.Identifier(self.config.quiz_answers_table),
            users=sql.Identifier(self.config.users_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
        rows = self.postgres.client.fetch(query, [telegram_user_id])
        return [
            AnsweredQuestion(
                number=number, topic=topic, session_id=session_id, is_correct=is_correct
            )
            for number, topic, session_id, is_correct in rows
        ]

    def _session_scope(self) -> sql.Composed:
        """The `FROM ... WHERE` that limits a summary query to one user's one session (AD-16).

        Shared by every `session_summary` query so the two of them can never scope
        differently: `u.telegram_user_id` too, not just `session_id`, so a reused
        `session_id` never exposes another user's answers.
        """
        return sql.SQL(
            "FROM {answers} qa "
            "JOIN {users} u ON u.id = qa.user_id "
            "JOIN {questions} q ON q.id = qa.quiz_id "
            "WHERE u.telegram_user_id = %s AND qa.session_id = %s"
        ).format(
            answers=sql.Identifier(self.config.quiz_answers_table),
            users=sql.Identifier(self.config.users_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
