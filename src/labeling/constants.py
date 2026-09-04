"""Values the labeling stack names in exactly one place."""

EMBEDDING_MODEL_COLUMN = "embedding_3_small"
"""The `quiz_question_embeddings` column both the batch pass and the live path read.

Deliberately a constant, not configuration. The column determines which embedding
model produced the dense arm's query vector, so making it configurable would oblige it
to enter the configuration epoch (`labeling_runs` plus `uq_labeling_runs_live_config`)
— otherwise a switch would serve labelings judged on another model's vectors under an
identical cache key, which is the failure AD-8 exists to prevent. The corpus half is
asymmetric on top of that: `article_commas.embedding` is a single unversioned column,
hardcoded in `CorpusReadRepository.dense_top_k`, so a model change today means
re-embedding the corpus in place rather than selecting a second column.

Promoting this to a real, symmetric parameter — per-model columns on `article_commas`,
a parameterised `dense_top_k`, the column inside the epoch key, and an ingestion write
path that targets it — is a separate, deliberate increment (spec 0012 phase 3, D7).
Until then this is the single edit point, referenced by both callers.
"""
