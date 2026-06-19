from pathlib import Path
from typing import Any, Self, cast

from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.models.quiz import ImageDescription


class RoadSignDescriberAgent(BaseAgent[ImageDescription]):
    """Descrive segnali stradali tramite vision LLM."""

    def describe(self, image_path: Path) -> ImageDescription:
        """Descrive il segnale stradale nell'immagine.

        Args:
            image_path: Percorso dell'immagine del segnale.

        Returns:
            Descrizione strutturata con `name` e `description`.
        """
        return self.run_prompt_sync({}, images=(image_path,)).data

    @classmethod
    def from_yaml(
        cls,
        name: str,
        agents_dir: Path,
        output_type: Any = None,
    ) -> Self:
        return cast(Self, super().from_yaml(name, agents_dir, ImageDescription))
