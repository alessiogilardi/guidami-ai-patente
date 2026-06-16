from pathlib import Path
from unittest.mock import Mock

import pytest

from commons.clients import EmbeddingClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import (
    IndexingPipeline,
    IndexingPipelineBuilder,
)
from guidami_ai_patente_ingestor.repositories import (
    ArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"

MODULE = "guidami_ai_patente_ingestor.orchestrators.knowledge_indexing.indexing_pipeline_builder"


def _build_config(
    cds_cleaned_path: Path = FIXTURES_DIR / "cds_sample.json",
    cap_cleaned_path: Path = FIXTURES_DIR / "cap_sample.json",
) -> IngestorConfig:
    return IngestorConfig(
        cds_cleaned_path=cds_cleaned_path,
        cap_cleaned_path=cap_cleaned_path,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def test_build_raises_before_instantiating_clients_when_source_path_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.LiteLLMEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )
    monkeypatch.setattr(
        f"{MODULE}.PostgresClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )

    cds_cleaned_path = tmp_path / "missing-cds.json"
    cap_cleaned_path = tmp_path / "missing-cap.json"
    config = _build_config(cds_cleaned_path=cds_cleaned_path, cap_cleaned_path=cap_cleaned_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        IndexingPipelineBuilder(config).build()

    assert str(cds_cleaned_path) in str(exc_info.value)
    assert str(cap_cleaned_path) in str(exc_info.value)


def test_build_uses_overridden_dependencies_instead_of_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.LiteLLMEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )
    monkeypatch.setattr(
        f"{MODULE}.PostgresClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )

    article_repository = Mock(spec=ArticleRepository)
    article_chunker = Mock(spec=ArticleChunker)
    embedding_client = Mock(spec=EmbeddingClient)
    knowledge_chunk_store_repository = Mock(spec=KnowledgeChunkStoreRepository)

    pipeline = (
        IndexingPipelineBuilder(_build_config())
        .with_article_repository(article_repository)
        .with_article_chunker(article_chunker)
        .with_embedding_client(embedding_client)
        .with_knowledge_chunk_store_repository(knowledge_chunk_store_repository)
        .build()
    )

    assert isinstance(pipeline, IndexingPipeline)
    assert pipeline._article_repository is article_repository
    assert pipeline._article_chunker is article_chunker
    assert pipeline._embedding_client is embedding_client
    assert pipeline._knowledge_chunk_store_repository is knowledge_chunk_store_repository
