"""Records submitted answers and summarizes a session's results."""

from psycopg import sql
from pywire import Autowired, repository

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import SessionSummary


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
        """Returns how many answers were recorded for this session, and how many were correct.

        Correctness is computed via a `JOIN` against `quiz_questions.correct_answer` on
        every call, never cached (same rule AD-3 already applies to every other
        correctness check in this spec) — `AD-16`.
        """
        query = sql.SQL(
            "SELECT count(*), "
            "count(*) FILTER (WHERE qa.user_answer = q.correct_answer) "
            "FROM {answers} qa "
            "JOIN {users} u ON u.id = qa.user_id "
            "JOIN {questions} q ON q.id = qa.quiz_id "
            "WHERE u.telegram_user_id = %s AND qa.session_id = %s"
        ).format(
            answers=sql.Identifier(self.config.quiz_answers_table),
            users=sql.Identifier(self.config.users_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
        rows = self.postgres.client.fetch(query, [telegram_user_id, session_id])
        answered, correct = rows[0]
        return SessionSummary(answered=int(answered), correct=int(correct))
