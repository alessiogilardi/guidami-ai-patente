from pydantic import BaseModel, ConfigDict


class BlockOutcome(BaseModel):
    """One block's `build-glossary` result: written, skipped, or (via the caller) failed."""

    model_config = ConfigDict(frozen=True)

    source: str
    article_number: str
    comma_number: str | None
    entries_written: int
    skipped: bool

    @property
    def label(self) -> str:
        """The block's `source/article_number/comma_number` identity, `comma_number` -> "all"."""
        comma = self.comma_number or "all"
        return f"{self.source}/{self.article_number}/{comma}"
