from pydantic import BaseModel


class ParsedComma(BaseModel):
    """A single comma (paragraph) of an article, as extracted by the scraper."""

    number: str
    text: str


class ParsedArticleModel(BaseModel):
    """Article of the corpus normativo (CdS or CAP), as found in the source JSON."""

    number: str
    title: str
    commas: list[ParsedComma]
    url: str
    scraped_at: str
    repealed: bool
