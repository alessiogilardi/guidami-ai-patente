"""Loads agent prompts from the configured `agents_dir`."""

from pywire import Autowired, repository

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from guidami_ai_patente.configs import AppConfig
from labeling.configs import LabelingConfig


@repository
class AgentConfigRepository:
    """The API's single door to the agent prompt files (AD-22).

    Two anchors, one door. `load` reads the API's own agents from
    `AppConfig.agents_dir`; `load_judge` reads the epoch-controlled ones from
    `LabelingConfig.agents_dir`, whose prompt text *is* `prompt_version`. Keeping the
    two directories distinct is ADR 0020's shape: a per-deployment override of the
    judge's directory must not relocate a prompt that enters no epoch (D4). Both
    resolve `AGENTS_DIR` today, so the split costs nothing until it is needed.

    Reading through the file-system client is not decoration: `BaseFileSystemClient`
    anchors every path to its directory and raises `PermissionError` on anything that
    resolves outside it, so a name is confined by construction rather than by a caller
    remembering to sanitise it.

    Building both clients in `__init__` resolves the directories once, at startup,
    which is the same fail-fast intent as the variable having no default anywhere.
    """

    config: Autowired[AppConfig]
    labeling_config: Autowired[LabelingConfig]

    def __init__(self) -> None:
        """Anchors one YAML repository per agent directory."""
        self._app_agents: YamlRepository[AgentConfig] = YamlRepository(
            AgentConfig, file_system_client=LocalFileSystemClient(self.config.agents_dir)
        )
        self._judge_agents: YamlRepository[AgentConfig] = YamlRepository(
            AgentConfig,
            file_system_client=LocalFileSystemClient(self.labeling_config.agents_dir),
        )

    def load(self, name: str) -> AgentConfig:
        """Returns the config of an API agent whose prompt enters no epoch.

        Args:
            name: Bare agent name, e.g. `"explanation_writer"`.

        Returns:
            The parsed and validated `AgentConfig`.

        Raises:
            FileNotFoundError: No `<name>.yaml` exists under `AppConfig.agents_dir`.
            PermissionError: The name resolves outside that directory.
        """
        return self._app_agents.load_one(f"{name}.yaml")

    def load_judge(self, name: str) -> AgentConfig:
        """Returns the config of an epoch-controlled agent (AD-22).

        The prompt text this returns is what `prompt_version` hashes, so the batch
        judge and the live judge agree only when both resolve the same directory.

        Args:
            name: Bare agent name, e.g. `"comma_labeler"`.

        Returns:
            The parsed and validated `AgentConfig`.

        Raises:
            FileNotFoundError: No `<name>.yaml` exists under `LabelingConfig.agents_dir`.
            PermissionError: The name resolves outside that directory.
        """
        return self._judge_agents.load_one(f"{name}.yaml")
