from pathlib import Path
from unittest.mock import Mock, call

from commons.clients import EmbeddingClient, VectorStoreClient
from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipeline
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def _build_config(embedding_batch_size: int) -> IngestorConfig:
    return IngestorConfig(
        cds_path=FIXTURES_DIR / "cds_sample.json",
        cap_path=FIXTURES_DIR / "cap_sample.json",
        embedding_batch_size=embedding_batch_size,
        vector_store=VectorStoreConfig(database_url="postgresql://unused"),
    )


def _expected_chunks() -> list:
    loader = ArticleLoader()
    chunker = ArticleChunker()
    cds = [
        chunk
        for article in loader.load(FIXTURES_DIR / "cds_sample.json")
        for chunk in chunker.chunk(article, "cds")
    ]
    cap = [
        chunk
        for article in loader.load(FIXTURES_DIR / "cap_sample.json")
        for chunk in chunker.chunk(article, "cap")
    ]
    return cds + cap


def test_run_assigns_embeddings_in_batches_and_reloads_vector_store() -> None:
    expected_chunks = _expected_chunks()
    batch_size = 2

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.side_effect = lambda texts: [[float(len(t))] for t in texts]

    vector_store_client = Mock(spec=VectorStoreClient)

    pipeline = IndexingPipeline(
        article_loader=ArticleLoader(),
        article_chunker=ArticleChunker(),
        embedding_client=embedding_client,
        vector_store_client=vector_store_client,
        config=_build_config(batch_size),
    )

    pipeline.run()

    assert vector_store_client.method_calls[0] == call.truncate()
    assert vector_store_client.method_calls[1][0] == "bulk_insert"

    inserted_chunks = vector_store_client.bulk_insert.call_args.args[0]
    assert len(inserted_chunks) == len(expected_chunks)
    assert all(chunk.embedding == [float(len(chunk.chunk_text))] for chunk in inserted_chunks)

    call_sizes = [len(c.args[0]) for c in embedding_client.embed_passages.call_args_list]
    assert call_sizes == [
        min(batch_size, len(expected_chunks) - start)
        for start in range(0, len(expected_chunks), batch_size)
    ]


def test_run_loads_both_sources_before_chunking() -> None:
    config = _build_config(embedding_batch_size=64)

    article_loader = Mock(spec=ArticleLoader)
    cds_article, cap_article = Mock(), Mock()
    article_loader.load.side_effect = lambda path: (
        [cds_article] if path == config.cds_path else [cap_article]
    )

    article_chunker = Mock(spec=ArticleChunker)
    article_chunker.chunk.return_value = []

    manager = Mock()
    manager.attach_mock(article_loader, "loader")
    manager.attach_mock(article_chunker, "chunker")

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.return_value = []
    vector_store_client = Mock(spec=VectorStoreClient)

    pipeline = IndexingPipeline(
        article_loader=article_loader,
        article_chunker=article_chunker,
        embedding_client=embedding_client,
        vector_store_client=vector_store_client,
        config=config,
    )

    pipeline.run()

    load_calls = [c.args[0] for c in article_loader.load.call_args_list]
    assert load_calls == [config.cds_path, config.cap_path]

    assert article_chunker.chunk.call_args_list == [
        call(cds_article, "cds"),
        call(cap_article, "cap"),
    ]

    step_names = [c[0] for c in manager.mock_calls]
    load_indices = [i for i, name in enumerate(step_names) if name == "loader.load"]
    chunk_indices = [i for i, name in enumerate(step_names) if name == "chunker.chunk"]
    assert len(load_indices) == 2
    assert max(load_indices) < min(chunk_indices)
