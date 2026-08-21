from pydantic import BaseModel


class RetrievedComma(BaseModel):
    """A comma retrieved from the corpus, carrying enough of its parent article to cite it.

    `source` is mandatory because article numbers collide across sources — CdS art. 43
    and Regolamento art. 43 both exist — so `article_number` alone cannot disambiguate
    a citation. `id` is the `article_commas.id` of the source row, carried so callers can
    reference the row without a second lookup by citation.
    """

    id: int
    source: str
    article_number: str
    article_title: str
    comma_number: str
    text: str
    distance: float

    @property
    def citation(self) -> str:
        """Human-readable citation, e.g. `"cds art. 43 c. 3"`."""
        return f"{self.source} art. {self.article_number} c. {self.comma_number}"
