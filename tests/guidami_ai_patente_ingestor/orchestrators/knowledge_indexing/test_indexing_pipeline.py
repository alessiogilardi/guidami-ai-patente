from pathlib import Path
from unittest.mock import Mock, call

from commons.clients import EmbeddingClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipeline
from guidami_ai_patente_ingestor.repositories import (
    ArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def _build_config(embedding_batch_size: int) -> IngestorConfig:
    return IngestorConfig(
        cds_cleaned_path=FIXTURES_DIR / "cds_sample.json",
        cap_cleaned_path=FIXTURES_DIR / "cap_sample.json",
        embedding_batch_size=embedding_batch_size,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def _expected_chunks() -> list:
    repository = ArticleRepository()
    chunker = ArticleChunker()
    cds = [
        chunk
        for article in repository.load(FIXTURES_DIR / "cds_sample.json")
        for chunk in chunker.chunk(article, "cds")
    ]
    cap = [
        chunk
        for article in repository.load(FIXTURES_DIR / "cap_sample.json")
        for chunk in chunker.chunk(article, "cap")
    ]
    return cds + cap


def test_run_assigns_embeddings_in_batches_and_reloads_knowledge_chunks() -> None:
    expected_chunks = _expected_chunks()
    batch_size = 2

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.side_effect = lambda texts: [[float(len(t))] for t in texts]

    knowledge_chunk_store_repository = Mock(spec=KnowledgeChunkStoreRepository)

    pipeline = IndexingPipeline(
        article_repository=ArticleRepository(),
        article_chunker=ArticleChunker(),
        embedding_client=embedding_client,
        knowledge_chunk_store_repository=knowledge_chunk_store_repository,
        config=_build_config(batch_size),
    )

    pipeline.run()

    assert knowledge_chunk_store_repository.method_calls[0] == call.truncate()
    assert knowledge_chunk_store_repository.method_calls[1][0] == "bulk_insert"

    inserted_chunks = knowledge_chunk_store_repository.bulk_insert.call_args.args[0]
    assert len(inserted_chunks) == len(expected_chunks)
    assert all(chunk.embedding == [float(len(chunk.chunk_text))] for chunk in inserted_chunks)

    call_sizes = [len(c.args[0]) for c in embedding_client.embed_passages.call_args_list]
    assert call_sizes == [
        min(batch_size, len(expected_chunks) - start)
        for start in range(0, len(expected_chunks), batch_size)
    ]


def test_run_loads_both_sources_before_chunking() -> None:
    config = _build_config(embedding_batch_size=64)

    article_repository = Mock(spec=ArticleRepository)
    cds_article, cap_article = Mock(), Mock()
    article_repository.load.side_effect = lambda path: (
        [cds_article] if path == config.cds_cleaned_path else [cap_article]
    )

    article_chunker = Mock(spec=ArticleChunker)
    article_chunker.chunk.return_value = []

    manager = Mock()
    manager.attach_mock(article_repository, "repository")
    manager.attach_mock(article_chunker, "chunker")

    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_passages.return_value = []
    knowledge_chunk_store_repository = Mock(spec=KnowledgeChunkStoreRepository)

    pipeline = IndexingPipeline(
        article_repository=article_repository,
        article_chunker=article_chunker,
        embedding_client=embedding_client,
        knowledge_chunk_store_repository=knowledge_chunk_store_repository,
        config=config,
    )

    pipeline.run()

    load_calls = [c.args[0] for c in article_repository.load.call_args_list]
    assert load_calls == [config.cds_cleaned_path, config.cap_cleaned_path]

    assert article_chunker.chunk.call_args_list == [
        call(cds_article, "cds"),
        call(cap_article, "cap"),
    ]

    step_names = [c[0] for c in manager.mock_calls]
    load_indices = [i for i, name in enumerate(step_names) if name == "repository.load"]
    chunk_indices = [i for i, name in enumerate(step_names) if name == "chunker.chunk"]
    assert len(load_indices) == 2
    assert max(load_indices) < min(chunk_indices)
