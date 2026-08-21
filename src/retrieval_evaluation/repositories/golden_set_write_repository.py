from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.evaluation import LabelingRunEntity, QuizCommaLabelEntity, QuizLabelingEntity

# Insertable columns of `labeling_runs`, in table order (see db/init.sql). `id` and
# `created_at` are DB-generated and excluded (entities-as-insertable-projection rule).
_RUN_COLUMNS = (
    "judge_model",
    "prompt_version",
    "candidate_variant",
    "dense_k",
    "text_k",
    "shuffle_seed",
    "corpus_commit",
    "corpus_comma_count",
    "question_limit",
)

# Insertable columns of `quiz_labelings`, in table order. `id` and `created_at` are
# DB-generated and excluded. There is no `_LABEL_COLUMNS` tuple: the
# `quiz_comma_labels` child columns are written out inside `insert_labeling`'s CTE,
# and `labeling_id` among them comes from `parent.id` rather than from the entity.
_LABELING_COLUMNS = ("run_id", "quiz_question_id", "rationale")


class GoldenSetWriteRepository:
    """Insert-only repository over the three golden-set tables (AD-10).

    Issues `INSERT` statements only — no `UPDATE`, no upsert/conflict-handling
    clause, no `DELETE`, no DDL. A run is never corrected in place: a re-labeling is
    a new run (AD-5 historizes rather than updates).

    A labeling's outcome is derived, never stored: zero `quiz_comma_labels` children
    means "the corpus does not justify this question", which is distinct from a
    missing `quiz_labelings` row for a question, meaning "never labeled" (AD-6).

    `insert_labeling` writes the parent `quiz_labelings` row and its
    `quiz_comma_labels` children in a single statement, atomic despite the
    connection's `autocommit=True` (PD-15): two separate statements would commit the
    parent independently of its children, and a failing child insert would leave a
    childless parent indistinguishable from a genuine "no justifying comma" outcome.

    The caller is responsible for the `judge_rank` values carried on `labels` — this
    repository writes them as given, with no reordering or validation of its own.
    """

    def __init__(
        self,
        labeling_runs_table: str,
        quiz_labelings_table: str,
        quiz_comma_labels_table: str,
        client: PostgresClient,
    ) -> None:
        """Injects the three table names and the `PostgresClient`."""
        self._client = client
        self._labeling_runs = sql.Identifier(labeling_runs_table)
        self._quiz_labelings = sql.Identifier(quiz_labelings_table)
        self._quiz_comma_labels = sql.Identifier(quiz_comma_labels_table)

    def insert_run(self, run: LabelingRunEntity) -> int:
        """Inserts one `labeling_runs` row and returns its generated id."""
        query = sql.SQL(
            "INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
        ).format(
            table=self._labeling_runs,
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in _RUN_COLUMNS),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in _RUN_COLUMNS),
        )
        rows = self._client.fetch(query, [getattr(run, column) for column in _RUN_COLUMNS])
        return int(rows[0][0])

    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int:
        """Inserts one `quiz_labelings` row and its `quiz_comma_labels` children.

        Both are written by a single data-modifying CTE (PD-15), so the pair is
        atomic: a failing child insert (e.g. a foreign-key violation) leaves no
        parent row either. An empty `labels` sequence needs no branch — `unnest`
        over four empty arrays yields no rows, so the child `INSERT` inserts nothing
        and the parent is written alone, which is the FR-8/AD-6 "no justifying
        comma" outcome, not an error.

        The `children` CTE is never selected from; that is deliberate and required.
        PostgreSQL executes a data-modifying CTE exactly once whether or not it is
        referenced, and this statement must return the parent id, not the children.
        """
        query = sql.SQL(
            "WITH parent AS ("
            "INSERT INTO {labelings} ({labeling_columns}) "
            "VALUES ({labeling_placeholders}) RETURNING id"
            "), children AS ("
            "INSERT INTO {labels} "
            "(labeling_id, article_comma_id, judge_rank, dense_rank, text_rank) "
            "SELECT parent.id, c.article_comma_id, c.judge_rank, c.dense_rank, c.text_rank "
            "FROM parent, unnest(%s::bigint[], %s::int[], %s::int[], %s::int[]) "
            "AS c(article_comma_id, judge_rank, dense_rank, text_rank)"
            ") "
            "SELECT id FROM parent"
        ).format(
            labelings=self._quiz_labelings,
            labels=self._quiz_comma_labels,
            labeling_columns=sql.SQL(", ").join(
                sql.Identifier(column) for column in _LABELING_COLUMNS
            ),
            labeling_placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in _LABELING_COLUMNS),
        )
        params: list[object] = [getattr(labeling, column) for column in _LABELING_COLUMNS]
        params.extend(
            [
                [label.article_comma_id for label in labels],
                [label.judge_rank for label in labels],
                [label.dense_rank for label in labels],
                [label.text_rank for label in labels],
            ]
        )
        rows = self._client.fetch(query, params)
        return int(rows[0][0])

    def outcome_counts(self, run_id: int) -> tuple[int, int]:
        """Returns `(with_commas, without_commas)` labeling counts for `run_id`.

        The single read method on this class: FR-12's "issues `INSERT` statements
        only" constrains the *write* path, and this is a `SELECT`, not a write. No
        `UPDATE`, `DELETE` or DDL is ever issued here or anywhere else on this class.
        """
        query = sql.SQL(
            "SELECT count(*) FILTER (WHERE child_count > 0), "
            "count(*) FILTER (WHERE child_count = 0) FROM ("
            "SELECT l.id, count(cl.article_comma_id) AS child_count "
            "FROM {labelings} l LEFT JOIN {labels} cl ON cl.labeling_id = l.id "
            "WHERE l.run_id = %s GROUP BY l.id"
            ") outcomes"
        ).format(labelings=self._quiz_labelings, labels=self._quiz_comma_labels)
        rows = self._client.fetch(query, [run_id])
        with_commas, without_commas = rows[0]
        return int(with_commas), int(without_commas)
