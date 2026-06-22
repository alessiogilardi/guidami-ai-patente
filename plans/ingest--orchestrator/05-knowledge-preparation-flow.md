# SP05 — Flow knowledge preparation + runner generico

> ⚠️ **Decisione architetturale 2026-06-22 — PER-SOURCE, una run per source.**
> Coerente con SP03 (già implementato così): la preparazione gira **una source per esecuzione**
> via CLI `--source` obbligatoria (`uv run prepare-knowledge --source cds`), **non** un runner che
> cicla `for source in sources` internamente. Implicazioni che superano il corpo qui sotto:
> - **niente `SOURCE` nel context** e **niente loop di source** nel runner: la `source` è iniettata
>   negli step (`Load*`/`Write*`) al momento della factory, come in SP03
>   (`LoadEnrichedArticlesStep(source=...)`).
> - `run_preparation` si riduce a un helper **per singola source**: solo lo skip idempotente
>   (`out.exists() and not force`) + `flow.run()`. Il loop su più source, se serve, lo fa il
>   chiamante (CLI) — ma la scelta presa è una run per source.
> - `context_keys`: l'indexing **non** usa più `ARTICLES_BY_SOURCE` (rimossa in SP03); la prep
>   produce/consuma `PARSED_ARTICLES`/`CLEANED_ARTICLES`/`ENRICHED_ARTICLES` (liste piatte, una source).
> - `sources: list[str]` su `PipelineLayerConfig` resta il **catalogo** delle source valide
>   (validazione dell'argomento `--source`), non l'elenco da ciclare.

## Scopo singolo
Ricostruire la preparazione del corpus (`parsed` → `cleaned` → `enriched`) come **due Flow lineari**
+ introdurre il **runner generico** che incapsula idempotenza/loop-source/checkpoint (oggi inline
in `_prepare_source`/`_get_cleaned_articles`). Il runner è condiviso con SP06.

## Dipende da
SP02 (`context_keys`). Non usa `EmbedStep`. Parallelo a SP03/04.

## Mappatura Flow (due flow distinti)
- **clean**: `LoadParsedArticlesStep` → `CleanArticlesStep` → `WriteCleanedStep`
- **enrich**: `LoadCleanedArticlesStep` → `ContextualizeStep` → `WriteEnrichedStep`

I Flow sono **lineari e puri**; idempotenza/skip/loop **non** sono Step → vivono nel runner.

## Stato attuale (riferimento)
`orchestrators/knowledge_preparation/data_preparation_pipeline.py`:
- `run(force)` → loop `("cds","cap")` → `_prepare_source`;
- `_prepare_source`: skip se `enriched` esiste (e non force);
- `_get_cleaned_articles`: checkpoint `cleaned` (skip se esiste), altrimenti `ArticleCleaner.clean`;
- `_enrich`: per articolo `ArticleContextualizerAgent.contextualize` → costruisce `EnrichedArticle`.

## Componenti

### Nuovi (runner generico) — `orchestrators/preparation_runner.py`
```python
def run_preparation(
    flow: Flow, sources: Sequence[str], output_layer: str,
    layer_resolver: LayerResolver, force: bool,
) -> None:
    for source in sources:
        out = layer_resolver.path(output_layer, source)
        if out.exists() and not force:
            logger.info(f"{source}: {out} already exists, skipping"); continue
        flow.run({SOURCE: source})
```
Knowledge prep = **due** chiamate: clean→layer `cleaned`, enrich→layer `enriched`.
Il checkpoint `cleaned` intermedio è gestito dal runner (clean prima, enrich poi),
**oppure** lo step clean stesso fa skip-se-esiste — scegliere in implementazione:
preferenza = due `run_preparation` separate, una per layer, così lo skip è uniforme.

### Nuovi (step di dominio sottili) — `orchestrators/steps/knowledge/`
- `LoadParsedArticlesStep` (`ArticleRepository.load`, legge `SOURCE`) → `produced={PARSED_ARTICLES}`.
- `CleanArticlesStep` (delega `ArticleCleaner.clean`) → `{PARSED_ARTICLES}→{CLEANED_ARTICLES}`.
- `WriteCleanedStep` (`ArticleRepository.write` su layer `cleaned`, legge `SOURCE`+`CLEANED_ARTICLES`).
- `LoadCleanedArticlesStep` → `produced={CLEANED_ARTICLES}`.
- `ContextualizeStep` (delega `ArticleContextualizerAgent.contextualize` + `EnrichedArticleMapper`)
  → `{CLEANED_ARTICLES}→{ENRICHED_ARTICLES}`.
- `WriteEnrichedStep` (`EnrichedArticleRepository.write` su layer `enriched`).

Tutti gli step leggono `SOURCE` dal context per risolvere il path via `LayerResolver`.

### Nuovi (mapper estratto) — `mappers/knowledge/enriched_article_mapper.py`
- **`EnrichedArticleMapper`**: `Article + contexts → EnrichedArticle`. Sostituisce `_enrich`
  (oggi costruzione inline di `EnrichedArticle`). Statico/verboso come gli altri mapper del progetto.

### Nuovi (flow factory) — in `orchestrators/knowledge_flows.py`
- `build_knowledge_cleaning_flow(...) -> Flow`
- `build_knowledge_enrichment_flow(...) -> Flow`

### Modificati
- `mappers/knowledge/__init__.py` (mapper), `orchestrators/steps/knowledge/__init__.py` (step),
  `orchestrators/__init__.py` (factory + runner): re-export.
- **`context_keys.py`** (⚠️ edit condiviso con SP03/SP06): aggiungere in modo **additivo**
  `SOURCE`, `PARSED_ARTICLES`, `CLEANED_ARTICLES`; **riusare** `ENRICHED_ARTICLES` (già definita
  da SP02, consumata da `ContextualizeStep`/`WriteEnrichedStep`); **non rimuovere**
  `ARTICLES_BY_SOURCE` aggiunta da SP03. Coordinare il merge (file toccato anche da SP03/SP06).
- **`IngestorConfig` / `PipelineLayerConfig`** (⚠️ condiviso con SP03): il runner riceve `sources`
  da `config.knowledge_preparation.sources` — il nuovo campo `sources: list[str]` su
  `PipelineLayerConfig` introdotto da SP03 (default knowledge_* = `["cds","cap"]`). Niente lista
  hardcoded nel runner/CLI.
- `prepare_knowledge_main.py` legacy: lasciato fino a SP07.

## TDD
- **Runner**: skip se output esiste; `force=True` rigenera; itera tutte le source; `flow.run({SOURCE: s})` chiamato.
- `EnrichedArticleMapper`: `Article + contexts` → `EnrichedArticle` con tutti i campi copiati + `contexts`.
- `CleanArticlesStep` / `ContextualizeStep`: delega corretta (fake cleaner/contextualizer) + contratto chiavi.
- Flow factory clean/enrich: `build(validate=True)` senza ERROR; `required_input_keys == {SOURCE}`.

## Done criteria
- Due flow + runner verdi; `DataPreparationPipeline`/builder non ancora rimossi (SP07).
- Idempotenza/skip preservata (test runner) — comportamento identico al pipeline attuale.
