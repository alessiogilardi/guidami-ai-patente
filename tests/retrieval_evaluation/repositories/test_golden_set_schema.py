"""Schema tests for the three golden-set tables (spec 0011, T-1)."""

from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig

_TABLES = ("labeling_runs", "quiz_labelings", "quiz_comma_labels")

# (table_name, column_name) -> (data_type, is_nullable), exactly as specified by the
# spec's Data Model / T-1's literal DDL. `id`/`created_at` are DB-generated but still
# real columns of the table, so they are asserted too.
_EXPECTED_COLUMNS: dict[tuple[str, str], tuple[str, str]] = {
    ("labeling_runs", "id"): ("bigint", "NO"),
    ("labeling_runs", "judge_model"): ("text", "NO"),
    ("labeling_runs", "prompt_version"): ("text", "NO"),
    ("labeling_runs", "candidate_variant"): ("text", "NO"),
    ("labeling_runs", "dense_k"): ("integer", "NO"),
    ("labeling_runs", "text_k"): ("integer", "NO"),
    ("labeling_runs", "shuffle_seed"): ("bigint", "NO"),
    ("labeling_runs", "corpus_commit"): ("text", "NO"),
    ("labeling_runs", "corpus_comma_count"): ("integer", "NO"),
    ("labeling_runs", "question_limit"): ("integer", "YES"),
    ("labeling_runs", "created_at"): ("timestamp with time zone", "NO"),
    ("quiz_labelings", "id"): ("bigint", "NO"),
    ("quiz_labelings", "run_id"): ("bigint", "NO"),
    ("quiz_labelings", "quiz_question_id"): ("bigint", "NO"),
    ("quiz_labelings", "rationale"): ("text", "NO"),
    ("quiz_labelings", "created_at"): ("timestamp with time zone", "NO"),
    ("quiz_comma_labels", "labeling_id"): ("bigint", "NO"),
    ("quiz_comma_labels", "article_comma_id"): ("bigint", "NO"),
    ("quiz_comma_labels", "judge_rank"): ("integer", "NO"),
    ("quiz_comma_labels", "dense_rank"): ("integer", "YES"),
    ("quiz_comma_labels", "text_rank"): ("integer", "YES"),
}


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        yield client


@pytest.mark.integration
def test_golden_set_tables_exist_with_their_columns(client: PostgresClient) -> None:
    rows = client.fetch(
        sql.SQL(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = ANY(%s) "
            "ORDER BY table_name, ordinal_position"
        ),
        [list(_TABLES)],
    )
    actual_columns = {
        (table_name, column_name): (data_type, is_nullable)
        for table_name, column_name, data_type, is_nullable in rows
    }

    assert actual_columns == _EXPECTED_COLUMNS, (
        "labeling_runs / quiz_labelings / quiz_comma_labels do not match the spec's "
        "Data Model exactly"
    )
    assert ("quiz_labelings", "outcome") not in actual_columns, (
        "quiz_labelings must have no outcome column (AD-6): the outcome is derived by "
        "counting quiz_comma_labels children"
    )


@pytest.mark.integration
def test_golden_set_constraints_exist(client: PostgresClient) -> None:
    constraint_rows = client.fetch(
        sql.SQL(
            "SELECT tc.table_name, tc.constraint_name, tc.constraint_type "
            "FROM information_schema.table_constraints tc "
            "WHERE tc.table_name = ANY(%s)"
        ),
        [list(_TABLES)],
    )
    constraints = {
        (table_name, constraint_name): constraint_type
        for table_name, constraint_name, constraint_type in constraint_rows
    }

    assert constraints.get(("quiz_comma_labels", "quiz_comma_labels_at_least_one_arm")) == "CHECK"
    assert (
        constraints.get(("quiz_comma_labels", "quiz_comma_labels_unique_judge_rank")) == "UNIQUE"
    )

    unique_judge_rank_columns = client.fetch(
        sql.SQL(
            "SELECT column_name FROM information_schema.key_column_usage "
            "WHERE table_name = 'quiz_comma_labels' "
            "AND constraint_name = 'quiz_comma_labels_unique_judge_rank' "
            "ORDER BY ordinal_position"
        )
    )
    assert [row[0] for row in unique_judge_rank_columns] == ["labeling_id", "judge_rank"]

    quiz_labelings_unique = [
        constraint_name
        for (table_name, constraint_name), constraint_type in constraints.items()
        if table_name == "quiz_labelings" and constraint_type == "UNIQUE"
    ]
    assert quiz_labelings_unique, "quiz_labelings has no UNIQUE (run_id, quiz_question_id)"

    primary_key_columns = client.fetch(
        sql.SQL(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON kcu.constraint_name = tc.constraint_name "
            "WHERE tc.table_name = 'quiz_comma_labels' AND tc.constraint_type = 'PRIMARY KEY' "
            "ORDER BY kcu.ordinal_position"
        )
    )
    assert [row[0] for row in primary_key_columns] == ["labeling_id", "article_comma_id"]

    assert _EXPECTED_COLUMNS[("labeling_runs", "question_limit")][1] == "YES"
