from pathlib import Path

import pytest
from pydantic import ValidationError

from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig


def _build_config() -> IngestorConfig:
    return IngestorConfig(vector_store=VectorStoreConfig(database_url="postgresql://unused"))


def test_default_paths_point_to_expected_source_files() -> None:
    config = _build_config()

    assert config.cds_path == Path("data/processed/cds/codice_della_strada.json")
    assert config.cap_path == Path("data/processed/cap/codice_rca.json")


def test_vector_store_is_required() -> None:
    with pytest.raises(ValidationError):
        IngestorConfig()


def test_config_is_frozen() -> None:
    config = _build_config()

    with pytest.raises(ValidationError):
        config.embedding_batch_size = 1
