from pathlib import Path
from unittest.mock import Mock

import pytest

from commons.clients import EmbeddingClient, VectorStoreClient
from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import (
    IndexingPipeline,
    IndexingPipelineBuilder,
)
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"

MODULE = "guidami_ai_patente_ingestor.orchestrators.knowledge_indexing.indexing_pipeline_builder"


def _build_config(
    cds_path: Path = FIXTURES_DIR / "cds_sample.json",
    cap_path: Path = FIXTURES_DIR / "cap_sample.json",
) -> IngestorConfig:
    return IngestorConfig(
        cds_path=cds_path,
        cap_path=cap_path,
        vector_store=VectorStoreConfig(database_url="postgresql://unused"),
    )


def test_build_raises_before_instantiating_clients_when_source_path_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.E5SmallEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )
    monkeypatch.setattr(
        f"{MODULE}.VectorStoreClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )

    cds_path = tmp_path / "missing-cds.json"
    cap_path = tmp_path / "missing-cap.json"
    config = _build_config(cds_path=cds_path, cap_path=cap_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        IndexingPipelineBuilder(config).build()

    assert str(cds_path) in str(exc_info.value)
    assert str(cap_path) in str(exc_info.value)


def test_build_uses_overridden_dependencies_instead_of_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        f"{MODULE}.E5SmallEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )
    monkeypatch.setattr(
        f"{MODULE}.VectorStoreClient",
        lambda config: pytest.fail("non deve essere istanziato se sovrascritto con with_*"),
    )

    article_loader = Mock(spec=ArticleLoader)
    article_chunker = Mock(spec=ArticleChunker)
    embedding_client = Mock(spec=EmbeddingClient)
    vector_store_client = Mock(spec=VectorStoreClient)

    pipeline = (
        IndexingPipelineBuilder(_build_config())
        .with_article_loader(article_loader)
        .with_article_chunker(article_chunker)
        .with_embedding_client(embedding_client)
        .with_vector_store_client(vector_store_client)
        .build()
    )

    assert isinstance(pipeline, IndexingPipeline)
    assert pipeline._article_loader is article_loader
    assert pipeline._article_chunker is article_chunker
    assert pipeline._embedding_client is embedding_client
    assert pipeline._vector_store_client is vector_store_client
