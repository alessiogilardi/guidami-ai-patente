from pathlib import Path

from commons.agents import BaseAgent
from commons.agents.base_agent import ConfigLoader
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberRequest,
    NormReferenceDescriberResponse,
)


class NormReferenceDescriberAgent(
    BaseAgent[NormReferenceDescriberRequest, NormReferenceDescriberResponse]
):
    """Wrapper puro intorno all'LLM per la generazione di metadati normativi dai quiz."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, agents_dir: Path
    ) -> "NormReferenceDescriberAgent":
        """Istanzia l'agente leggendo la configurazione da un file YAML.

        Args:
            name: Nome del file YAML (senza estensione).
            agents_dir: Directory che contiene i file di configurazione degli agenti.

        Returns:
            Istanza configurata di `NormReferenceDescriberAgent`.
        """
        config = ConfigLoader.from_yaml(agents_dir, name)
        return cls(config, NormReferenceDescriberResponse)
