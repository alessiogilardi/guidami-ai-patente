import mimetypes
from pathlib import Path
from string import Template
from typing import Any, cast

from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.settings import ModelSettings

from ..configs import AgentConfig
from ..repositories import YamlRepository


class PromptRenderer:
    """Formats the user prompt template and attaches media."""

    def __init__(self, template_str: str) -> None:
        """Initialize the renderer with a `$var`-style template string.

        Args:
            template_str: User prompt template with `$var` placeholders.
        """
        self._template = Template(template_str)

    def render(
        self, request: BaseModel | dict[str, Any], images: tuple[Path, ...] = ()
    ) -> str | list[str | BinaryContent]:
        """Substitute template variables and attach binary images.

        Args:
            request: Pydantic model or dict providing substitution values.
            images: Image paths to attach as `BinaryContent`.

        Returns:
            Rendered string when no images are provided, otherwise a list
            containing the text followed by `BinaryContent` items.
        """
        variables = request.model_dump() if isinstance(request, BaseModel) else request
        text = self._template.safe_substitute(**variables)

        if not images:
            return text

        parts: list[str | BinaryContent] = [text]
        for img in images:
            mime_type, _ = mimetypes.guess_type(img)
            media_type = mime_type or "application/octet-stream"
            parts.append(BinaryContent(data=img.read_bytes(), media_type=media_type))

        return parts


class BaseAgent[T_In: BaseModel, T_Out]:
    """Wraps `pydantic_ai.Agent` with Pydantic request/response models."""

    def __init__(self, config: AgentConfig, output_type: type[T_Out]) -> None:
        """Initialize the agent with configuration and output type.

        Args:
            config: Agent configuration (model, prompts, parameters).
            output_type: Expected Pydantic type for structured LLM output.
        """
        self.config = config
        self.renderer = PromptRenderer(config.user)

        model_name = self.__parse_model_name(config)

        settings: ModelSettings = {"temperature": config.temperature, "timeout": config.timeout}
        if config.max_tokens is not None:
            settings["max_tokens"] = config.max_tokens

        self._agent: Agent[None, T_Out] = Agent(
            model_name,
            output_type=output_type,
            system_prompt=config.system,
            model_settings=settings,
            retries=config.num_retries,
            defer_model_check=True,
        )

    @classmethod
    def from_yaml(
        cls, name: str, repository: YamlRepository, output_type: type[T_Out]
    ) -> "BaseAgent[T_In, T_Out]":
        """Instantiate the agent by loading its YAML configuration file.

        Args:
            name: Agent name (without the `.yaml` extension).
            repository: Repository used to load agent configuration files.
            output_type: Expected Pydantic type for structured LLM output.

        Returns:
            Configured agent instance.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
        """
        config = cast(AgentConfig, repository.load(f"{name}.yaml"))
        return cls(config, output_type)

    async def run(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent asynchronously."""
        prompt_content = self.renderer.render(request, images)
        result = await self._agent.run(prompt_content)
        return result.output

    def run_sync(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Run the agent synchronously, blocking the current thread."""
        prompt_content = self.renderer.render(request, images)
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
