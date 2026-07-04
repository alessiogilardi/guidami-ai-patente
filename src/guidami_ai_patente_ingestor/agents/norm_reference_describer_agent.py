from pathlib import Path

from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberRequest,
    NormReferenceDescriberResponse,
)


class NormReferenceDescriberAgent(
    BaseAgent[NormReferenceDescriberRequest, NormReferenceDescriberResponse]
):
    """Pure LLM wrapper for generating normative metadata from quiz questions."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, agents_dir: Path
    ) -> "NormReferenceDescriberAgent":
        """Instantiate the agent from a YAML configuration file.

        Args:
            name: YAML file name without extension.
            agents_dir: Directory containing agent configuration files.

        Returns:
            Configured `NormReferenceDescriberAgent` instance.
        """
        return super().from_yaml(name, agents_dir, output_type=NormReferenceDescriberResponse)  # type: ignore[return-value]
