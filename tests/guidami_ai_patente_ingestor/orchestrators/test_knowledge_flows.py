"""Tests for build_knowledge_indexing_flow (flow factory SP03, per-source)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from unittest.mock import MagicMock

import pytest
from flowstep import Flow

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.models.knowledge import CleanedArticleModel, ParsedComma
from guidami_ai_patente_ingestor.orchestrators import build_knowledge_indexing_flow
from guidami_ai_patente_ingestor.services import LayerResolver

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter

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
    """Stubbed client: `execute_many_returning` fabricates sequential ids per row.

    Enough for tests that run the flow against a mocked (not real) DB: the
    store step only needs *some* distinct id per inserted article to resolve
    each comma's `article_id`, not real persistence.
    """
    client = MagicMock(spec=PostgresClient)
    client.execute_many_returning.side_effect = lambda query, params_seq: [
        (i,) for i in range(1, len(params_seq) + 1)
    ]
    return client


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


def test_knowledge_flows_module_has_no_enrichment_factory() -> None:
    """FR-16/AD-18 (T-13): context enrichment is removed; the factory no longer exists."""
    from guidami_ai_patente_ingestor.orchestrators import knowledge_flows

    assert not hasattr(knowledge_flows, "build_knowledge_enrichment_flow")


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


def test_build_knowledge_indexing_flow_accepts_reg_source() -> None:
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="reg",
    )
    assert isinstance(flow, Flow)


def test_build_knowledge_indexing_flow_reads_cleaned_layer() -> None:
    """T-14: the flow's first step reads CleanedArticleModel from the 'cleaned' layer."""
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
    )

    load_step = flow.get_steps()[0]
    assert load_step._input_layer == "cleaned"  # type: ignore[attr-defined]  # noqa: SLF001
    assert (
        load_step._repository._model_class is CleanedArticleModel  # type: ignore[attr-defined]  # noqa: SLF001
    )


def test_build_knowledge_indexing_flow_has_five_steps_no_chunker() -> None:
    """T-14: the new comma-based step chain replaces the old chunk-based one."""
    flow = build_knowledge_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
    )

    step_names = [step.name for step in flow.get_steps()]
    assert step_names == [
        "load_cleaned_articles",
        "map_to_article_entities",
        "expand_to_embeddable_commas",
        "embed_commas",
        "store_articles_and_commas",
    ]
    assert "chunk_articles" not in step_names


def test_indexing_flow_reports_step_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    """Runs on a tmp_path filesystem with a stubbed postgres_client: no real DB access."""
    resolver = _cleaned_resolver(tmp_path)
    _write_cleaned(resolver.dir("cleaned", "cds"), [_make_cleaned_article("1", "cds")])
    config = IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        project_root=tmp_path,
    )

    build_knowledge_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        source="cds",
        progress=progress_recorder,
    ).run()

    begin_steps = [call for call in progress_recorder.calls if call[0] == "begin_step"]
    end_steps = [call for call in progress_recorder.calls if call[0] == "end_step"]
    assert len(begin_steps) == 5
    assert len(end_steps) == 5
    assert [args[1] for _, args in begin_steps] == [1, 2, 3, 4, 5]
    assert all(args[2] == 5 for _, args in begin_steps)


# ---------------------------------------------------------------------------
# Integration test — requires Postgres and files on disk
# ---------------------------------------------------------------------------


def _make_cleaned_article(
    number: str,
    source: Literal["cds", "cap"],
    repealed: bool = False,
    comma_text: str | None = None,
) -> CleanedArticleModel:
    return CleanedArticleModel(
        number=number,
        title=f"Articolo {number}",
        commas=[ParsedComma(number="1", text=comma_text or f"Comma 1 articolo {number}.")],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        source=source,
    )


def _write_cleaned(directory: Path, articles: list[CleanedArticleModel]) -> None:
    """Writes one JSON file per article, named by `element_id` (per-element layer)."""
    directory.mkdir(parents=True, exist_ok=True)
    for article in articles:
        file_path = directory / f"{element_id(article.source, article.number)}.json"
        file_path.write_text(
            json.dumps(article.model_dump(), ensure_ascii=False), encoding="utf-8"
        )


def _cleaned_resolver(tmp_path: Path) -> LayerResolver:
    return LayerResolver(
        layers={"cleaned": str(tmp_path / "cleaned")},
        sources={
            "cds": SourceConfig(dir="cds", file="articles.json"),
            "cap": SourceConfig(dir="cap", file="articles.json"),
        },
    )


def _count(pg_client: PostgresClient, table: str, where: str) -> int:
    from psycopg import sql

    query = sql.SQL(f"SELECT COUNT(*) FROM {table} WHERE " + where)  # noqa: S608
    return pg_client.fetch(query)[0][0]


@pytest.mark.integration
def test_cap_run_does_not_overwrite_cds_run(tmp_path: Path) -> None:
    """The key point of per-source: a run on 'cap' does not delete 'cds' articles/commas.

    Also: repealed comma embeddings stay NULL, non-repealed ones are embedded.
    """
    db_config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    pg_client = PostgresClient(db_config)
    pg_client.truncate("article_commas", "articles")

    resolver = _cleaned_resolver(tmp_path)
    cds_articles = [
        _make_cleaned_article("1", "cds", repealed=False),
        _make_cleaned_article("2", "cds", repealed=True),
    ]
    cap_articles = [_make_cleaned_article("3", "cap", repealed=False)]
    _write_cleaned(resolver.dir("cleaned", "cds"), cds_articles)
    _write_cleaned(resolver.dir("cleaned", "cap"), cap_articles)

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
    cds_after_run1 = _count(pg_client, "articles", "source = 'cds'")
    assert cds_after_run1 > 0, "the cds run must insert articles"

    # Run 2: cap — must NOT touch the cds rows
    _run("cap")

    cds_count = _count(pg_client, "articles", "source = 'cds'")
    cap_count = _count(pg_client, "articles", "source = 'cap'")
    repealed_null = _count(pg_client, "article_commas", "embedding IS NULL AND is_repealed = TRUE")
    non_repealed_embedded = _count(
        pg_client, "article_commas", "embedding IS NOT NULL AND is_repealed = FALSE"
    )
    pg_client.close()

    assert cds_count == cds_after_run1, "the cap run must not delete the cds articles"
    assert cap_count > 0, "the cap run must insert its own articles"
    assert repealed_null > 0, "repealed comma embeddings must stay NULL"
    assert non_repealed_embedded > 0, "non-repealed comma embeddings must be populated"


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
    pg_client.truncate("article_commas", "articles")

    resolver = _cleaned_resolver(tmp_path)
    _write_cleaned(
        resolver.dir("cleaned", "cds"),
        [_make_cleaned_article("1", "cds"), _make_cleaned_article("2", "cds")],
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
    count_after_first = _count(pg_client, "articles", "source = 'cds'")
    _run()
    count_after_second = _count(pg_client, "articles", "source = 'cds'")
    pg_client.close()

    assert count_after_first > 0
    assert count_after_second == count_after_first, "re-running must not duplicate the articles"
