"""Container-managed provider for the one shared OpenRouter model provider."""

from pydantic_ai.providers.openrouter import OpenRouterProvider
from pywire import Autowired, provider

from commons.configs import OpenRouterConfig
from labeling.wiring import build_open_router_provider


@provider
class OpenRouterProviderComponent:
    """Owns the one `OpenRouterProvider` every agent in this process shares.

    `OpenRouterProvider` is pydantic-ai's, so it is not ours to decorate — the
    third-party half of AD-16's rule 2. Built through `labeling.wiring`'s builder
    rather than instantiated here, so the API and the batch harness construct it the
    same way from the same single input, the API key.

    Named `...Component` because the bare name would collide with the pydantic-ai
    class it wraps at every import site.

    A provider, not a service: consumers receive a technical capability and never
    learn how it was built, and this class decides nothing (`.claude/rules/pywire-di.md`).
    """

    open_router_config: Autowired[OpenRouterConfig]

    def __init__(self) -> None:
        """Builds the provider from the configured credential."""
        self.provider: OpenRouterProvider = build_open_router_provider(
            self.open_router_config.api_key.get_secret_value()
        )
