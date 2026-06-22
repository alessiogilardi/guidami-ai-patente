"""Test per build_knowledge_indexing_flow (flow factory SP03)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from commons.clients import EmbeddingClient, PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.flowstep import Flow
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import build_knowledge_indexing_flow
from guidami_ai_patente_ingestor.services import LayerResolver

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _base_config() -> IngestorConfig:
    return IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def _make_layer_resolver(tmp_path: Path) -> LayerResolver:
    return LayerResolver(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={
            "cds": SourceConfig(dir="cds", file="articles.json"),
            "cap": SourceConfig(dir="cap", file="articles.json"),
        },
    )


def _make_embedding_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    client.embed_passages.side_effect = lambda texts: [[float(len(t))] * 1536 for t in texts]
    return client


def _make_postgres_client() -> PostgresClient:
    return MagicMock(spec=PostgresClient)


# ---------------------------------------------------------------------------
# Unit tests — no filesystem, no DB
# ---------------------------------------------------------------------------


def test_build_returns_flow_instance() -> None:
    config = _base_config()
    embedding_client = _make_embedding_client()
    postgres_client = _make_postgres_client()
    resolver = MagicMock(spec=LayerResolver)

    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=embedding_client,
        postgres_client=postgres_client,
    )

    assert isinstance(flow, Flow)


def test_flow_name_is_knowledge_indexing() -> None:
    config = _base_config()
    embedding_client = _make_embedding_client()
    postgres_client = _make_postgres_client()
    resolver = MagicMock(spec=LayerResolver)

    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=embedding_client,
        postgres_client=postgres_client,
    )

    assert flow.name == "knowledge_indexing"


def test_flow_required_input_keys_is_empty_set() -> None:
    """Il flow non richiede chiavi esterne: LoadEnrichedArticlesStep parte da zero."""
    from commons.flowstep import FlowValidator

    config = _base_config()
    embedding_client = _make_embedding_client()
    postgres_client = _make_postgres_client()
    resolver = MagicMock(spec=LayerResolver)

    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=embedding_client,
        postgres_client=postgres_client,
    )

    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_build_with_validate_true_does_not_raise() -> None:
    """validate=True non solleva (il WARNING su CHUNKS è benigno)."""
    config = _base_config()
    embedding_client = _make_embedding_client()
    postgres_client = _make_postgres_client()
    resolver = MagicMock(spec=LayerResolver)

    # deve completare senza eccezioni
    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=embedding_client,
        postgres_client=postgres_client,
        validate=True,
    )

    assert isinstance(flow, Flow)


# ---------------------------------------------------------------------------
# Integration test — richiede Postgres e file su disco
# ---------------------------------------------------------------------------


def _make_enriched_article(number: str, repealed: bool = False) -> EnrichedArticle:
    return EnrichedArticle(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo articolo {number}.",
        paragraphs=[f"Comma 1 articolo {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        contexts={},
    )


def _write_enriched(path: Path, articles: list[EnrichedArticle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([a.model_dump() for a in articles], ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.integration
def test_flow_run_stores_all_chunks_including_repealed(tmp_path: Path) -> None:
    """Flow completo su Postgres.

    - tutti i chunk (repealed inclusi) vengono inseriti in knowledge_chunks;
    - i chunk repealed hanno embedding IS NULL;
    - i chunk non-repealed hanno il vettore valorizzato.
    """
    from psycopg import sql

    from commons.clients import PostgresClient
    from commons.configs import PostgresConnectionConfig

    db_config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    pg_client = PostgresClient(db_config)

    resolver = LayerResolver(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={
            "cds": SourceConfig(dir="cds", file="articles.json"),
            "cap": SourceConfig(dir="cap", file="articles.json"),
        },
    )

    cds_articles = [
        _make_enriched_article("1", repealed=False),
        _make_enriched_article("2", repealed=True),
    ]
    cap_articles = [
        _make_enriched_article("3", repealed=False),
    ]
    _write_enriched(resolver.path("enriched", "cds"), cds_articles)
    _write_enriched(resolver.path("enriched", "cap"), cap_articles)

    config = IngestorConfig(
        embedding_batch_size=4,
        postgres=db_config,
    )

    embedding_client = _make_embedding_client()

    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=embedding_client,
        postgres_client=pg_client,
    )
    flow.run()

    # Verifica su DB
    total: int = pg_client.fetch(sql.SQL("SELECT COUNT(*) FROM knowledge_chunks"))[0][0]
    repealed_null: int = pg_client.fetch(
        sql.SQL(
            "SELECT COUNT(*) FROM knowledge_chunks "
            "WHERE embedding IS NULL AND is_repealed = TRUE"
        )
    )[0][0]
    non_repealed_embedded: int = pg_client.fetch(
        sql.SQL(
            "SELECT COUNT(*) FROM knowledge_chunks "
            "WHERE embedding IS NOT NULL AND is_repealed = FALSE"
        )
    )[0][0]
    pg_client.close()

    assert total > 0, "devono esserci righe in knowledge_chunks"
    assert repealed_null > 0, "i chunk repealed devono avere embedding IS NULL"
    assert non_repealed_embedded > 0, "i chunk non-repealed devono avere embedding valorizzato"
    assert total == repealed_null + non_repealed_embedded, (
        "ogni chunk è o repealed-null o non-repealed-embedded"
    )
