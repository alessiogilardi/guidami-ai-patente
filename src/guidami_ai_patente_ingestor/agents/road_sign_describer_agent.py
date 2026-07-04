from pathlib import Path

from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)


class RoadSignDescriberAgent(BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]):
    """Pure LLM wrapper for describing road signs via vision."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, agents_dir: Path
    ) -> "RoadSignDescriberAgent":
        """Instantiate the agent from a YAML configuration file.

        Args:
            name: YAML file name without extension.
            agents_dir: Directory containing agent configuration files.

        Returns:
            Configured `RoadSignDescriberAgent` instance.
        """
        return super().from_yaml(name, agents_dir, output_type=RoadSignDescriberResponse)  # type: ignore[return-value]
