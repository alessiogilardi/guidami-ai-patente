"""AppConfig and LabelingConfig are two independent config roots (spec 0013, FR-1)."""

import hashlib
from pathlib import Path

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

    assert own_fields.isdisjoint(LabelingConfig.EPOCH_FIELDS), (
        "AD-27: every epoch input reaches a consumer through an autowired LabelingConfig, "
        "never as a field declared here — a second declaration is a second place to get "
        "it wrong"
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
