from pathlib import Path

import pytest

from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipelineBuilder


def test_build_raises_before_instantiating_clients_when_source_path_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = (
        "guidami_ai_patente_ingestor.orchestrators.knowledge_indexing.indexing_pipeline_builder"
    )
    monkeypatch.setattr(
        f"{module}.E5SmallEmbeddingClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )
    monkeypatch.setattr(
        f"{module}.VectorStoreClient",
        lambda config: pytest.fail("non deve essere istanziato se i path sorgente sono invalidi"),
    )

    config = IngestorConfig(
        cds_path=tmp_path / "missing-cds.json",
        cap_path=tmp_path / "missing-cap.json",
        vector_store=VectorStoreConfig(database_url="postgresql://unused"),
    )

    with pytest.raises(FileNotFoundError):
        IndexingPipelineBuilder(config).build()
