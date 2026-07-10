from pydantic import BaseModel


class ArticleContextualizerRequest(BaseModel):
    """Input for the norm article contextualization agent.

    Attributes:
        title: Article title.
        text: Article main text.
        paragraphs: Commas pre-formatted as a numbered string (e.g. "1. ...", "2. ...").
    """

    title: str
    text: str
    paragraphs: str
