from pathlib import Path

from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)


class ArticleContextualizerAgent(
    BaseAgent[ArticleContextualizerRequest, ArticleContextualizerResponse]
):
    """Pure LLM wrapper for contextualising normative articles."""

    @classmethod
    def from_yaml(  # type: ignore[override]
        cls, name: str, agents_dir: Path
    ) -> "ArticleContextualizerAgent":
        """Instantiate the agent from a YAML configuration file.

        Args:
            name: YAML file name without extension.
            agents_dir: Directory containing agent configuration files.

        Returns:
            Configured `ArticleContextualizerAgent` instance.
        """
        return super().from_yaml(name, agents_dir, output_type=ArticleContextualizerResponse)  # type: ignore[return-value]
