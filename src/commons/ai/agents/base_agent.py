from contextlib import AbstractContextManager
from pathlib import Path
from typing import Self, cast

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.settings import ModelSettings

from commons.ai.observability import LlmCallTracker, PydanticAILlmCallCapture
from commons.clients import FileReaderInterface
from commons.repositories import YamlRepository

from .configs import AgentConfig
from .utils.prompt_renderer import PromptInput, PromptRenderer


class BaseAgent[T_In, T_Out]:
    """Wraps `pydantic_ai.Agent` with Pydantic request/response models."""

    output_type: type[T_Out]

    def __init__(
        self,
        config: AgentConfig,
        name: str | None = None,
        file_reader: FileReaderInterface | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """Initialize the agent with configuration.

        Args:
            config: Agent configuration (model, prompts, parameters).
            name: Identifies this agent as `LlmCallLog.caller` in tracked rows.
                Defaults to the concrete subclass name when omitted.
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.
            tracker: Optional port persisting one `LlmCallLog` per call. When
                `None`, `run`/`run_sync` run today's untracked path unchanged.
        """
        self._name = name if name is not None else type(self).__name__
        self._model_name = config.model_name
        self._system_prompt = config.system
        self._tracker = tracker
        self.renderer = PromptRenderer(config.user, file_reader)

        pydantic_ai_model_name = self.__parse_model_name(config.model_name)

        settings: ModelSettings = {"temperature": config.temperature, "timeout": config.timeout}
        if config.max_tokens is not None:
            settings["max_tokens"] = config.max_tokens

        self._agent: Agent[None, T_Out] = Agent(
            pydantic_ai_model_name,
            output_type=self.output_type,
            system_prompt=config.system,
            model_settings=settings,
            retries=config.num_retries,
            defer_model_check=True,
        )

    @classmethod
    def from_yaml(
        cls,
        name: str,
        repository: YamlRepository,
        file_reader: FileReaderInterface | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> Self:
        """Instantiate the agent by loading its YAML configuration file.

        Args:
            name: Agent name (without the `.yaml` extension); also becomes the
                agent's identity (`self._name`, i.e. `LlmCallLog.caller`).
            repository: Repository used to load agent configuration files.
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.
            tracker: Optional port persisting one `LlmCallLog` per call.

        Returns:
            Configured agent instance.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
        """
        config = cast(AgentConfig, repository.load(f"{name}.yaml"))
        return cls(config, name, file_reader, tracker)

    async def run(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent asynchronously."""
        prompt_content = self.renderer.render(cast(PromptInput, request), images)
        if self._tracker is None:
            result = await self._agent.run(prompt_content)
            return result.output

        with self._tracked(_prompt_text(prompt_content)) as capture:
            result = await self._agent.run(prompt_content)
            capture.record(result)
        return result.output

    def run_sync(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent synchronously, blocking the current thread."""
        prompt_content = self.renderer.render(cast(PromptInput, request), images)
        if self._tracker is None:
            result = self._agent.run_sync(prompt_content)
            return result.output

        with self._tracked(_prompt_text(prompt_content)) as capture:
            result = self._agent.run_sync(prompt_content)
            capture.record(result)
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

    def _tracked(self, prompt: str) -> AbstractContextManager[PydanticAILlmCallCapture]:
        """Binds this agent's fixed identity to `PydanticAILlmCallCapture.tracked`.

        `caller`/`model`/`system_prompt`/`tracker` never change across calls to this
        agent instance, so only `prompt` (the one thing that varies per call) needs
        to be supplied at the `run`/`run_sync` call site. Callers must have already
        checked `self._tracker is not None` (both do, via their early-return branch).
        """
        assert self._tracker is not None
        return PydanticAILlmCallCapture.tracked(
            self._name, self._model_name, prompt, self._system_prompt, self._tracker
        )

    @staticmethod
    def __parse_model_name(model_name: str) -> str:
        """Rewrite the model name: replace the first `/` with `:` for pydantic_ai compatibility."""
        if "/" in model_name:
            return model_name.replace("/", ":", 1)

        return model_name


def _prompt_text(prompt: str | list[str | BinaryContent]) -> str:
    """Collapses the renderer's `str | list[str | BinaryContent]` union to its text part.

    Images are never persisted (log-schema plan Decision 8): only the leading text
    element of a multi-part prompt is kept.
    """
    if isinstance(prompt, str):
        return prompt

    return next(part for part in prompt if isinstance(part, str))
