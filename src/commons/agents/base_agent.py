import mimetypes
from pathlib import Path
from string import Template
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.settings import ModelSettings

from ..configs import AgentConfig


class PromptRenderer:
    """SRP: Si occupa esclusivamente della formattazione del prompt e della gestione media."""

    def __init__(self, template_str: str) -> None:
        """Inizializza il renderer con un template stringa in formato `$var`.

        Args:
            template_str: Template del prompt utente con variabili in formato `$var`.
        """
        self._template = Template(template_str)

    def render(
        self, request: BaseModel | dict[str, Any], images: tuple[Path, ...] = ()
    ) -> str | list[str | BinaryContent]:
        """Sostituisce le variabili nel template e allega le immagini binarie.

        Args:
            request: Modello Pydantic o dizionario con le variabili da sostituire.
            images: Tuple di percorsi immagine da allegare come `BinaryContent`.

        Returns:
            Stringa renderizzata se nessuna immagine, altrimenti lista con testo e binari.
        """
        # Centralizziamo qui lo spacchettamento del modello Pydantic
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


class ConfigLoader:
    """SRP/DIP: Isola la logica di caricamento della configurazione dal filesystem."""

    @staticmethod
    def from_yaml(agents_dir: Path, name: str) -> AgentConfig:
        """Carica e valida la configurazione dell'agente da un file YAML.

        Args:
            agents_dir: Directory che contiene i file di configurazione degli agenti.
            name: Nome dell'agente (senza estensione `.yaml`).

        Returns:
            `AgentConfig` validata.

        Raises:
            FileNotFoundError: Se il file YAML non esiste.
        """
        yaml_path = agents_dir / f"{name}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Agent config not found: {name} ({yaml_path})")

        with yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return AgentConfig.model_validate(raw)


class BaseAgent[T_In: BaseModel, T_Out]:
    """Wrappa `pydantic_ai.Agent` gestendo modelli Pydantic per Request e Response."""

    def __init__(self, config: AgentConfig, output_type: type[T_Out]) -> None:
        """Inizializza l'agente con la configurazione e il tipo di output.

        Args:
            config: Configurazione dell'agente (modello, prompt, parametri).
            output_type: Tipo Pydantic atteso per l'output strutturato dell'LLM.
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
        cls, name: str, agents_dir: Path, output_type: type[T_Out]
    ) -> "BaseAgent[T_In, T_Out]":
        """Factory method per istanziare l'agente leggendo un file YAML."""
        config = ConfigLoader.from_yaml(agents_dir, name)
        return cls(config, output_type)

    async def run(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Esegue l'agente in modo ASINCRONO."""
        # Adesso passiamo direttamente l'oggetto 'request' al renderer
        prompt_content = self.renderer.render(request, images)
        result = await self._agent.run(prompt_content)
        return result.output

    def run_sync(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Esegue l'agente in modo SINCRONO bloccando il thread corrente."""
        # Adesso passiamo direttamente l'oggetto 'request' al renderer
        prompt_content = self.renderer.render(request, images)
        result = self._agent.run_sync(prompt_content)
        return result.output

    def __call__(self, request: T_In, images: tuple[Path, ...] = ()) -> T_Out:
        """Alias sincrono di `run_sync`: consente di usare l'agente come funzione callable."""
        return self.run_sync(request, images)

    @property
    def core_agent(self) -> Agent[None, T_Out]:
        """Permette di accedere all'agente pydantic_ai originale."""
        return self._agent

    @staticmethod
    def __parse_model_name(config: AgentConfig) -> str:
        """Adatta il nome del modello rimuovendo l'eventuale slash iniziale per compatibilità."""
        if "/" in config.model_name:
            return config.model_name.replace("/", ":", 1)

        return config.model_name
