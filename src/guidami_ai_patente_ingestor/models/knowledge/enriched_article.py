from pydantic import BaseModel, Field


class EnrichedArticle(BaseModel):
    """Articolo con contesti per comma generati dall'LLM (layer enriched).

    Self-contained: non dipende da `Article` — i campi sono replicati per
    mantenere `commons` indipendente dall'ingestor.
    """

    number: str
    title: str
    text: str
    paragraphs: list[str]
    url: str
    scraped_at: str
    repealed: bool
    contexts: dict[int, str] = Field(default_factory=dict)
