from pydantic import BaseModel


class ArticleEntity(BaseModel):
    """Row of the `articles` table (see db/init.sql)."""

    source: str
    number: str
    title: str
    url: str
    is_repealed: bool
