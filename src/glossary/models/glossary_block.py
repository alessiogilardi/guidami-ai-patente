from pydantic import BaseModel, ConfigDict


class CommaSpan(BaseModel):
    """The `[start, end)` offset range one comma occupies inside `GlossaryBlock.text`."""

    model_config = ConfigDict(frozen=True)

    comma_number: str
    start: int
    end: int


class GlossaryBlock(BaseModel):
    """One block's already-cleaned, concatenated text, ready for extraction (FR-1)."""

    model_config = ConfigDict(frozen=True)

    source: str
    article_number: str
    text: str
    comma_spans: tuple[CommaSpan, ...]

    def get_comma_number_at(self, offset: int) -> str:
        """Resolves an offset into `text` to the comma it came from (Data Model).

        Raises:
            ValueError: `offset` falls outside every known span — a defect in the
                caller, since every character of `text` belongs to exactly one span.
        """
        for span in self.comma_spans:
            if span.start <= offset < span.end:
                return span.comma_number
        raise ValueError(f"offset {offset} is outside every known comma span")
