"""Tests for GlossaryReadRepository's hybrid retrieval (FR-4)."""

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import GlossaryReadRepository

_TABLES = ("glossary_entries",)


@pytest.fixture(autouse=True)
def _clean_glossary(api_client: object) -> None:
    """Truncates glossary_entries before and after every test in this file."""
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    yield
    client.truncate(*_TABLES)


def _seed_entry(
    *, term: str, definition: str, source: str, article_number: str, comma_number: str
) -> None:
    """Inserts one glossary_entries row with no embedding (full-text-arm-only fixture)."""
    client = get_default_container().resolve(PostgresClientProvider).client
    client.execute(
        sql.SQL(
            "INSERT INTO glossary_entries "
            "(source, article_number, comma_number, term, definition, term_ru, embedding_3_small) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)"
        ),
        [source, article_number, comma_number, term, definition, "x", [0.1] * 1536],
    )


def _seed_entry_with_embedding(*, term: str, definition: str) -> list[float]:
    """Inserts one row with a distinctive embedding and returns that same vector.

    Returning the exact vector the row was seeded with lets a dense-arm test query for
    that vector and expect an exact (distance-zero) match, without depending on real
    embedding-model output.
    """
    embedding = [0.9] * 1536
    client = get_default_container().resolve(PostgresClientProvider).client
    client.execute(
        sql.SQL(
            "INSERT INTO glossary_entries "
            "(source, article_number, comma_number, term, definition, term_ru, embedding_3_small) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)"
        ),
        ["cds", "3", "1", term, definition, "x", embedding],
    )
    return embedding


@pytest.mark.integration
def test_an_empty_table_returns_no_candidates_without_error(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    """Independence from Spec 0019: an empty glossary_entries is valid, not an error."""
    repository = get_default_container().resolve(GlossaryReadRepository)
    assert repository.candidates_for("La domanda parla di banchina.", embedding=None) == []


@pytest.mark.integration
def test_the_full_text_arm_finds_an_inflected_form(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    """'carreggiate' (plural) must match a stored term 'carreggiata' via Italian stemming."""
    _seed_entry(
        term="carreggiata", definition="...", source="cds", article_number="3", comma_number="1"
    )

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for("Le carreggiate a doppio senso.", embedding=None)

    assert any(c.term == "carreggiata" for c in candidates)


@pytest.mark.integration
def test_the_dense_arm_returns_a_semantically_near_entry(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    embedding = _seed_entry_with_embedding(term="banchina", definition="...")

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for("testo qualsiasi", embedding=embedding)

    assert any(c.term == "banchina" for c in candidates)


@pytest.mark.integration
def test_an_entry_found_by_both_arms_ranks_first(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    embedding = _seed_entry_with_embedding(term="carreggiata", definition="...")

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for("La carreggiata è larga.", embedding=embedding)

    assert candidates[0].term == "carreggiata"


@pytest.mark.integration
def test_no_embedding_degrades_to_the_full_text_arm_only(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    _seed_entry(
        term="carreggiata", definition="...", source="cds", article_number="3", comma_number="1"
    )

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for("La carreggiata è larga.", embedding=None)

    assert any(c.term == "carreggiata" for c in candidates)


@pytest.mark.integration
def test_text_only_matches_keep_their_own_relevance_order(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    """Regression test for the pre-RRF bug (grilling round, 2026-09-23).

    The old Python-side sort tied every text-only match at the same surrogate key,
    breaking ties by `id` instead of by `ts_rank` — a stronger lexical match could
    come back after a weaker one. RRF's `1/(60+text_rank)` term preserves the real
    order.
    """
    _seed_entry(
        term="sosta",
        definition="Fermata del veicolo protratta oltre il tempo per la salita/discesa.",
        source="cds",
        article_number="157",
        comma_number="1",
    )
    _seed_entry(
        term="fermata",
        definition="Sospensione della marcia limitata al tempo per la salita/discesa.",
        source="cds",
        article_number="157",
        comma_number="6",
    )

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for(
        "Cosa si intende per sosta di un veicolo?", embedding=None
    )

    terms = [c.term for c in candidates]
    assert terms.index("sosta") < terms.index("fermata")
