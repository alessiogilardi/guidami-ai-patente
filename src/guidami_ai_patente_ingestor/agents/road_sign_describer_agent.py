from pathlib import Path

from commons.agents import BaseAgent
from commons.agents.base_agent import ConfigLoader
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)


class RoadSignDescriberAgent(BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]):
    """Wrapper puro intorno all'LLM per la descrizione dei segnali stradali via vision."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, agents_dir: Path
    ) -> "RoadSignDescriberAgent":
        """Istanzia l'agente leggendo la configurazione da un file YAML.

        Args:
            name: Nome del file YAML (senza estensione).
            agents_dir: Directory che contiene i file di configurazione degli agenti.

        Returns:
            Istanza configurata di `RoadSignDescriberAgent`.
        """
        config = ConfigLoader.from_yaml(agents_dir, name)
        return cls(config, RoadSignDescriberResponse)
