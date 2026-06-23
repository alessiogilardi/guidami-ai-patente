"""Costanti per le chiavi del FlowContext (no magic string).

Vocabolario unico dei flow di ingestion. Esteso in modo ADDITIVO dalle slice:
qui le chiavi consumate dall'indexing (SP03/04) e dalla preparation knowledge
(SP05); le chiavi di preparation quiz (IMAGE_DESCRIPTIONS) le aggiunge SP06.
"""

# --- Knowledge indexing (SP03) ---
# Il flow di indexing è per-source (una run per source): input = lista piatta di
# EnrichedArticle di UNA sola source. Stessa chiave usata dal flow di enrichment (SP05).
ENRICHED_ARTICLES = "enriched_articles"  # input indexing/enrich: list[EnrichedArticle], una source
CHUNKS = "chunks"  # output del chunker → embed → store

# --- Knowledge preparation (SP05) ---
# Flow clean: LoadParsedArticlesStep → CleanArticlesStep → WriteCleanedStep.
# Flow enrich: LoadCleanedArticlesStep → ContextualizeStep → WriteEnrichedStep.
PARSED_ARTICLES = "parsed_articles"  # input clean: list[Article] caricati dal layer "parsed"
CLEANED_ARTICLES = "cleaned_articles"  # output clean / input enrich: list[Article] puliti

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"  # input: quiz bank enriched caricato da disco
EMBEDDABLE_QUIZ = "embeddable_quiz"  # modelli intermedi → embed
QUIZ_ENTITIES = "quiz_entities"  # entità finali → store
