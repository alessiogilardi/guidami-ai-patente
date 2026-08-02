from pathlib import Path

import pytest
from pydantic import ValidationError

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig


def _build_config(**kwargs) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        **kwargs,
    )


def test_default_layers_contain_parsed_cleaned_enriched() -> None:
    config = _build_config()
    assert config.layers["parsed"] == "data/parsed"
    assert config.layers["cleaned"] == "data/cleaned"
    assert config.layers["enriched"] == "data/enriched"


def test_default_sources_contain_cds_cap_quiz() -> None:
    config = _build_config()
    assert "cds" in config.sources
    assert "cap" in config.sources
    assert "quiz" in config.sources
    assert config.sources["cds"].file == "codice_della_strada.json"
    assert config.sources["quiz"].dir == "quiz-patente-ab"


def test_default_sources_and_pipelines_include_reg() -> None:
    config = _build_config()

    assert "reg" in config.sources
    assert config.sources["reg"].file == "regolamento_attuazione.json"
    assert "reg" in config.knowledge_preparation.sources
    assert "reg" in config.knowledge_indexing.sources


def test_default_pipeline_selectors() -> None:
    """Knowledge layer defaults are covered separately by `test_knowledge_layers_are_cleaned`."""
    config = _build_config()
    assert config.knowledge_preparation.input_layer == "parsed"
    assert config.quiz_preparation.input_layer == "parsed"
    assert config.quiz_preparation.output_layer == "enriched"
    assert config.quiz_indexing.input_layer == "enriched"


def test_knowledge_layers_are_cleaned() -> None:
    """FR-16/AD-18 (T-13): no LLM enrichment step, pipeline moves parsed→cleaned directly."""
    config = _build_config()
    assert config.knowledge_preparation.output_layer == "cleaned"
    assert config.knowledge_indexing.input_layer == "cleaned"


def test_default_agents_dir() -> None:
    config = _build_config()
    assert config.agents_dir == Path("configs/agents")


def test_default_project_root() -> None:
    config = _build_config()
    assert config.project_root == Path(".")


def test_default_table_names() -> None:
    config = _build_config()
    assert config.articles_table == "articles"
    assert config.article_commas_table == "article_commas"
    assert config.quiz_questions_table == "quiz_questions"
    assert hasattr(config, "knowledge_chunks_table") is False


def test_default_rca_ranges() -> None:
    config = _build_config()
    assert config.rca_ranges == ["118-165", "278-300"]


def test_postgres_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES__USER", raising=False)
    monkeypatch.delenv("POSTGRES__PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        IngestorConfig(_env_file=None)


def test_config_is_frozen() -> None:
    config = _build_config()

    with pytest.raises(ValidationError):
        config.embedding_batch_size = 1
