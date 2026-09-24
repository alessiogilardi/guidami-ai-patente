"""Loads glossary agent prompts from GlossaryConfig.agents_dir (one directory, two agents)."""

from pywire import Autowired, repository

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from glossary.configs import GlossaryConfig


@repository
class GlossaryAgentConfigRepository:
    """The package's single door to its two agent prompt files.

    Unlike `guidami_ai_patente`'s `AgentConfigRepository`, there is only one
    directory here: `GlossaryConfig.agents_dir` (AD-5) — this prompt enters no
    configuration epoch, so a single anchor is enough.
    """

    config: Autowired[GlossaryConfig]

    def __init__(self) -> None:
        self._agents = YamlRepository(
            AgentConfig, file_system_client=LocalFileSystemClient(self.config.agents_dir)
        )

    def load(self, name: str) -> AgentConfig:
        """Returns the config of `<name>.yaml` under `GlossaryConfig.agents_dir`."""
        return self._agents.load_one(f"{name}.yaml")
