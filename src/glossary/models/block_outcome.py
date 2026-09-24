from pydantic import BaseModel, ConfigDict


class BlockOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    article_number: str
    comma_number: str | None
    entries_written: int
    skipped: bool

    @property
    def label(self) -> str:
        comma = self.comma_number or "all"
        return f"{self.source}/{self.article_number}/{comma}"
