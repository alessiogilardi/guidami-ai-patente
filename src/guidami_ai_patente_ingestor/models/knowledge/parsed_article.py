from pydantic import BaseModel


class ParsedArticleModel(BaseModel):
    """Article of the corpus normativo (CdS or CAP), as found in the source JSON."""

    number: str
    title: str
    text: str
    paragraphs: list[str]
    url: str
    scraped_at: str
    repealed: bool
