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
# EnrichedArticle di UNA sola source. Stessa chiave usata dal flow di enrichment (SP05).
ENRICHED_ARTICLES = "enriched_articles"  # input indexing/enrich: list[EnrichedArticle], una source
CHUNKS = "chunks"  # output del chunker → embed → store

# --- Knowledge preparation (SP05) ---
# Flow clean: LoadJsonStep → MapStep → WriteJsonStep.
# Flow enrich: LoadJsonStep → ContextualizeStep → WriteJsonStep.
PARSED_ARTICLES = "parsed_articles"  # input clean: list[Article] caricati dal layer "parsed"
CLEANED_ARTICLES = "cleaned_articles"  # output clean / input enrich: list[Article] puliti

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"  # input: quiz bank enriched caricato da disco
EMBEDDABLE_QUIZ = "embeddable_quiz"  # modelli intermedi → embed
QUIZ_ENTITIES = "quiz_entities"  # entità finali → store

# --- Quiz preparation (SP06) ---
# Flow: LoadJsonStep → EnrichQuizStep → WriteJsonStep.
CLEANED_QUIZ = "cleaned_quiz"  # input: quiz bank caricato dal layer "cleaned"
