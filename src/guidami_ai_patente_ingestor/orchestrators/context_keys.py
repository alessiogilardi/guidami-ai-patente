"""Costanti per le chiavi del FlowContext (no magic string).

Vocabolario unico dei flow di ingestion. Esteso in modo ADDITIVO dalle slice:
qui solo le chiavi consumate dall'indexing (SP03/04); le chiavi di preparation
(PARSED_*/CLEANED_*/IMAGE_DESCRIPTIONS) le aggiungono SP05/06.
"""

# --- Knowledge indexing (SP03) ---
ENRICHED_ARTICLES = "enriched_articles"    # input enrich (SP05) — NON rimuovere
ARTICLES_BY_SOURCE = "articles_by_source"  # input indexing: dict[str, list[EnrichedArticle]]
CHUNKS = "chunks"  # output del chunker → embed → store

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"  # input: quiz bank enriched caricato da disco
EMBEDDABLE_QUIZ = "embeddable_quiz"  # modelli intermedi → embed
QUIZ_ENTITIES = "quiz_entities"  # entità finali → store
