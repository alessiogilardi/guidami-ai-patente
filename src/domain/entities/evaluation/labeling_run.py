from pydantic import BaseModel


class LabelingRunEntity(BaseModel):
    """Row of the `labeling_runs` table (see db/init.sql).

    `id` and `created_at` are DB-generated and have no corresponding field here.
    Records the run provenance a labeling pass is reconstructible from: judge model,
    prompt version, candidate variant, both arm depths, the shuffle seed, the corpus
    commit and comma count, and the requested question limit (spec 0011, FR-11).
    """

    judge_model: str
    prompt_version: str
    candidate_variant: str
    dense_k: int
    text_k: int
    shuffle_seed: int
    corpus_commit: str
    corpus_comma_count: int
    question_limit: int | None = None
