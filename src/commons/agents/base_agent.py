from pathlib import Path
from typing import Self, cast

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from commons.clients import FileReaderInterface

from ..configs import AgentConfig
from ..repositories import YamlRepository
from .utils.prompt_renderer import PromptInput, PromptRenderer


class BaseAgent[T_In, T_Out]:
    """Wraps `pydantic_ai.Agent` with Pydantic request/response models."""

    output_type: type[T_Out]

    def __init__(
        self, config: AgentConfig, file_reader: FileReaderInterface | None = None
    ) -> None:
        """Initialize the agent with configuration.

        Args:
            config: Agent configuration (model, prompts, parameters).
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.
        """
        self.config = config
        self.renderer = PromptRenderer(config.user, file_reader)

        model_name = self.__parse_model_name(config)

        settings: ModelSettings = {"temperature": config.temperature, "timeout": config.timeout}
        if config.max_tokens is not None:
            settings["max_tokens"] = config.max_tokens

        self._agent: Agent[None, T_Out] = Agent(
            model_name,
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
    ) -> Self:
        """Instantiate the agent by loading its YAML configuration file.

        Args:
            name: Agent name (without the `.yaml` extension).
            repository: Repository used to load agent configuration files.
            file_reader: Reader used to resolve `images` paths passed to `run`.
                Optional: only required by agents that pass `images=`.

        Returns:
            Configured agent instance.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
        """
        config = cast(AgentConfig, repository.load(f"{name}.yaml"))
        return cls(config, file_reader)

    async def run(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent asynchronously."""
        prompt_content = self.renderer.render(cast(PromptInput, request), images)
        result = await self._agent.run(prompt_content)
        return result.output

    def run_sync(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent synchronously, blocking the current thread."""
        prompt_content = self.renderer.render(cast(PromptInput, request), images)
        result = self._agent.run_sync(prompt_content)
        return result.output

    def __call__(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Synchronous alias for `run_sync`; allows the agent to be used as a callable."""
        return self.run_sync(request, images)

    @property
    def core_agent(self) -> Agent[None, T_Out]:
        """The underlying pydantic_ai Agent instance."""
        return self._agent

    @staticmethod
    def __parse_model_name(config: AgentConfig) -> str:
        """Rewrite the model name: replace the first `/` with `:` for pydantic_ai compatibility."""
        if "/" in config.model_name:
            return config.model_name.replace("/", ":", 1)

        return config.model_name
