import pytest
from pydantic import SecretStr, ValidationError

from commons.configs import PostgresConnectionConfig
from domain.enums import LexemeField
from guidami_ai_patente_ingestor.configs import IngestorConfig, LabelingConfig


def _build_ingestor_config(**kwargs: object) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
        ),
        **kwargs,
    )


def test_defaults_match_the_spec_run_parameters() -> None:
    config = LabelingConfig()

    assert config.candidate_variant == "topic_text"
    assert config.dense_k == 50
    assert config.text_k == 50
    assert config.concurrency == 8
    assert config.transport_retries == 3
    assert config.retry_backoff_seconds == 2.0
    assert config.lexeme_fields == (
        LexemeField.TOPIC,
        LexemeField.TEXT,
        LexemeField.IMAGE_DESCRIPTION,
    )


def test_rejects_an_unknown_lexeme_field() -> None:
    with pytest.raises(ValidationError):
        LabelingConfig(lexeme_fields=("topic", "embedding"))  # type: ignore[arg-type]


def test_rejects_a_repeated_lexeme_field() -> None:
    with pytest.raises(ValidationError, match="must not repeat a field"):
        LabelingConfig(lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT, LexemeField.TOPIC))


def test_rejects_an_empty_lexeme_field_selection() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        LabelingConfig(lexeme_fields=())


def test_rejects_a_non_positive_arm_depth() -> None:
    with pytest.raises(ValidationError):
        LabelingConfig(dense_k=0)


def test_ingestor_config_exposes_the_golden_set_table_names() -> None:
    config = _build_ingestor_config()

    assert config.labeling_runs_table == "labeling_runs"
    assert config.quiz_labelings_table == "quiz_labelings"
    assert config.quiz_comma_labels_table == "quiz_comma_labels"
    assert isinstance(config.labeling, LabelingConfig)
