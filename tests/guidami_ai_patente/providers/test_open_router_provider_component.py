"""The model provider is one container-managed third-party object (AD-16)."""

from pydantic_ai.providers.openrouter import OpenRouterProvider
from pywire import get_default_container

from guidami_ai_patente.providers import OpenRouterProviderComponent


def test_the_component_exposes_an_open_router_provider(api_client: object) -> None:
    component = get_default_container().resolve(OpenRouterProviderComponent)

    assert isinstance(component.provider, OpenRouterProvider)


def test_every_agent_shares_one_provider(api_client: object) -> None:
    container = get_default_container()

    first = container.resolve(OpenRouterProviderComponent).provider
    second = container.resolve(OpenRouterProviderComponent).provider

    assert first is second, (
        "one provider per process: two would open two HTTP client pools against the "
        "same endpoint for no benefit"
    )
