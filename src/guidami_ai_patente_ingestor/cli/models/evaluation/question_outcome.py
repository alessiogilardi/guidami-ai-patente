from pydantic import BaseModel, Field

from domain.models.retrieval import QuizEvaluationRow, RetrievedComma


class QuestionOutcome(BaseModel):
    """The per-question record PD-8's single pass builds, before aggregation.

    Consumed by `RankingCalculator.build_report` (T-6), `EvaluationArtifactWriter`'s
    detail/judge-export writers (T-9), and `RetrievalEvaluator` (T-10). The signal
    fields (`text_coverage` onward) default to a neutral value so a partially built
    outcome (e.g. `QuestionOutcome.model_construct(row=..., dense_top_k=..., fts_top_k=...)`
    in a test double) still serializes; a real run always supplies every field
    explicitly.
    """

    row: QuizEvaluationRow
    dense_top_k: list[RetrievedComma]
    fts_top_k: list[RetrievedComma]
    text_coverage: float = 0.0
    keyword_best_df: int | None = None
    keyword_measurable: bool = False
    hits: dict[int, bool] = Field(default_factory=dict)
    top1_adherence: float = 0.0
    dense_fts_overlap: float = 0.0
    distance_margin: float = 0.0
