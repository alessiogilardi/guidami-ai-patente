from pathlib import Path

import pytest
from pydantic import ValidationError

from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig


def _build_config() -> IngestorConfig:
    return IngestorConfig(
        vector_store=VectorStoreConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        )
    )


def test_default_paths_point_to_expected_source_files() -> None:
    config = _build_config()

    assert config.cds_parsed_path == Path("data/parsed/cds/codice_della_strada.json")
    assert config.cds_cleaned_path == Path("data/cleaned/cds/codice_della_strada.json")
    assert config.cap_parsed_path == Path("data/parsed/cap/codice_rca.json")
    assert config.cap_cleaned_path == Path("data/cleaned/cap/codice_rca.json")


def test_vector_store_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VECTOR_STORE__USER", raising=False)
    monkeypatch.delenv("VECTOR_STORE__PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        IngestorConfig(_env_file=None)


def test_config_is_frozen() -> None:
    config = _build_config()

    with pytest.raises(ValidationError):
        config.embedding_batch_size = 1
