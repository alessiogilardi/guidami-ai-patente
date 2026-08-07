from pydantic import BaseModel, Field

from .embeddable_quiz_variant import EmbeddableQuizVariant


class EmbedQuizVariantsResult(BaseModel):
    """Output of `EmbedQuizVariantsService`: computed rows plus FR-2's per-variant omission counts.

    `omitted_counts` maps variant name -> number of questions for which that variant's
    text builder returned `None` (missing input, e.g. no `quiz_metadata`) — never a
    stored null vector, per FR-2. Carried as one value (PD-8) so `StoreQuizStep` and the
    CLI-layer manifest/log recording (T-10) read from a single produced context value.
    """

    variants: list[EmbeddableQuizVariant]
    omitted_counts: dict[str, int] = Field(default_factory=dict)
