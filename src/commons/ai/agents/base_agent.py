import logging
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Self, cast

from openai import AsyncOpenAI
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from commons.ai.observability import LlmCallTracker, NullLlmCallTracker, PydanticAILlmCallCapture
from commons.clients import FileReaderInterface
from commons.repositories import YamlRepository

from .configs import AgentConfig
from .utils.prompt_renderer import PromptInput, PromptRenderer

logger = logging.getLogger(__name__)


class BaseAgent[T_In, T_Out]:
    """Wraps `pydantic_ai.Agent` with Pydantic request/response models."""

    output_type: type[T_Out]

    def __init__(
        self,
        config: AgentConfig,
        provider: Provider[AsyncOpenAI],
        file_reader: FileReaderInterface | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """Initialize the agent with configuration.

        Args:
            config: Agent configuration (model, prompts, parameters). `config.name`
                identifies this agent as `LlmCallLogEntity.caller` in tracked rows,
                defaulting to the concrete subclass name when `None`.
            provider: Provider injected into the underlying `pydantic_ai` model. An
                `OpenRouterProvider` selects `OpenRouterModel` (with OpenRouter-specific
                cost tracking); any other OpenAI-compatible provider (e.g.
                `OllamaProvider`) selects the generic `OpenAIChatModel`.
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.
            tracker: Optional port persisting one `LlmCallLogEntity` per call. When
                `None`, defaults to `NullLlmCallTracker`, a no-op collaborator.
        """
        self._name = config.name if config.name is not None else type(self).__name__
        self._model_name = config.model_name
        self._provider = provider
        self._system_prompt = config.system
        self._tracker: LlmCallTracker = tracker if tracker is not None else NullLlmCallTracker()
        self._renderer = PromptRenderer(config.user, file_reader)

        self._agent: Agent[None, T_Out] = Agent(
            self._create_model(),
            output_type=self.output_type,
            system_prompt=self._system_prompt,
            model_settings=self._create_model_settings(config),
            retries=config.num_retries,
            defer_model_check=True,
        )

    @classmethod
    def from_yaml(
        cls,
        name: str,
        repository: YamlRepository[AgentConfig],
        provider: Provider[AsyncOpenAI],
        file_reader: FileReaderInterface | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> Self:
        """Instantiate the agent by loading its YAML configuration file.

        Args:
            name: Agent name (without the `.yaml` extension); also becomes the
                agent's identity (`self._name`, i.e. `LlmCallLogEntity.caller`).
            repository: Repository used to load agent configuration files.
            provider: Provider injected into the underlying `pydantic_ai` model. See
                `BaseAgent.__init__` for the model-selection rule.
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.
            tracker: Optional port persisting one `LlmCallLogEntity` per call.

        Returns:
            Configured agent instance.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
        """
        config = repository.load_one(f"{name}.yaml")
        return cls(
            config=config,
            provider=provider,
            file_reader=file_reader,
            tracker=tracker,
        )

    async def run(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent asynchronously."""
        prompt_content = self._renderer.render(cast(PromptInput, request), images)
        prompt_text = _prompt_text(prompt_content)
        logger.debug(
            "Calling agent %r (model=%s, images=%d, prompt_chars=%d) asynchronously",
            self._name,
            self._model_name,
            len(images),
            len(prompt_text),
        )
        with self._tracked(prompt_text) as capture:
            result = await self._agent.run(prompt_content)
            capture.record(result)
        self._log_call_completed(capture)
        return result.output

    def run_sync(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent synchronously, blocking the current thread."""
        prompt_content = self._renderer.render(cast(PromptInput, request), images)
        prompt_text = _prompt_text(prompt_content)
        logger.debug(
            "Calling agent %r (model=%s, images=%d, prompt_chars=%d) synchronously",
            self._name,
            self._model_name,
            len(images),
            len(prompt_text),
        )
        with self._tracked(prompt_text) as capture:
            result = self._agent.run_sync(prompt_content)
            capture.record(result)
        self._log_call_completed(capture)
        return result.output

    def __call__(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Synchronous alias for `run_sync`; allows the agent to be used as a callable."""
        return self.run_sync(request, images)

    def __repr__(self) -> str:
        """Debug representation: class name and agent identity (`caller`)."""
        return f"{type(self).__name__}(name={self._name!r})"

    @property
    def core_agent(self) -> Agent[None, T_Out]:
        """The underlying pydantic_ai Agent instance."""
        return self._agent

    @property
    def _is_openrouter(self) -> bool:
        """Whether this agent's provider is `OpenRouterProvider`.

        Gates every OpenRouter-specific behavior: `OpenRouterModel` selection,
        the `openrouter_usage` model setting, and the "no cost reported" warning
        — none of which apply to a generic OpenAI-compatible provider (e.g. Ollama).
        """
        return isinstance(self._provider, OpenRouterProvider)

    def _tracked(self, prompt: str) -> AbstractContextManager[PydanticAILlmCallCapture]:
        """Binds this agent's fixed identity to `PydanticAILlmCallCapture.tracked`.

        `caller`/`model`/`system_prompt`/`tracker` never change across calls to this
        agent instance, so only `prompt` (the one thing that varies per call) needs
        to be supplied at the `run`/`run_sync` call site.
        """
        return PydanticAILlmCallCapture.tracked(
            self._name, self._model_name, prompt, self._system_prompt, self._tracker
        )

    def _log_call_completed(self, capture: PydanticAILlmCallCapture) -> None:
        """Logs a successful call's timing/usage; warns if OpenRouter reported no cost.

        Reads `capture.log` once: it rebuilds the `LlmCallLogEntity` on every access,
        so the fields used here are captured in a local instead of re-read per field.
        Only `OpenRouterProvider` calls are expected to report a cost (see
        `_create_model_settings`'s `openrouter_usage` setting), so the warning is
        skipped for every other provider (e.g. Ollama, which never reports cost).
        """
        log_entry = capture.log
        logger.info(
            "Agent %r call completed (latency_ms=%d, tokens=%s in / %s out / %s total, "
            "cost_usd=%s)",
            self._name,
            log_entry.latency_ms,
            log_entry.input_tokens,
            log_entry.output_tokens,
            log_entry.total_tokens,
            log_entry.cost_usd,
        )
        if log_entry.cost_usd is None and self._is_openrouter:
            logger.warning(
                "Agent %r call succeeded but OpenRouter reported no cost (model=%s)",
                self._name,
                self._model_name,
            )

    def _create_model(self) -> Model:
        model_name = _parse_model_name(self._model_name)
        if self._is_openrouter:
            return OpenRouterModel(model_name, provider=self._provider)

        return OpenAIChatModel(model_name, provider=self._provider)

    def _create_model_settings(self, config: AgentConfig) -> ModelSettings:
        settings: ModelSettings = {
            "temperature": config.temperature,
            "timeout": config.timeout,
        }
        if config.max_tokens is not None:
            settings["max_tokens"] = config.max_tokens
        if self._is_openrouter:
            return OpenRouterModelSettings(**settings, openrouter_usage={"include": True})

        return settings


def _parse_model_name(model_name: str) -> str:
    """Rewrite the model name: removes "openrouter/" for pydantic_ai compatibility."""
    if model_name.startswith("openrouter/"):
        return model_name.removeprefix("openrouter/")

    return model_name


def _prompt_text(prompt: str | list[str | BinaryContent]) -> str:
    """Collapses the renderer's `str | list[str | BinaryContent]` union to its text part.

    Images are never persisted (log-schema plan Decision 8): only the leading text
    element of a multi-part prompt is kept.
    """
    if isinstance(prompt, str):
        return prompt

    return next(part for part in prompt if isinstance(part, str))
