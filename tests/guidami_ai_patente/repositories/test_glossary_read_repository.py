"""Tests for GlossaryReadRepository's hybrid retrieval (FR-4)."""

from collections.abc import Generator

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import GlossaryReadRepository

_TABLES = ("glossary_entries",)


@pytest.fixture(autouse=True)
def _clean_glossary(api_client: object) -> Generator[None]:
    """Truncates glossary_entries before and after every test in this file."""
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    yield
    client.truncate(*_TABLES)


def _seed_entry(
    *,
    term: str,
    definition: str,
    source: str,
    article_number: str,
    comma_number: str,
    term_ru: str | None = "x",
) -> None:
    """Inserts one glossary_entries row with a fixed, non-distinctive embedding.

    Full-text-arm-only fixture: the embedding is a constant vector (not `NULL`, since
    `embedding_3_small` participates in the table's `glossary_entries_at_least_one_vector`
    check), shared by every row this helper seeds, so it never wins a dense-arm exact
    match the way `_seed_entry_with_embedding`'s distinctive vector does.

    `term_ru` defaults to a placeholder non-blank value; a test seeding `term_ru=None`
    covers the actual bug this fixes (spec 0019 AD-11: `build-glossary` never
    translates, so a row may legitimately have no Russian term yet).
    """
    client = get_default_container().resolve(PostgresClientProvider).client
    client.execute(
        sql.SQL(
            "INSERT INTO glossary_entries "
            "(source, article_number, comma_number, term, definition, term_ru, embedding_3_small) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)"
        ),
        [source, article_number, comma_number, term, definition, term_ru, [0.1] * 1536],
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
def test_a_row_with_no_russian_term_is_returned_without_raising(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    """Spec 0019 AD-11 regression.

    `build-glossary` never translates — only `translate-glossary-terms`'s separate
    pass does — so `glossary_entries.term_ru` can legitimately be `NULL` on the row
    `_row_to_candidate` maps. Before this fix, building `GlossaryCandidate(term_ru=
    None)` raised a `pydantic.ValidationError` here, inside `ExplanationService`'s
    vocabulary-stage `try` block, which the broad `except Exception` there silently
    swallowed as "Vocabulary stage failed" — dropping every citation for the request.
    This asserts the mapping itself no longer raises and preserves the `None`.
    """
    _seed_entry(
        term="carreggiata",
        definition="...",
        source="cds",
        article_number="3",
        comma_number="1",
        term_ru=None,
    )

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for("Le carreggiate a doppio senso.", embedding=None)

    matches = [c for c in candidates if c.term == "carreggiata"]
    assert len(matches) == 1
    assert matches[0].term_ru is None


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

    Both terms here are genuine (non-zero) matches against the query's tsquery
    ('cos' | 'intend' | 'sost' | 'veicol', the stems of "Cosa si intende per sosta
    di un veicolo?") — this is what actually exercises the bug this test guards
    against, without relying on the `WHERE g.tsv_term @@ p.tsquery` floor being
    absent (a later, separate bug: a floor-less query would let true zero-overlap
    noise, like "fermata" → 'ferm', into the arm; that is covered by
    `test_the_full_text_arm_finds_an_inflected_form` and the WHERE clause itself,
    not by this test).
    `glossary_entries.tsv_term` is generated from `term` alone, at a single weight
    ('A'), and `ts_rank` here is unnormalized — so any two single-word terms that
    each match exactly one query lexeme tie exactly (verified against live
    Postgres: both come back at 0.15198177). A genuine, *unequal* ranking
    therefore requires the two terms to match a different **number** of the
    query's lexemes, not merely "a strong word" vs "a weak word": "sosta dei
    veicoli" matches two of the four query lexemes ('sost' + 'veicol', ts_rank
    0.30396354), while "veicolo" alone matches only one ('veicol', ts_rank
    0.15198177) — both are real, on-topic matches for the question, but the
    former is more textually relevant and must rank first.
    """
    _seed_entry(
        term="sosta dei veicoli",
        definition="Sospensione della marcia non giustificata da esigenze della circolazione.",
        source="cds",
        article_number="157",
        comma_number="1",
    )
    _seed_entry(
        term="veicolo",
        definition="Ogni macchina di qualsiasi specie che circola sulla strada guidata dall'uomo.",
        source="cds",
        article_number="3",
        comma_number="1",
    )

    repository = get_default_container().resolve(GlossaryReadRepository)
    candidates = repository.candidates_for(
        "Cosa si intende per sosta di un veicolo?", embedding=None
    )

    terms = [c.term for c in candidates]
    assert terms.index("sosta dei veicoli") < terms.index("veicolo")
