"""AppConfig and LabelingConfig are two independent config roots (spec 0013, FR-1)."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from labeling.configs import LabelingConfig


def test_the_quiz_image_root_defaults_to_the_committed_directory() -> None:
    assert AppConfig.model_fields["quiz_images_dir"].default == Path("data/quiz-images")


def test_the_app_declares_no_labeling_field() -> None:
    assert "labeling" not in AppConfig.model_fields, (
        "FR-1: AppConfig and LabelingConfig are loaded and registered independently, "
        "not nested — a nested field would let the two configs be built from different "
        "sources by accident"
    )


def test_the_app_declares_no_epoch_field_of_its_own() -> None:
    own_fields = set(AppConfig.model_fields)

    # `agents_dir` is the one deliberate exception (D4, ADR 0020): AppConfig declares its
    # own copy to anchor the app's non-epoch agents, distinct from LabelingConfig.agents_dir
    # which anchors the epoch-controlled judge prompt. Both alias AGENTS_DIR, but they are
    # two independently-declared fields, not one shared epoch input.
    assert own_fields.isdisjoint(LabelingConfig.EPOCH_FIELDS - {"agents_dir"}), (
        "AD-27: every epoch input other than agents_dir reaches a consumer through an "
        "autowired LabelingConfig, never as a field declared here — a second declaration "
        "is a second place to get it wrong"
    )


def test_both_roots_resolve_the_same_comma_labeler_prompt(
    labeling_config: LabelingConfig,
) -> None:
    """AD-22's content-hash test — a spec constraint, not optional coverage."""
    ingestor = IngestorConfig.load()

    app_file = labeling_config.agents_dir / "comma_labeler.yaml"
    ingestor_file = ingestor.labeling.agents_dir / "comma_labeler.yaml"

    assert app_file.resolve() == ingestor_file.resolve()
    assert (
        hashlib.sha256(app_file.read_bytes()).hexdigest()
        == hashlib.sha256(ingestor_file.read_bytes()).hexdigest()
    )


def test_the_agents_dir_has_no_default(
    postgres_test_config: PostgresConnectionConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-22: a missing AGENTS_DIR is a loud ValidationError, never a silent fallback."""
    monkeypatch.delenv("AGENTS_DIR", raising=False)

    with pytest.raises(ValidationError):
        AppConfig(postgres=postgres_test_config, _env_file=None)  # pyright: ignore[reportCallIssue]


def test_the_quiz_images_table_and_deadline_have_defaults(app_config: AppConfig) -> None:
    assert app_config.quiz_images_table == "quiz_images"
    assert app_config.explanation_deadline_s > 0


def test_no_epoch_field_is_declared_on_the_root(app_config: AppConfig) -> None:
    """AD-27: the six epoch inputs live on LabelingConfig only."""
    declared = set(type(app_config).model_fields)

    assert declared.isdisjoint({"candidate_variant", "dense_k", "text_k", "lexeme_fields"})


def test_the_new_spec_0016_tables_have_defaults(app_config: AppConfig) -> None:
    assert app_config.users_table == "users"
    assert app_config.quiz_answers_table == "quiz_answers"
