from pydantic import BaseModel


class Article(BaseModel):
    """Articolo del corpus normativo (CdS o CAP), come da JSON sorgente."""

    number: str
    title: str
    text: str
    paragraphs: list[str]
    url: str
    scraped_at: str
    repealed: bool
