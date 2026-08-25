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
    "lexeme_fields",
    "shuffle_seed",
    "corpus_commit",
    "corpus_comma_count",
    "question_limit",
    "origin",
)

# Insertable columns of `quiz_labelings`, in table order. `id` and `created_at` are
# DB-generated and excluded. There is no `_LABEL_COLUMNS` tuple: the
# `quiz_comma_labels` child columns are written out inside `insert_labeling`'s CTE,
# and `labeling_id` among them comes from `parent.id` rather than from the entity.
_LABELING_COLUMNS = ("run_id", "quiz_question_id", "rationale")


class GoldenSetWriteRepository:
    """Insert-only repository over the three golden-set tables (AD-10).

    Issues `INSERT` statements only — no `UPDATE`, no `DELETE`, no DDL. A run is
    never corrected in place: a re-labeling is a new run (AD-5 historizes rather than
    updates). `insert_labeling` is idempotent under `UNIQUE (run_id,
    quiz_question_id)` (AD-19, spec 0012): a repeated write for the same pair is
    silently discarded via `ON CONFLICT DO NOTHING`, so two racing writers never
    raise, and the loser's `None` return signals "read the existing row instead".

    `has_supporting_commas` is the derived outcome of a labeling (spec 0012, FR-15/
    AD-10), computed by `insert_labeling` itself from the very array that feeds its
    children — never supplied by a caller, so the flag and its rows cannot
    physically disagree.

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
        # psycopg adapts a `tuple` to a Postgres record, not an array, so `lexeme_fields`
        # must be passed as a `list` to reach `TEXT[]` correctly.
        params = [getattr(run, column) for column in _RUN_COLUMNS]
        params[_RUN_COLUMNS.index("lexeme_fields")] = list(run.lexeme_fields)
        rows = self._client.fetch(query, params)
        return int(rows[0][0])

    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int | None:
        """Inserts one `quiz_labelings` row and its `quiz_comma_labels` children.

        Both are written by a single data-modifying CTE, so the pair is atomic: a
        failing child insert (e.g. a foreign-key violation) leaves no parent row
        either. An empty `labels` sequence needs no branch — `unnest` over four empty
        arrays yields no rows, so the child `INSERT` inserts nothing and the parent is
        written alone, which is the "no justifying comma" outcome, not an error.

        `has_supporting_commas` is derived here, from the very array that feeds the
        children (spec 0012, FR-15/AD-10): one statement, one array, so the flag and
        its rows cannot physically disagree. No caller supplies it, and the field is
        deliberately absent from `QuizLabelingEntity`.

        Returns:
            The new labeling's id, or `None` when another writer already inserted a
            labeling for this `(run_id, quiz_question_id)` pair. `None` is not an
            error (AD-19): the caller re-reads the current labeling instead. The
            `children` CTE needs no branch for that case — it cross-joins `parent`,
            so an empty parent inserts nothing.
        """
        query = sql.SQL(
            "WITH parent AS ("
            "INSERT INTO {labelings} ({labeling_columns}, has_supporting_commas) "
            "VALUES ({labeling_placeholders}, cardinality(%s::bigint[]) > 0) "
            "ON CONFLICT (run_id, quiz_question_id) DO NOTHING RETURNING id"
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
        # Named once and reused for both the `cardinality()` check and the `unnest()`
        # call, rather than reconstructing the same list twice.
        comma_ids = [label.article_comma_id for label in labels]
        params: list[object] = [getattr(labeling, column) for column in _LABELING_COLUMNS]
        params.append(comma_ids)
        params.extend(
            [
                comma_ids,
                [label.judge_rank for label in labels],
                [label.dense_rank for label in labels],
                [label.text_rank for label in labels],
            ]
        )
        rows = self._client.fetch(query, params)
        return int(rows[0][0]) if rows else None

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
