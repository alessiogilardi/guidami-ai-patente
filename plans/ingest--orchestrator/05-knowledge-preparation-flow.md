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
+ introdurre il **runner generico** che incapsula l'idempotenza/skip per singola source
(oggi inline in `_prepare_source`/`_get_cleaned_articles`, ora recuperabile solo dalla git history
dopo la rimozione in SP03-bis). Il runner è condiviso con SP06.

## Dipende da
SP02 (`context_keys`). Non usa `EmbedStep`. Parallelo a SP03/04.

## Mappatura Flow (due flow distinti)
- **clean**: `LoadParsedArticlesStep` → `CleanArticlesStep` → `WriteCleanedStep`
- **enrich**: `LoadCleanedArticlesStep` → `ContextualizeStep` → `WriteEnrichedStep`

I Flow sono **lineari e puri**; idempotenza/skip/loop **non** sono Step → vivono nel runner.

## Stato attuale (riferimento)
⚠️ Il package legacy `orchestrators/knowledge_preparation/` (con `data_preparation_pipeline.py`)
e l'entrypoint `prepare_knowledge_main.py` sono stati **rimossi da SP03-bis**: non esistono più su
disco. Il comportamento storico da preservare (loop source → skip-se-`enriched`-esiste → checkpoint
`cleaned` → `clean` → `enrich`) va recuperato dalla **git history**, non da file esistenti.

I componenti delegati **sopravvissuti** (da riusare, firme reali):
- `services/knowledge/article_cleaner.py` → `ArticleCleaner.clean(article: Article) -> Article`.
- `agents/article_contextualizer_agent.py` → `ArticleContextualizerAgent.contextualize(article: Article) -> dict[int, str]`
  (ritorna `{}` per articoli repealed); si costruisce con `ArticleContextualizerAgent.from_yaml(name, config.agents_dir)`.
- `repositories/` → `ArticleRepository` (`JsonRepository[Article]`) e `EnrichedArticleRepository`
  (`JsonRepository[EnrichedArticle]`), entrambi con `load(path) -> list[T]` e `write(items, path) -> None`.
- `services/layer_resolver.py` → `LayerResolver.path(layer, source) -> Path`.

## Componenti

### Nuovi (runner generico) — `orchestrators/preparation_runner.py`
Helper a **singola source**, coerente con l'header per-source: nessun loop interno sulle source,
nessun `flow.run({SOURCE: source})` (la `source` è già iniettata negli step alla factory).
Riceve l'`out_path` già risolto dal chiamante e applica solo lo skip idempotente:
```python
def run_preparation(flow: Flow, out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        logger.info(f"{out_path} already exists, skipping")
        return
    flow.run()
```
Knowledge prep = **due** chiamate per source: clean→layer `cleaned`, enrich→layer `enriched`.
Il **loop sulle source** lo fa la **CLI/chiamante** (`for source in config.knowledge_preparation.sources`),
non il runner: per ogni source la CLI costruisce i due flow per-source, risolve i due `out_path` via
`LayerResolver.path(...)` e invoca `run_preparation` due volte. Lo skip è così uniforme su entrambi i layer.

### Nuovi (step di dominio sottili) — `orchestrators/steps/knowledge/`
- `LoadParsedArticlesStep` (`ArticleRepository.load`) → `required=set()`, `produced={PARSED_ARTICLES}`.
- `CleanArticlesStep` (delega `ArticleCleaner.clean`) → `{PARSED_ARTICLES}→{CLEANED_ARTICLES}`.
- `WriteCleanedStep` (`ArticleRepository.write` su layer `cleaned`, legge `CLEANED_ARTICLES`).
- `LoadCleanedArticlesStep` → `required=set()`, `produced={CLEANED_ARTICLES}`.
- `ContextualizeStep` (delega `ArticleContextualizerAgent.contextualize` + `EnrichedArticleMapper`)
  → `{CLEANED_ARTICLES}→{ENRICHED_ARTICLES}`.
- `WriteEnrichedStep` (`EnrichedArticleRepository.write` su layer `enriched`, legge `ENRICHED_ARTICLES`).

Gli step **non** leggono `SOURCE` dal context. Come in SP03 (`LoadEnrichedArticlesStep(source=...)`),
la `source` — insieme a `layer_resolver` e `input_layer`/`output_layer` — è iniettata nel `__init__`
degli step `Load*`/`Write*` alla factory; lo step risolve il path via `layer_resolver.path(layer, source)`.
Di conseguenza i `Load*` hanno `required=set()` (non dipendono da nessuna chiave di context).

### Nuovi (mapper estratto) — `mappers/knowledge/enriched_article_mapper.py`
⚠️ `mappers/knowledge/` è un **package NUOVO** da creare (oggi esiste solo `mappers/quiz/`):
includere `__init__.py` con il re-export del mapper.
- **`EnrichedArticleMapper`**: `Article + contexts → EnrichedArticle`. Sostituisce `_enrich`
  (oggi costruzione inline di `EnrichedArticle`). Copia i campi comuni (`number`, `title`, `text`,
  `paragraphs`, `url`, `scraped_at`, `repealed`) e imposta `contexts`. Statico/verboso come gli
  altri mapper del progetto.

### Nuovi (flow factory) — in `orchestrators/knowledge_flows.py`
Firme allineate a SP03 (`build_knowledge_indexing_flow`), per-source, **senza** embedding/db:
- `build_knowledge_cleaning_flow(config, layer_resolver, source, validate=False) -> Flow`
- `build_knowledge_enrichment_flow(config, layer_resolver, source, validate=False) -> Flow`

Entrambe **non** ricevono `embedding_client`/`postgres_client` (nessun embed/store nello stadio prep).
Entrambe validano `source` contro `config.knowledge_preparation.sources` e sollevano
`ValueError(f"Unknown source '{source}'. ...")` su source sconosciuta (stesso pattern di SP03,
incluso il `cast(Literal["cds","cap"], source)` se serve). La factory `enrich` istanzia l'agente via
`ArticleContextualizerAgent.from_yaml(name, config.agents_dir)` e lo inietta nel `ContextualizeStep`.
La `source` viene iniettata nei costruttori degli step `Load*`/`Write*`.

### Modificati
- `mappers/knowledge/__init__.py` (mapper), `orchestrators/steps/knowledge/__init__.py` (step),
  `orchestrators/__init__.py` (factory + runner): re-export.
- **`context_keys.py`** (⚠️ edit condiviso con SP03/SP06): aggiungere in modo **additivo** SOLO
  `PARSED_ARTICLES` e `CLEANED_ARTICLES`; **riusare** `ENRICHED_ARTICLES` (già definita da SP02,
  consumata da `ContextualizeStep`/`WriteEnrichedStep`). **Nessuna** chiave `SOURCE` (la source non
  passa dal context). Coordinare il merge (file toccato anche da SP03/SP06).
- **`IngestorConfig` / `PipelineLayerConfig`** (⚠️ condiviso con SP03): la CLI cicla `sources`
  da `config.knowledge_preparation.sources` — il campo `sources: list[str]` su `PipelineLayerConfig`
  introdotto da SP03 (default knowledge_* = `["cds","cap"]`). Niente lista hardcoded nel runner/CLI.

## Punto aperto / decisione di layer
`config.knowledge_preparation` (`PipelineLayerConfig`) espone solo `input_layer="parsed"` e
`output_layer="enriched"`, ma la prep richiede **due** flow con un layer intermedio `cleaned`.
Il layer `cleaned` esiste già in `IngestorConfig.layers` ma **non** è espresso nella
`PipelineLayerConfig` di prep. Risoluzione proposta (esplicita, **senza nuovo campo di config**):
- **clean**: input = `knowledge_preparation.input_layer` (`parsed`), output = costante `"cleaned"`.
- **enrich**: input = costante `"cleaned"`, output = `knowledge_preparation.output_layer` (`enriched`).

Raccomandazione: trattare `"cleaned"` come costante intermedia condivisa dalle due factory (non
serve aggiungere un campo `intermediate_layer` a `PipelineLayerConfig`). Se in futuro il layer
intermedio dovesse variare per pipeline, valutare allora l'aggiunta del campo.

## TDD
- **Runner**: skip se `out_path` esiste (e non `force`) → `flow.run()` **non** chiamato; con
  `force=True` rigenera chiamando `flow.run()`. Nessun loop su sources, nessun `flow.run({SOURCE: s})`.
- `EnrichedArticleMapper`: `Article + contexts` → `EnrichedArticle` con tutti i campi copiati + `contexts`.
- `CleanArticlesStep` / `ContextualizeStep`: delega corretta (fake cleaner/contextualizer) + contratto chiavi.
- Flow factory clean/enrich: `build(validate=True)` senza ERROR;
  `FlowValidator().validate(flow).required_input_keys == set()` (i `Load*` hanno `required=set()`);
  `source` sconosciuta → `ValueError`.

## Done criteria
- Due flow factory (clean/enrich) + runner per-source verdi.
- Idempotenza/skip preservata (test runner): skip se output esiste, `force` rigenera.
- Comportamento identico al pipeline storico (riferimento: git history, già rimosso da SP03-bis).
