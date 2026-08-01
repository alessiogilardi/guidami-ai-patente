"""Constants for FlowContext keys (no magic strings).

Single vocabulary for the ingestion flows. Extended in an ADDITIVE way by the
slices: here are the keys consumed by indexing (SP03/04), by knowledge
preparation (SP05), and by quiz preparation (SP06: `CLEANED_QUIZ`, extended by
the single-loop enrichment revamp: `MAPPED_QUIZ`). `IMAGE_DESCRIPTIONS` is not
a context key, it stays an internal dict of the enricher. No `SOURCE`: it is
injected at the factory, not read from the context.
"""

# --- Knowledge indexing (SP03) ---
# The indexing flow is per-source (one run per source): input = flat list of
# CleanedArticleModel for ONE source only, loaded from the "cleaned" layer (T-14). Two
# parallel derivations (PD-12) are computed from that same loaded list: ARTICLE_ENTITIES
# (article rows to store) and EMBEDDABLE_ARTICLE_COMMAS (comma rows to embed then store).
ARTICLE_ENTITIES = "article_entities"  # map→entity output: list[Article] → store
EMBEDDABLE_ARTICLE_COMMAS = (
    "embeddable_article_commas"  # expand output → embed: list[EmbeddableArticleComma]
)

# --- Knowledge preparation (per-element layers) ---
# Clean flow: LoadJsonStep → ApplyStep → FilterAlreadyDoneStep → WriteJsonDirStep.
PARSED_ARTICLES = (
    "parsed_articles"  # clean input: list[ParsedArticleModel] loaded from the "parsed" layer
)
CLEANED_ARTICLES = "cleaned_articles"  # clean output: list[CleanedArticleModel]
FILTERED_ARTICLES = "filtered_articles"  # FilterAlreadyDoneStep output: elements still to clean

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"  # input: enriched quiz bank loaded from disk
EMBEDDED_QUIZ = "embedded_quiz"  # intermediate models → embed
QUIZ_ENTITIES = "quiz_entities"  # final entities → store

# --- Quiz preparation (SP06, extended by SP09) ---
# Cleaning flow: LoadJsonStep → ApplyStep(flatten_quiz) → WriteJsonStep.
# Enrichment flow: LoadJsonStep → ApplyStep(map_cleaned_quiz) → AsyncApplyStep(enrich_quiz)
#   → WriteJsonStep.
PARSED_QUIZ = "parsed_quiz"  # input: nested quiz bank loaded from the "parsed" layer
CLEANED_QUIZ = "cleaned_quiz"  # cleaning output / enrichment input: list[CleanedQuizModel] flat
MAPPED_QUIZ = "mapped_quiz"  # cleaned→enriched map output; async-enrichment input
