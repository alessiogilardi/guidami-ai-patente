"""AppConfig reaches the container as a single registered instance (spec 0012, AD-16)."""

import pytest
from pywire import get_default_container
from pywire.exceptions import RegistrationError

from guidami_ai_patente.api.app import create_app
from guidami_ai_patente.configs import AppConfig


def test_the_container_resolves_the_config_the_app_was_built_with(
    app_config: AppConfig, api_client: object
) -> None:
    assert get_default_container().resolve(AppConfig) is app_config


def test_building_the_app_twice_with_the_same_config_is_not_an_error(
    app_config: AppConfig, api_client: object
) -> None:
    create_app(app_config)

    assert get_default_container().resolve(AppConfig) is app_config


def test_building_the_app_with_a_second_config_raises(
    app_config: AppConfig, api_client: object
) -> None:
    other = app_config.model_copy(update={"port": 9999})

    with pytest.raises(RegistrationError, match="AppConfig"):
        create_app(other)
