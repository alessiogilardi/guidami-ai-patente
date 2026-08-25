from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from labeling.configs import LabelingConfig

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _build_config(**kwargs) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
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


def test_default_project_root() -> None:
    config = _build_config()
    assert config.project_root == Path(".")


def test_default_table_names() -> None:
    config = _build_config()
    assert config.articles_table == "articles"
    assert config.article_commas_table == "article_commas"
    assert config.quiz_questions_table == "quiz_questions"
    assert config.quiz_images_table == "quiz_images"
    assert hasattr(config, "knowledge_chunks_table") is False


def test_default_quiz_embedding_variants() -> None:
    """FR-2/AD-7 (T-4): the six starting variants, in FR-2's listing order."""
    config = _build_config()
    assert config.quiz_embedding_variants == [
        "text",
        "topic_text",
        "search_queries",
        "combined",
        "combined_description",
        "image_description",
    ]


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


def test_exposes_the_golden_set_table_names_and_the_labeling_config() -> None:
    """Moved from the deleted `guidami_ai_patente_ingestor.configs.LabelingConfig` test."""
    config = _build_config()

    assert config.labeling_runs_table == "labeling_runs"
    assert config.quiz_labelings_table == "quiz_labelings"
    assert config.quiz_comma_labels_table == "quiz_comma_labels"
    assert isinstance(config.labeling, LabelingConfig)


def test_both_agents_dir_fields_are_defaultless() -> None:
    """D2: one defaultless env var is what makes divergence impossible, not one field."""
    assert IngestorConfig.model_fields["agents_dir"].is_required()
    assert LabelingConfig.model_fields["agents_dir"].is_required()


def test_both_agents_dir_fields_read_the_same_environment_variable() -> None:
    """D2: two fields, one source — so they cannot disagree within a deployment."""
    for model in (IngestorConfig, LabelingConfig):
        alias = model.model_fields["agents_dir"].validation_alias
        assert "AGENTS_DIR" in alias.choices  # type: ignore[union-attr]


def test_the_two_agents_dir_values_agree_when_resolved() -> None:
    """D11: the check `ingest status` reports on, pinned in-process too."""
    config = IngestorConfig.load()

    assert config.agents_dir == config.labeling.agents_dir


def test_the_base_yaml_no_longer_sets_agents_dir() -> None:
    raw = yaml.safe_load((_REPO_ROOT / "configs" / "ingestor_config.yaml").read_text("utf-8"))

    assert "agents_dir" not in raw


def test_the_base_yaml_does_not_duplicate_the_labeling_section() -> None:
    raw = yaml.safe_load((_REPO_ROOT / "configs" / "ingestor_config.yaml").read_text("utf-8"))

    assert "labeling" not in raw, (
        "a labeling: section here would move the duplication rather than remove it (AD-27)"
    )


def test_the_ingestor_embeds_the_shared_labeling_config() -> None:
    assert IngestorConfig.model_fields["labeling"].annotation is LabelingConfig


def test_a_nested_env_override_does_not_break_the_labeling_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D16: `LabelingConfig` is a `BaseSettings` nested in a `BaseSettings`.

    `IngestorConfig` sets `env_nested_delimiter="__"`, so `LABELING__DENSE_K` makes the
    parent's env source yield `{"labeling": {"dense_k": 10}}`. If pydantic routes that
    dict through `LabelingConfig.__init__` the nested sources still run and `agents_dir`
    resolves from `AGENTS_DIR`; if it validates the dict as a plain model instead,
    `agents_dir` is absent and EVERY `ingest` command breaks for anyone with a
    `LABELING__*` variable in their shell. Which one happens is pydantic-settings
    behaviour, so it is pinned rather than assumed.

    If this fails: give `LabelingConfig` its own `env_prefix` so the parent's nested
    delimiter cannot reach into it, in this same commit.
    """
    monkeypatch.setenv("LABELING__DENSE_K", "10")

    config = IngestorConfig.load()

    assert config.labeling.dense_k == 10
    # Compared against the sibling field (both single-sourced from AGENTS_DIR, per D2)
    # rather than a hardcoded literal: the session fixture resolves AGENTS_DIR to an
    # absolute path, so what matters here is that agents_dir did not come back
    # empty/defaulted by the nested-settings routing, not its literal value.
    assert config.labeling.agents_dir == config.agents_dir
