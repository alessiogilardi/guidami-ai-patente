"""One comma the judge associated with a question, as the explanation path reads it."""

from pydantic import BaseModel, ConfigDict


class LabeledComma(BaseModel):
    """A labeled comma with enough of its article to cite it (FR-5).

    `judge_rank` is the judge's own ordering, one-based, ascending by relevance — the
    order FR-5 requires the citations to be returned in and the order the writer sees
    them in. The retrieval arms' ranks (`dense_rank`, `text_rank`) are deliberately
    absent: they are recorded in `quiz_comma_labels` as a retrieval trace, and FR-5's
    citation contract does not include them.

    `source` is mandatory for the same reason it is on `RetrievedComma`: article
    numbers collide across sources — CdS art. 43 and Regolamento art. 43 both exist.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    article_number: str
    article_title: str
    comma_number: str
    text: str
    judge_rank: int

    @property
    def citation(self) -> str:
        """Human-readable citation, e.g. `"cds art. 43 c. 3"`.

        Built the same way as `RetrievedComma.citation`, so the writer sees the
        identical citation shape the judge saw for the same comma.
        """
        return f"{self.source} art. {self.article_number} c. {self.comma_number}"
