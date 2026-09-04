"""AppConfig and LabelingConfig each reach the container as a single instance.

spec 0012, AD-16; spec 0013, FR-1.
"""

import pytest
from pywire import get_default_container
from pywire.exceptions import RegistrationError

from commons.ai.observability import ObservabilityConfig
from commons.configs import OpenRouterConfig
from guidami_ai_patente.api.app import create_app
from guidami_ai_patente.configs import AppConfig
from labeling.configs import LabelingConfig


def test_the_container_resolves_the_config_the_app_was_built_with(
    app_config: AppConfig, api_client: object
) -> None:
    assert get_default_container().resolve(AppConfig) is app_config


def test_the_container_resolves_the_labeling_config_the_app_was_built_with(
    labeling_config: LabelingConfig, api_client: object
) -> None:
    assert get_default_container().resolve(LabelingConfig) is labeling_config


def test_building_the_app_twice_with_the_same_config_is_not_an_error(
    app_config: AppConfig,
    labeling_config: LabelingConfig,
    open_router_config: OpenRouterConfig,
    observability_config: ObservabilityConfig,
    api_client: object,
) -> None:
    create_app(
        app_config,
        labeling_config,
        open_router_config=open_router_config,
        observability_config=observability_config,
    )

    assert get_default_container().resolve(AppConfig) is app_config
    assert get_default_container().resolve(LabelingConfig) is labeling_config


def test_building_the_app_with_a_second_config_raises(
    app_config: AppConfig,
    labeling_config: LabelingConfig,
    open_router_config: OpenRouterConfig,
    observability_config: ObservabilityConfig,
    api_client: object,
) -> None:
    other = app_config.model_copy(update={"port": 9999})

    with pytest.raises(RegistrationError, match="AppConfig"):
        create_app(
            other,
            labeling_config,
            open_router_config=open_router_config,
            observability_config=observability_config,
        )


def test_building_the_app_with_a_second_labeling_config_raises(
    app_config: AppConfig,
    labeling_config: LabelingConfig,
    open_router_config: OpenRouterConfig,
    observability_config: ObservabilityConfig,
    api_client: object,
) -> None:
    other = labeling_config.model_copy(update={"shuffle_seed": labeling_config.shuffle_seed + 1})

    with pytest.raises(RegistrationError, match="LabelingConfig"):
        create_app(
            app_config,
            other,
            open_router_config=open_router_config,
            observability_config=observability_config,
        )
