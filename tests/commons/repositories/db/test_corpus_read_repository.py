from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.repositories.db import CorpusReadRepository


def _vector(dimension: int, hot_index: int) -> list[float]:
    """Builds a 1536-dim one-hot vector, used so cosine distance is unambiguous."""
    vector = [0.0] * dimension
    vector[hot_index] = 1.0
    return vector


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("article_commas", "articles")
        yield client
        client.truncate("article_commas", "articles")


def _insert_article(client: PostgresClient, source: str, number: str, title: str) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO articles (source, number, title, url, scraped_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [source, number, title, "https://example.test", datetime.now(UTC)],
    )
    return rows[0][0]


def _insert_comma(
    client: PostgresClient,
    article_id: int,
    comma_number: str,
    text: str,
    embedding: list[float] | None,
) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [article_id, comma_number, 0, text, embedding],
    )
    return rows[0][0]


def _insert_comma_with_id(
    client: PostgresClient,
    comma_id: int,
    article_id: int,
    comma_number: str,
    text: str,
    embedding: list[float] | None,
) -> int:
    """Inserts a comma with an explicit `id`, decoupled from insertion order.

    Used by tie-breaking tests so a comma's row *position* on disk and its numeric
    `id` are deliberately independent: without a tiebreaker, equal-scoring rows come
    back in scan order, which otherwise coincides with ascending `id` on a freshly
    truncated table where every row is inserted through the auto-incrementing
    sequence, masking the missing `ORDER BY ... , c.id` clause.
    """
    client.execute(
        sql.SQL(
            "INSERT INTO article_commas (id, article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        [comma_id, article_id, comma_number, 0, text, embedding],
    )
    return comma_id


@pytest.mark.integration
def test_dense_top_k_returns_source_qualified_commas(client: PostgresClient) -> None:
    cds_article_id = _insert_article(client, "cds", "43", "Segnaletica CdS")
    reg_article_id = _insert_article(client, "reg", "43", "Segnaletica Regolamento")
    _insert_comma(client, cds_article_id, "1", "Testo cds.", _vector(1536, 0))
    _insert_comma(client, reg_article_id, "1", "Testo reg.", _vector(1536, 1))

    repository = CorpusReadRepository("articles", "article_commas", client)
    query_vector = _vector(1536, 0)

    results = repository.dense_top_k(query_vector, k=2)

    assert len(results) == 2
    assert results[0].distance <= results[1].distance
    assert results[0].source == "cds"
    assert all(comma.article_title for comma in results)


@pytest.mark.integration
def test_random_top_k_excludes_unembedded_commas(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Titolo")
    _insert_comma(client, article_id, "1", "Comma senza embedding.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    for seed_key in ("seed-a", "seed-b", "seed-c"):
        results = repository.random_top_k(k=5, seed_key=seed_key)
        assert all(comma.comma_number != "1" for comma in results)


@pytest.mark.integration
def test_dense_top_k_returns_the_comma_database_id(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "43", "Segnaletica CdS")
    comma_id = _insert_comma(client, article_id, "1", "Testo cds.", _vector(1536, 0))

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.dense_top_k(_vector(1536, 0), k=1)

    assert len(results) == 1
    assert results[0].id == comma_id


@pytest.mark.integration
def test_random_top_k_returns_the_comma_database_id(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Titolo")
    comma_id = _insert_comma(client, article_id, "1", "Comma con embedding.", _vector(1536, 0))

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.random_top_k(k=1, seed_key="seed-a")

    assert len(results) == 1
    assert results[0].id == comma_id


@pytest.mark.integration
def test_search_columns_are_generated_and_indexed(client: PostgresClient) -> None:
    column_rows = client.fetch(
        sql.SQL(
            "SELECT table_name, is_generated FROM information_schema.columns "
            "WHERE (table_name = 'articles' AND column_name = 'tsv_title') "
            "OR (table_name = 'article_commas' AND column_name = 'tsv_text')"
        )
    )
    generation_by_table = dict(column_rows)

    assert generation_by_table.get("articles") == "ALWAYS", (
        "articles.tsv_title is not a generated column"
    )
    assert generation_by_table.get("article_commas") == "ALWAYS", (
        "article_commas.tsv_text is not a generated column"
    )

    index_rows = client.fetch(
        sql.SQL(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE indexname IN ('idx_articles_tsv_title', 'idx_article_commas_tsv_text')"
        )
    )
    indexdef_by_name = dict(index_rows)

    assert "idx_articles_tsv_title" in indexdef_by_name
    assert "using gin" in indexdef_by_name["idx_articles_tsv_title"].lower()
    assert "idx_article_commas_tsv_text" in indexdef_by_name
    assert "using gin" in indexdef_by_name["idx_article_commas_tsv_text"].lower()


@pytest.mark.integration
def test_generated_search_columns_follow_their_source_text(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Titolo iniziale")
    comma_id = _insert_comma(client, article_id, "1", "Testo iniziale.", None)

    client.execute(
        sql.SQL("UPDATE articles SET title = %s WHERE id = %s"),
        ["Segnaletica orizzontale", article_id],
    )
    client.execute(
        sql.SQL("UPDATE article_commas SET text = %s WHERE id = %s"),
        ["Obbligo di precedenza.", comma_id],
    )

    title_match = client.fetch(
        sql.SQL("SELECT tsv_title @@ to_tsquery('italian', %s) FROM articles WHERE id = %s"),
        ["segnaletica", article_id],
    )
    text_match = client.fetch(
        sql.SQL("SELECT tsv_text @@ to_tsquery('italian', %s) FROM article_commas WHERE id = %s"),
        ["precedenza", comma_id],
    )

    assert title_match[0][0] is True
    assert text_match[0][0] is True


@pytest.mark.integration
def test_text_match_top_k_ranks_matching_commas_and_excludes_the_rest(
    client: PostgresClient,
) -> None:
    article_a = _insert_article(client, "cds", "1", "Segnaletica stradale")
    article_b = _insert_article(client, "cds", "2", "Norme di circolazione")
    strong_match_id = _insert_comma(
        client, article_a, "1", "Precedenza precedenza obbligatoria all'incrocio.", None
    )
    weak_match_id = _insert_comma(
        client, article_a, "2", "Regola sulla precedenza ai pedoni.", None
    )
    _insert_comma(client, article_b, "1", "Limiti di velocita in autostrada.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.text_match_top_k(["precedenza"], k=10)

    assert [comma.id for comma in results] == [strong_match_id, weak_match_id]


@pytest.mark.integration
def test_text_match_top_k_returns_empty_when_nothing_matches(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    _insert_comma(client, article_id, "1", "Limiti di velocita in autostrada.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.text_match_top_k(["inesistente"], k=10)

    assert results == []


@pytest.mark.integration
def test_text_match_top_k_matches_on_the_article_title_alone(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica orizzontale")
    comma_id = _insert_comma(client, article_id, "1", "Obbligo di fermarsi al semaforo.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.text_match_top_k(["segnaletica"], k=10)

    assert [comma.id for comma in results] == [comma_id]


@pytest.mark.integration
def test_text_match_top_k_respects_k_and_is_deterministic(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    top_id = _insert_comma(
        client, article_id, "1", "Precedenza precedenza precedenza obbligatoria.", None
    )
    middle_id = _insert_comma(client, article_id, "2", "Precedenza precedenza ai pedoni.", None)
    _insert_comma(client, article_id, "3", "Precedenza in rotatoria.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    first_call = repository.text_match_top_k(["precedenza"], k=2)
    second_call = repository.text_match_top_k(["precedenza"], k=2)

    assert [comma.id for comma in first_call] == [top_id, middle_id]
    assert [comma.id for comma in first_call] == [comma.id for comma in second_call]


@pytest.mark.integration
def test_text_match_top_k_uses_a_gin_index(client: PostgresClient) -> None:
    # Local import: `_text_match_query` does not exist yet (T-1). Importing the module
    # rather than the symbol keeps collection of the rest of this file green until it
    # is implemented — only this test fails, with an AttributeError.
    from commons.repositories.db import corpus_read_repository

    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    _insert_comma(client, article_id, "1", "Obbligo di precedenza all'incrocio.", None)

    client.execute(sql.SQL("SET enable_seqscan = off"))

    query = sql.SQL("EXPLAIN ") + corpus_read_repository._text_match_query(
        sql.Identifier("article_commas"), sql.Identifier("articles")
    )
    plan_rows = client.fetch(query, ["precedenza", 10])
    plan_text = "\n".join(row[0] for row in plan_rows)

    assert "Bitmap Index Scan" in plan_text
    assert "idx_articles_tsv_title" in plan_text or "idx_article_commas_tsv_text" in plan_text


@pytest.mark.integration
def test_text_match_top_k_breaks_score_ties_by_ascending_comma_id(
    client: PostgresClient,
) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    # Explicit, non-monotonic ids: without them the physical scan order of a freshly
    # truncated table coincides with ascending id, masking a missing tiebreaker.
    comma_ids = [
        _insert_comma_with_id(
            client, 900_000_003, article_id, "1", "Obbligo di precedenza.", None
        ),
        _insert_comma_with_id(
            client, 900_000_001, article_id, "2", "Obbligo di precedenza.", None
        ),
        _insert_comma_with_id(
            client, 900_000_002, article_id, "3", "Obbligo di precedenza.", None
        ),
    ]

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.text_match_top_k(["precedenza"], k=3)

    assert [comma.id for comma in results] == sorted(comma_ids)


@pytest.mark.integration
def test_text_match_top_k_cut_is_stable_when_scores_tie_at_k(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    comma_ids = [
        _insert_comma_with_id(
            client, 900_000_004, article_id, "1", "Obbligo di precedenza.", None
        ),
        _insert_comma_with_id(
            client, 900_000_002, article_id, "2", "Obbligo di precedenza.", None
        ),
        _insert_comma_with_id(
            client, 900_000_003, article_id, "3", "Obbligo di precedenza.", None
        ),
        _insert_comma_with_id(
            client, 900_000_001, article_id, "4", "Obbligo di precedenza.", None
        ),
    ]
    lowest_two_ids = sorted(comma_ids)[:2]

    repository = CorpusReadRepository("articles", "article_commas", client)

    first_call = repository.text_match_top_k(["precedenza"], k=2)
    second_call = repository.text_match_top_k(["precedenza"], k=2)

    assert [comma.id for comma in first_call] == lowest_two_ids
    assert [comma.id for comma in first_call] == [comma.id for comma in second_call]


@pytest.mark.integration
def test_dense_top_k_breaks_distance_ties_by_ascending_comma_id(
    client: PostgresClient,
) -> None:
    article_id = _insert_article(client, "cds", "1", "Segnaletica stradale")
    embedding = _vector(1536, 0)
    comma_ids = [
        _insert_comma_with_id(client, 900_000_103, article_id, "1", "Testo 1.", embedding),
        _insert_comma_with_id(client, 900_000_101, article_id, "2", "Testo 2.", embedding),
        _insert_comma_with_id(client, 900_000_102, article_id, "3", "Testo 3.", embedding),
    ]

    repository = CorpusReadRepository("articles", "article_commas", client)

    results = repository.dense_top_k(embedding, k=3)

    assert [comma.id for comma in results] == sorted(comma_ids)
