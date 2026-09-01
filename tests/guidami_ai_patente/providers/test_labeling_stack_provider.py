"""The API resolves the same configuration epoch the batch harness writes (AD-22, AD-27)."""

from pywire import get_default_container

from guidami_ai_patente.providers import LabelingStackProvider
from labeling.configs import LabelingConfig
from labeling.mappers import LabelingEpochMapper
from labeling.utils import prompt_version


def test_the_epoch_matches_the_one_the_mapper_derives(
    labeling_config: LabelingConfig, api_client: object
) -> None:
    provider = get_default_container().resolve(LabelingStackProvider)

    assert provider.epoch == LabelingEpochMapper.from_config_to_epoch(
        labeling_config, provider.agent_config
    )


def test_the_prompt_version_hashes_the_loaded_prompt(api_client: object) -> None:
    provider = get_default_container().resolve(LabelingStackProvider)

    assert provider.epoch.prompt_version == prompt_version(
        provider.agent_config.system, provider.agent_config.user
    )


def test_the_lexeme_fields_are_canonically_sorted(api_client: object) -> None:
    provider = get_default_container().resolve(LabelingStackProvider)

    assert list(provider.epoch.lexeme_fields) == sorted(provider.epoch.lexeme_fields)


def test_the_arm_depths_come_from_the_shared_config(
    labeling_config: LabelingConfig, api_client: object
) -> None:
    provider = get_default_container().resolve(LabelingStackProvider)

    assert (provider.epoch.dense_k, provider.epoch.text_k) == (
        labeling_config.dense_k,
        labeling_config.text_k,
    )
