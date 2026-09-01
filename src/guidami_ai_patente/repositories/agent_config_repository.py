"""Loads agent prompts from the configured `agents_dir`."""

from pywire import Autowired, repository

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from labeling.configs import LabelingConfig


@repository
class AgentConfigRepository:
    """The API's single door to the agent prompt files (AD-22).

    A repository rather than a provider: no caller wants the `YamlRepository` or the
    `LocalFileSystemClient` themselves — they want "the config of the agent called X",
    which is a read. The two `commons/` classes are an implementation detail held
    here, not a shared object handed out (AD-16).

    Reading through the file-system client is not decoration: `BaseFileSystemClient`
    anchors every path to `agents_dir` and raises `PermissionError` on anything that
    resolves outside it, so a name is confined to the prompt directory by construction
    rather than by a caller remembering to sanitise it.

    Building the client in `__init__` resolves `agents_dir` once, at startup, which is
    the same fail-fast intent as the variable having no default anywhere (AD-22).
    """

    labeling_config: Autowired[LabelingConfig]

    def __init__(self) -> None:
        """Anchors a YAML repository to the configured agents directory."""
        self._repository: YamlRepository[AgentConfig] = YamlRepository(
            AgentConfig,
            file_system_client=LocalFileSystemClient(self.labeling_config.agents_dir),
        )

    def load(self, name: str) -> AgentConfig:
        """Returns the config of the agent named `name` (without the `.yaml` suffix).

        Args:
            name: Bare agent name, e.g. `"comma_labeler"`.

        Returns:
            The parsed and validated `AgentConfig`.

        Raises:
            FileNotFoundError: No `<name>.yaml` exists under `agents_dir`.
            PermissionError: The name resolves outside `agents_dir`.
        """
        return self._repository.load_one(f"{name}.yaml")
