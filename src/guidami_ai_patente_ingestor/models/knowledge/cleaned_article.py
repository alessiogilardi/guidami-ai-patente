from typing import Literal

from pydantic import BaseModel


class CleanedArticleModel(BaseModel):
    """Article cleaned from normattiva markup, carrying its own source.

    `source` enters the data at the parsed→cleaned boundary: from here on the
    element is self-identifying, so its id no longer depends on flow context.
    """

    number: str
    title: str
    text: str
    paragraphs: list[str]
    url: str
    scraped_at: str
    repealed: bool
    source: Literal["cds", "cap"]
