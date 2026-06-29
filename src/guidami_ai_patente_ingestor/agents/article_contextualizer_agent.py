from pathlib import Path
from typing import Any, Self, cast

from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel


class ArticleContextualizerAgent(BaseAgent[dict[int, str]]):
    """Arricchisce i commi del corpus normativo con contesto situazionale via LLM."""

    def contextualize(self, article: EnrichedArticleModel) -> dict[int, str]:
        """Produce un contesto situazionale per ogni comma dell'articolo.

        Articoli abrogati vengono saltati senza chiamare il modello.

        Args:
            article: Articolo del corpus normativo da contestualizzare.

        Returns:
            Dizionario `{comma_index: contesto}`. Vuoto per articoli abrogati.
        """
        if article.repealed or not article.paragraphs:
            return {}

        numbered_paragraphs = [f"Comma {i}: {para}" for i, para in enumerate(article.paragraphs)]

        variables = {
            "title": article.title,
            "text": article.text,
            "paragraphs": "\n".join(numbered_paragraphs),
        }

        # Pydantic AI espone il risultato strutturato in .data
        result = self.run_prompt_sync(variables)
        return result.output

    @classmethod
    def from_yaml(
        cls,
        name: str,
        agents_dir: Path,
        output_type: Any = None,
    ) -> Self:
        return cast(Self, super().from_yaml(name, agents_dir, dict[int, str]))
