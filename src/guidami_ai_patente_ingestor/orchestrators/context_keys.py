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
# EnrichedArticleModel for ONE source only. Same key used by the enrichment flow (SP05).
ENRICHED_ARTICLES = (
    "enriched_articles"  # indexing/enrich input: list[EnrichedArticleModel], one source
)
EMBEDDABLE_CHUNKS = "embeddable_chunks"  # chunker output → embed: list[EmbeddableChunkModel]
CHUNK_ENTITIES = "chunk_entities"  # map→entity output: list[KnowledgeChunk] → store

# --- Knowledge preparation (per-element layers) ---
# Clean flow: LoadJsonStep → ApplyStep → FilterAlreadyDoneStep → WriteJsonDirStep.
# Enrich flow: LoadJsonDirStep → FilterAlreadyDoneStep → ApplyStep → WriteJsonDirStep.
PARSED_ARTICLES = (
    "parsed_articles"  # clean input: list[ParsedArticleModel] loaded from the "parsed" layer
)
CLEANED_ARTICLES = "cleaned_articles"  # clean output / enrich input: list[CleanedArticleModel]
FILTERED_ARTICLES = (
    "filtered_articles"  # FilterAlreadyDoneStep output: elements still to (clean|enrich)
)

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
