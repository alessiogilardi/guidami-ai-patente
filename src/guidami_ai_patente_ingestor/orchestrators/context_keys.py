"""Costanti per le chiavi del FlowContext (no magic string).

Vocabolario unico dei flow di ingestion. Esteso in modo ADDITIVO dalle slice:
qui le chiavi consumate dall'indexing (SP03/04), dalla preparation knowledge
(SP05) e dalla preparation quiz (SP06: `CLEANED_QUIZ`). L'enrichment quiz
ripiega describe+map in un solo step: `IMAGE_DESCRIPTIONS` non è una chiave
di context, resta un dict interno all'enricher. Niente `SOURCE`: è iniettata
alla factory, non letta dal context.
"""

# --- Knowledge indexing (SP03) ---
# Il flow di indexing è per-source (una run per source): input = lista piatta di
# EnrichedArticleModel di UNA sola source. Stessa chiave usata dal flow di enrichment (SP05).
ENRICHED_ARTICLES = (
    "enriched_articles"  # input indexing/enrich: list[EnrichedArticleModel], una source
)
EMBEDDABLE_CHUNKS = "embeddable_chunks"  # output chunker → embed: list[EmbeddableChunkModel]
CHUNK_ENTITIES = "chunk_entities"  # output map→entità: list[KnowledgeChunk] → store

# --- Knowledge preparation (SP05) ---
# Flow clean: LoadJsonStep → MapStep → WriteJsonStep.
# Flow enrich: LoadJsonStep → MapStep → EnrichDataStep → WriteJsonStep.
PARSED_ARTICLES = (
    "parsed_articles"  # input clean: list[ParsedArticleModel] caricati dal layer "parsed"
)
CLEANED_ARTICLES = (
    "cleaned_articles"  # output clean / input enrich: list[ParsedArticleModel] puliti
)

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"  # input: quiz bank enriched caricato da disco
EMBEDDABLE_QUIZ = "embeddable_quiz"  # modelli intermedi → embed
QUIZ_ENTITIES = "quiz_entities"  # entità finali → store

# --- Quiz preparation (SP06, esteso da SP09) ---
# Flow cleaning: LoadJsonStep → ApplyStep(flatten_quiz) → WriteJsonStep.
# Flow enrichment: LoadJsonStep → ApplyStep(enrich) → WriteJsonStep.
PARSED_QUIZ = "parsed_quiz"  # input: quiz bank nested caricato dal layer "parsed"
CLEANED_QUIZ = "cleaned_quiz"  # output cleaning / input enrichment: list[CleanedQuizModel] flat
