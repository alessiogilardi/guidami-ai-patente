from commons.agents import BaseAgent
from commons.clients import FileReaderInterface
from commons.repositories import YamlRepository
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)


class RoadSignDescriberAgent(BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]):
    """Pure LLM wrapper for describing road signs via vision."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, repository: YamlRepository, file_reader: FileReaderInterface
    ) -> "RoadSignDescriberAgent":
        """Instantiate the agent from a YAML configuration file.

        Args:
            name: YAML file name without extension.
            repository: Repository used to load agent configuration files.
            file_reader: Reader used to resolve the `images` paths passed to `run`.

        Returns:
            Configured `RoadSignDescriberAgent` instance.
        """
        return super().from_yaml(  # type: ignore[return-value]
            name, RoadSignDescriberResponse, repository, file_reader
        )
