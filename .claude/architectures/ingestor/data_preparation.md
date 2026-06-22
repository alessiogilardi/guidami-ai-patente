# Ingestor — Pipeline di data preparation

Riferimento progettazione: `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--article-contextual-embedding.md`,
`plans/ingest--quiz-image-descriptions.md`.

Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI.

Due pipeline di preparation offline, idempotenti, che precedono le pipeline di
indexing. Producono gli artefatti `enriched` da cui l'indexing legge.

## Decisioni implementate

### Topologia a due stadi

```
parsed ──[DataPreparationPipeline: clean → enrich]────▶ enriched ──[IndexingPipeline]──────▶ DB
parsed ──[QuizDataPreparationPipeline: enrich]─────────▶ enriched ──[QuizIndexingPipeline]──▶ DB
```

L'enrichment LLM (costoso, offline) è separato dall'indexing (ri-eseguibile a
costo zero su `enriched`). Le due pipeline sono idempotenti: saltano se l'output
`enriched` esiste; il flag `--force` forza la rigenerazione.

### Entità ingestor per l'enriched quiz bank

`EnrichedQuizMainQuestion` e `EnrichedQuizSubQuestion` (in
`guidami_ai_patente_ingestor/entities/enriched_quiz_bank.py`) mappano il formato
del quiz bank enriched su disco. `EnrichedQuizSubQuestion` aggiunge
`image_description: str | None` rispetto alla controparte parsed.
Sono distinte da `QuizMainQuestion`/`QuizSubQuestion` (che restano il mapping
del layer parsed) per rispettare la regola entità ↔ layer.

### `repositories/enriched_article_repository.py` — `EnrichedArticleRepository`

- `load(path: Path) -> list[EnrichedArticle]` e
  `write(articles: list[EnrichedArticle], path: Path) -> None` — stesso pattern
  di `ArticleRepository`, ma opera sul tipo `EnrichedArticle` (da `commons`).
- `write` crea directory mancanti e serializza con `ensure_ascii=False, indent=2`.

### `repositories/enriched_quiz_bank_repository.py` — `EnrichedQuizBankRepository`

- `load(path: Path) -> list[EnrichedQuizMainQuestion]` e
  `write(questions: list[EnrichedQuizMainQuestion], path: Path) -> None`.
- Stesso pattern dei repository JSON esistenti.

### `agents/article_contextualizer_agent.py` — `ArticleContextualizerAgent`

Sottoclasse di `BaseAgent[dict[int, str]]` (`commons/agents/`). Sostituisce il
precedente service `ArticleContextualizer` (rimosso).

- `contextualize(article: Article) -> dict[int, str]`: early return `{}` se
  `article.repealed or not article.paragraphs` (nessuna chiamata LLM). Costruisce
  `variables = {"title": ..., "text": ..., "paragraphs": "Comma {i}: {para}..."}`.
  Chiama `run_prompt_sync(variables).output` — PydanticAI tipa il risultato come
  `dict[int, str]` direttamente.
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory che ignora
  `output_type` e lo fissa a `dict[int, str]`.
- L'output strutturato è gestito da PydanticAI via `output_type`; non è necessario
  parsare JSON manualmente né validare la risposta grezza.

### `agents/road_sign_describer_agent.py` — `RoadSignDescriberAgent`

Sottoclasse di `BaseAgent[ImageDescription]` (`commons/agents/`). Sostituisce il
precedente service `RoadSignDescriber` (rimosso).

- `describe(image_path: Path) -> ImageDescription`: chiama
  `run_prompt_sync({}, images=(image_path,)).output`.
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory che fissa
  `output_type=ImageDescription`.
- `ImageDescription(BaseModel, frozen=True)` — `name: str`, `description: str`
  — vive in `guidami_ai_patente_ingestor/models/quiz/image_description.py`.

### `orchestrators/knowledge_preparation/` — `DataPreparationPipeline` + `DataPreparationPipelineBuilder`

- Sostituisce `orchestrators/knowledge_cleaning/` (vedi deprecazione sotto).
- **`DataPreparationPipeline.run(force: bool = False)`**: per ciascuna source
  (cds, cap):
  1. risolve `enriched_path = layer_resolver.path("enriched", source)`;
  2. se `enriched_path.exists()` e non `force` → skip (idempotenza);
  3. altrimenti: `ArticleRepository.load(parsed_path)` →
     `ArticleCleaner.clean(article)` per ciascun articolo →
     `ArticleContextualizerAgent.contextualize(article)` → assembla
     `EnrichedArticle(contexts=...)` → `EnrichedArticleRepository.write(enriched)`.
  - La pulizia (`ArticleCleaner`) avviene inline nel flusso; il layer `cleaned`
    non è più scritto su disco come stadio separato.
- **`DataPreparationPipelineBuilder(config: IngestorConfig, layer_resolver:
  LayerResolver)`**: costruisce `ArticleContextualizerAgent.from_yaml("article_contextualizer",
  config.agents_dir)` internamente; setter fluent `with_article_repository`,
  `with_enriched_article_repository`, `with_article_cleaner`,
  `with_article_contextualizer`; `build()` usa controlli espliciti `is not None`.

### Deprecazione di `orchestrators/knowledge_cleaning/`

- Il package `knowledge_cleaning/` è convertito in uno **shim di deprecazione**:
  re-esporta `DataPreparationPipeline` as `CleaningPipeline` e
  `DataPreparationPipelineBuilder` as `CleaningPipelineBuilder` con un
  `DeprecationWarning`. Garantisce compatibilità con codice che importava
  la vecchia interfaccia senza rompere nulla.

### `orchestrators/quiz_preparation/` — `QuizDataPreparationPipeline` + `QuizDataPreparationPipelineBuilder`

- **`QuizDataPreparationPipeline.run(force: bool = False)`**:
  1. risolve `enriched_path = layer_resolver.path("enriched", "quiz")`;
  2. se `enriched_path.exists()` e non `force` → skip;
  3. altrimenti: `QuizBankRepository.load(parsed_path)`;
  4. raccoglie i `image_filename` unici da tutte le sotto-domande (dedup in-memory);
  5. per ogni filename unico: `RoadSignDescriberAgent.describe(quiz_images_dir / filename)`
     → `ImageDescription`; le domande prive di immagine hanno
     `image_description = None`;
  6. assembla `list[EnrichedQuizMainQuestion]` con `image_description` inline
     per ogni sotto-domanda → `EnrichedQuizBankRepository.write(enriched)`.
  - Dedup: riduce le chiamate al vision agent da ~4.148 (totale sotto-domande
    con immagine) a ~427 (immagini uniche). Ogni sotto-domanda con la stessa
    immagine riceve la stessa descrizione.
  - Immagine non trovata su disco → `logger.warning` + `image_description = None`
    (non blocca la pipeline).
- **`QuizDataPreparationPipelineBuilder(config: IngestorConfig, layer_resolver:
  LayerResolver)`**: costruisce `RoadSignDescriberAgent.from_yaml("road_sign_describer",
  config.agents_dir)` internamente; setter fluent `with_quiz_bank_repository`,
  `with_enriched_quiz_bank_repository`, `with_road_sign_describer`; `build()`
  con controlli `is not None`.

## Test

- `tests/guidami_ai_patente_ingestor/agents/test_article_contextualizer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: articolo abrogato →
  ritorna `{}` senza chiamare il modello; variabili prompt costruite correttamente;
  output `dict[int, str]` via PydanticAI (no parsing manuale).
- `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: output `ImageDescription`
  via PydanticAI; percorso immagine passato come `BinaryContent`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  round-trip `write`/`load` su `EnrichedArticle`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_quiz_bank_repository.py` —
  round-trip `write`/`load` su `EnrichedQuizMainQuestion`.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_preparation/test_data_preparation_pipeline.py` —
  unit con `Mock`: clean → contextualize → write enriched; skip se enriched
  esiste; `force=True` rigenera; articoli abrogati saltati dall'agente.
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_preparation/test_quiz_data_preparation_pipeline.py` —
  unit con `Mock`: solo i filename unici descritti; enriched bank con
  `image_description` inline; immagine mancante → warning + `None`; `force=True`.
