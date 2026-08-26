from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.enums import LexemeField
from labeling.configs import LabelingConfig


def test_agents_dir_has_no_default_and_fails_without_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("AGENTS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # no configs/labeling.yaml, no .env

    with pytest.raises(ValidationError, match="(?i)agents_dir"):
        LabelingConfig()  # type: ignore[call-arg]


def test_agents_dir_is_read_from_the_agents_dir_environment_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTS_DIR", "some/where/agents")

    assert LabelingConfig().agents_dir == Path("some/where/agents")  # type: ignore[call-arg]


def test_the_epoch_fields_are_named_explicitly() -> None:
    assert (
        frozenset({"agents_dir", "candidate_variant", "dense_k", "text_k", "lexeme_fields"})
        == LabelingConfig.EPOCH_FIELDS
    )


def test_run_mechanics_are_not_epoch_fields() -> None:
    mechanics = {"shuffle_seed", "concurrency", "transport_retries", "retry_backoff_seconds"}

    assert LabelingConfig.EPOCH_FIELDS.isdisjoint(mechanics)


def test_every_epoch_field_exists_on_the_model() -> None:
    assert set(LabelingConfig.model_fields) >= LabelingConfig.EPOCH_FIELDS


def test_lexeme_fields_defaults_to_the_three_sanctioned_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTS_DIR", "configs/agents")

    assert set(LabelingConfig().lexeme_fields) == {  # type: ignore[call-arg]
        LexemeField.TOPIC,
        LexemeField.TEXT,
        LexemeField.IMAGE_DESCRIPTION,
    }


def test_defaults_match_the_spec_run_parameters() -> None:
    """The field defaults are unchanged by the move to `labeling.configs`.

    Moved from the deleted `guidami_ai_patente_ingestor.configs.LabelingConfig` test.
    """
    config = LabelingConfig()  # type: ignore[call-arg]

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
    """Moved verbatim: the validator is unchanged by the move (Step 3 of the brief)."""
    with pytest.raises(ValidationError):
        LabelingConfig(lexeme_fields=("topic", "embedding"))  # type: ignore[arg-type, call-arg]


def test_rejects_a_repeated_lexeme_field() -> None:
    with pytest.raises(ValidationError, match="must not repeat a field"):
        LabelingConfig(  # type: ignore[call-arg]
            lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT, LexemeField.TOPIC)
        )


def test_rejects_an_empty_lexeme_field_selection() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        LabelingConfig(lexeme_fields=())  # type: ignore[call-arg]


def test_rejects_a_non_positive_arm_depth() -> None:
    with pytest.raises(ValidationError):
        LabelingConfig(dense_k=0)  # type: ignore[call-arg]


def test_a_bare_epoch_field_env_var_does_not_override_the_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`env_prefix="LABELING_"` closes the silent-override channel D16 left open.

    Without an `env_prefix`, pydantic-settings' default env source matches field names
    case-insensitively with no prefix at all, so a bare `DENSE_K` in the process
    environment would silently win over the Python default — exactly the kind of
    unrecorded epoch-field override AD-22/AD-27 exist to prevent (D16's own rationale
    for keeping `configs/labeling.yaml` unreachable from `ingest --config`).
    """
    monkeypatch.chdir(tmp_path)  # no configs/labeling.yaml here
    monkeypatch.setenv("AGENTS_DIR", "configs/agents")
    monkeypatch.setenv("DENSE_K", "7")
    monkeypatch.setenv("CONCURRENCY", "99")

    config = LabelingConfig()  # type: ignore[call-arg]

    assert config.dense_k == 50
    assert config.concurrency == 8
