from pydantic import BaseModel, ConfigDict

from .block_outcome import BlockOutcome


class GlossaryBuildReport(BaseModel):
    """The full result of one `build-glossary` run: every block's own outcome."""

    model_config = ConfigDict(frozen=True)

    outcomes: tuple[BlockOutcome, ...]
