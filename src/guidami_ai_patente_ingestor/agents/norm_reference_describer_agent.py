from commons.agents import BaseAgent
from commons.repositories import YamlRepository
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
        cls, name: str, repository: YamlRepository
    ) -> "NormReferenceDescriberAgent":
        """Instantiate the agent from a YAML configuration file.

        Args:
            name: YAML file name without extension.
            repository: Repository used to load agent configuration files.

        Returns:
            Configured `NormReferenceDescriberAgent` instance.
        """
        return super().from_yaml(name, repository, output_type=NormReferenceDescriberResponse)  # type: ignore[return-value]
