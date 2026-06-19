import mimetypes
from pathlib import Path
from string import Template
from typing import Any

import yaml
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.settings import ModelSettings

from ..configs import AgentConfig


class PromptRenderer:
    """SRP: Si occupa esclusivamente della formattazione del prompt e della gestione media."""

    def __init__(self, template_str: str):
        self._template = Template(template_str)

    def render(
        self, variables: dict[str, Any], images: tuple[Path, ...] = ()
    ) -> str | list[str | BinaryContent]:

        text = self._template.safe_substitute(**variables)

        if not images:
            return text

        parts: list[str | BinaryContent] = [text]
        for img in images:
            mime_type, _ = mimetypes.guess_type(img)
            media_type = mime_type or "application/octet-stream"

            parts.append(BinaryContent(data=img.read_bytes(), media_type=media_type))

        return parts


class ConfigLoader:
    """SRP/DIP: Isola la logica di caricamento della configurazione dal filesystem."""

    @staticmethod
    def from_yaml(agents_dir: Path, name: str) -> AgentConfig:
        yaml_path = agents_dir / f"{name}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Agent config not found: {name} ({yaml_path})")

        with yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return AgentConfig.model_validate(raw)


class BaseAgent[T_out]:
    """Wrappa `pydantic_ai.Agent` usando i nuovi Generics nativi di Python 3.12."""

    def __init__(self, config: AgentConfig, output_type: type[T_out]):
        self.config = config
        self.renderer = PromptRenderer(config.user)

        # Adatta il nome del modello rimuovendo l'eventuale slash iniziale per compatibilità
        model_name = (
            config.model_name.replace("/", ":", 1)
            if "/" in config.model_name
            else config.model_name
        )

        settings: ModelSettings = {"temperature": config.temperature, "timeout": config.timeout}
        if config.max_tokens is not None:
            settings["max_tokens"] = config.max_tokens

        self._agent: Agent[None, T_out] = Agent(
            model_name,
            output_type=output_type,
            system_prompt=config.system,
            model_settings=settings,
            retries=config.num_retries,
            defer_model_check=True,
        )

    @classmethod
    def from_yaml(
        cls, name: str, agents_dir: Path, output_type: type[T_out]
    ) -> "BaseAgent[T_out]":
        """Factory method per istanziare l'agente leggendo un file YAML."""
        config = ConfigLoader.from_yaml(agents_dir, name)
        return cls(config, output_type)

    async def run_prompt(self, variables: dict[str, Any], images: tuple[Path, ...] = ()) -> Any:
        """Esegue l'agente in modo ASINCRONO."""
        prompt_content = self.renderer.render(variables, images)
        return await self._agent.run(prompt_content)

    def run_prompt_sync(self, variables: dict[str, Any], images: tuple[Path, ...] = ()) -> Any:
        """Esegue l'agente in modo SINCRONO bloccando il thread corrente."""
        prompt_content = self.renderer.render(variables, images)
        return self._agent.run_sync(prompt_content)

    @property
    def core_agent(self) -> Agent[None, T_out]:
        """Permette di accedere all'agente pydantic_ai originale."""
        return self._agent
