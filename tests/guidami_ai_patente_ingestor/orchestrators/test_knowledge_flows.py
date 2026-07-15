"""Tests for build_knowledge_indexing_flow (flow factory SP03, per-source)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flowstep import Flow

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel
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
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
    )
    assert isinstance(flow, Flow)


def test_flow_name_is_knowledge_indexing() -> None:
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cap",
    )
    assert flow.name == "knowledge_indexing"


def test_flow_required_input_keys_is_empty_set() -> None:
    """The flow requires no external keys: LoadJsonStep starts from scratch."""
    from flowstep import FlowValidator

    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
    )

    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_build_with_validate_true_does_not_raise() -> None:
    """validate=True does not raise (the WARNING on CHUNKS is benign)."""
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
        validate=True,
    )
    assert isinstance(flow, Flow)


def test_build_with_unknown_source_raises_value_error() -> None:
    """A source outside the configured catalog is an explicit error."""
    with pytest.raises(ValueError, match="Unknown source"):
        build_knowledge_indexing_flow(
            config=_base_config(),
            layer_resolver=MagicMock(spec=LayerResolver),
            embedding_client=_make_embedding_client(),
            postgres_client=_make_postgres_client(),
            source="quiz",
        )


# ---------------------------------------------------------------------------
# Integration test — requires Postgres and files on disk
# ---------------------------------------------------------------------------


def _make_enriched_article(number: str, repealed: bool = False) -> EnrichedArticleModel:
    return EnrichedArticleModel(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo articolo {number}.",
        paragraphs=[f"Comma 1 articolo {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        contexts={},
    )


def _write_enriched(path: Path, articles: list[EnrichedArticleModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([a.model_dump() for a in articles], ensure_ascii=False), encoding="utf-8"
    )


def _integration_resolver(tmp_path: Path) -> LayerResolver:
    return LayerResolver(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={
            "cds": SourceConfig(dir="cds", file="articles.json"),
            "cap": SourceConfig(dir="cap", file="articles.json"),
        },
    )


def _count(pg_client: PostgresClient, where: str) -> int:
    from psycopg import sql

    query = sql.SQL("SELECT COUNT(*) FROM knowledge_chunks WHERE " + where)  # noqa: S608
    return pg_client.fetch(query)[0][0]


@pytest.mark.integration
def test_cap_run_does_not_overwrite_cds_run(tmp_path: Path) -> None:
    """The key point of per-source: a run on 'cap' does not delete 'cds' chunks.

    Also: repealed chunks are stored with embedding IS NULL, non-repealed ones are embedded.
    """
    db_config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    pg_client = PostgresClient(db_config)
    pg_client.truncate("knowledge_chunks")

    resolver = _integration_resolver(tmp_path)
    cds_articles = [
        _make_enriched_article("1", repealed=False),
        _make_enriched_article("2", repealed=True),
    ]
    cap_articles = [_make_enriched_article("3", repealed=False)]
    _write_enriched(resolver.path("enriched", "cds"), cds_articles)
    _write_enriched(resolver.path("enriched", "cap"), cap_articles)

    config = IngestorConfig(embedding_batch_size=4, postgres=db_config, project_root=tmp_path)
    embedding_client = _make_embedding_client()

    def _run(source: str) -> None:
        build_knowledge_indexing_flow(
            config=config,
            layer_resolver=resolver,
            embedding_client=embedding_client,
            postgres_client=pg_client,
            source=source,
        ).run()

    # Run 1: cds
    _run("cds")
    cds_after_run1 = _count(pg_client, "source = 'cds'")
    assert cds_after_run1 > 0, "the cds run must insert chunks"

    # Run 2: cap — must NOT touch the cds rows
    _run("cap")

    cds_count = _count(pg_client, "source = 'cds'")
    cap_count = _count(pg_client, "source = 'cap'")
    repealed_null = _count(pg_client, "embedding IS NULL AND is_repealed = TRUE")
    non_repealed_embedded = _count(pg_client, "embedding IS NOT NULL AND is_repealed = FALSE")
    pg_client.close()

    assert cds_count == cds_after_run1, "the cap run must not delete the cds chunks"
    assert cap_count > 0, "the cap run must insert its own chunks"
    assert repealed_null > 0, "repealed chunks must have embedding IS NULL"
    assert non_repealed_embedded > 0, "non-repealed chunks must have a populated embedding"


@pytest.mark.integration
def test_rerunning_same_source_is_full_reload(tmp_path: Path) -> None:
    """Re-running the same source is a per-source full-reload: the count stays stable."""
    db_config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    pg_client = PostgresClient(db_config)
    pg_client.truncate("knowledge_chunks")

    resolver = _integration_resolver(tmp_path)
    _write_enriched(
        resolver.path("enriched", "cds"),
        [_make_enriched_article("1"), _make_enriched_article("2")],
    )

    config = IngestorConfig(embedding_batch_size=4, postgres=db_config, project_root=tmp_path)
    embedding_client = _make_embedding_client()

    def _run() -> None:
        build_knowledge_indexing_flow(
            config=config,
            layer_resolver=resolver,
            embedding_client=embedding_client,
            postgres_client=pg_client,
            source="cds",
        ).run()

    _run()
    count_after_first = _count(pg_client, "source = 'cds'")
    _run()
    count_after_second = _count(pg_client, "source = 'cds'")
    pg_client.close()

    assert count_after_first > 0
    assert count_after_second == count_after_first, "re-running must not duplicate the chunks"
