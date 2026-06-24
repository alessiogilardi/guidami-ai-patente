# Ingestor — Data preparation

Riferimento progettazione: `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--article-contextual-embedding.md`,
`plans/ingest--quiz-image-descriptions.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md` (knowledge,
ricostruito su flowstep in SP05),
`plans/ingest--orchestrator/06-quiz-preparation-flow.md` (quiz, costruito da
zero su flowstep in SP06).

Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI, [flowstep_toolkit.md](flowstep_toolkit.md)
per `context_keys` condivise, [quiz_pipelines.md](quiz_pipelines.md) per la
catena dei modelli quiz e il dettaglio di `QuizMapper`/`services/quiz/`.

Due aree di preparation offline, idempotenti, che precedono le pipeline/flow di
indexing. Producono gli artefatti `enriched` da cui l'indexing legge.

- **corpus normativo (knowledge)**: ricostruito in SP05 come **due Flow
  flowstep lineari per-source** (`clean`, `enrich`) + runner generico
  `run_preparation`. Sostituisce la precedente `DataPreparationPipeline`
  (rimossa).
- **quiz bank**: costruito **da zero** in SP06 come **un Flow flowstep
  lineare** (`cleaned` → `enriched`), riusando il runner `run_preparation` di
  SP05. Non è un refactor: non esisteva alcuna pipeline di quiz preparation
  prima di SP06 (verificato su git history). Sostituisce concettualmente il
  vecchio riferimento `QuizDataPreparationPipeline` descritto in versioni
  precedenti di questo documento — quel componente non è mai stato
  implementato nel codice attuale.

## Topologia

```
parsed ──[clean flow: Load→Clean→Write]────▶ cleaned ──[enrich flow: Load→Contextualize→Write]──▶ enriched ──[knowledge_indexing flow]──▶ DB
cleaned ──[quiz_preparation flow: Load→Enrich→Write]──────────────────────────────────────────────▶ enriched ──[quiz_indexing flow]───────────▶ DB
```

Per il quiz bank il layer `parsed`/stadio di "clean" non esiste: l'input del
flow di preparation è già il layer `cleaned` (`data/cleaned/quiz-patente-ab/quiz-patente-ab.json`),
quindi un solo flow basta (a differenza del knowledge, che ne richiede due).

L'enrichment LLM (costoso, offline) è separato dall'indexing (ri-eseguibile a
costo zero su `enriched`). Knowledge e quiz preparation sono idempotenti a
**livello di file**: saltano se l'output del rispettivo layer esiste; un flag
`force` (applicato dal chiamante via `run_preparation`) forza la
rigenerazione. Per il quiz, questo è un limite noto e accettato: aggiungere un
nuovo enricher richiede di rigenerare l'intero file (incluse le chiamate
vision, le più costose) — un checkpoint per-enricher è rimandato a quando
servirà davvero.

## Knowledge preparation (SP05) — due Flow per-source + runner generico

Pattern **per-source** (coerente con SP03/04, già documentato): una run per
source, `source` iniettata negli step `Load*`/`Write*` al momento della
factory. **Nessuna** chiave `SOURCE` nel `FlowContext` e nessun loop sulle
source dentro flow/runner — il loop, se serve, è responsabilità del chiamante
(CLI, atteso in SP07).

### `orchestrators/knowledge_flows.py` — due flow factory

```python
def build_knowledge_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow
```
Catena: `LoadParsedArticlesStep` → `CleanArticlesStep` → `WriteCleanedStep`.
Layer: input = `config.knowledge_preparation.input_layer` (`"parsed"`),
output = costante privata del modulo `_CLEANED_LAYER = "cleaned"`.

```python
def build_knowledge_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow
```
Catena: `LoadCleanedArticlesStep` → `ContextualizeStep` → `WriteEnrichedStep`.
Layer: input = `_CLEANED_LAYER`, output = `config.knowledge_preparation.output_layer`
(`"enriched"`); solleva `ValueError` se `output_layer` non configurato. Istanzia
l'agente via `ArticleContextualizerAgent.from_yaml("article_contextualizer",
config.agents_dir)` e lo inietta in `ContextualizeStep`.

**Decisioni:**
- Entrambe le factory validano `source` contro
  `config.knowledge_preparation.sources` → `ValueError(f"Unknown source
  '{source}'. ...")` se non riconosciuta (stesso pattern di
  `build_knowledge_indexing_flow`, SP03).
- **Nessuna dipendenza da `embedding_client`/`postgres_client`**: lo stadio di
  preparation non fa embed né store, a differenza dell'indexing.
- **Layer intermedio `"cleaned"` come costante privata del modulo**, non un
  nuovo campo di `PipelineLayerConfig`: `knowledge_preparation` espone solo
  `input_layer`/`output_layer`, insufficiente per un flow a due stadi con
  layer intermedio. Evita di aggiungere un campo di configurazione per un
  valore che oggi non varia mai.
- I due flow sono **lineari e puri**: nessuna logica di idempotenza/skip al
  loro interno — quella vive nel runner.

### `orchestrators/preparation_runner.py` — `run_preparation`

```python
def run_preparation(flow: Flow, out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        logger.info(f"{out_path} already exists, skipping")
        return
    flow.run()
```

- Helper **a singola source**: incapsula solo lo skip idempotente. Nessun
  loop sulle source, nessuna iniezione di `source` nel `FlowContext` (la
  `source` è già fissata negli step alla factory).
- Riceve `out_path` già risolto dal chiamante (tipicamente via
  `LayerResolver.path(layer, source)`), così lo stesso runner serve sia il
  flow `clean` (out = layer `cleaned`) sia il flow `enrich` (out = layer
  `enriched`), e per SP06 anche il flow di quiz preparation.
- **Condiviso con SP06** (quiz preparation flow, implementato): nessuna
  logica domain-specific knowledge al suo interno.

### `orchestrators/steps/knowledge/` — sei step di dominio (estensione SP05)

Aggiunti ai quattro step di indexing già documentati in
[knowledge_pipelines.md](knowledge_pipelines.md). Tutti step sottili: get →
delega a un servizio/agente/mapper esistente → put, nessuna logica di dominio
nello step stesso.

- **`LoadParsedArticlesStep`**: iniettati `article_repository`,
  `layer_resolver`, `input_layer`, `source`. `execute`: risolve il path via
  `layer_resolver.path(input_layer, source)`, `repository.load(path)` →
  `put(PARSED_ARTICLES, list[Article])`. `required=set()` (primo step del
  flow `clean`), `produced={PARSED_ARTICLES}`.
- **`CleanArticlesStep`**: iniettato `article_cleaner: ArticleCleaner`.
  `execute`: legge `PARSED_ARTICLES`, applica `ArticleCleaner.clean` a ogni
  articolo, `put(CLEANED_ARTICLES, ...)`. `required={PARSED_ARTICLES}`,
  `produced={CLEANED_ARTICLES}`.
- **`WriteCleanedStep`** (sink): iniettati `article_repository`,
  `layer_resolver`, `output_layer`, `source`. `execute`: legge
  `CLEANED_ARTICLES`, risolve il path e chiama
  `ArticleRepository.write(articles, path)`. `required={CLEANED_ARTICLES}`,
  `produced=set()`.
- **`LoadCleanedArticlesStep`**: stessa forma di `LoadParsedArticlesStep` ma
  legge dal layer `cleaned` (`input_layer` iniettato = `"cleaned"`).
  `required=set()`, `produced={CLEANED_ARTICLES}` — primo step del flow
  `enrich`.
- **`ContextualizeStep`**: iniettato
  `article_contextualizer_agent: ArticleContextualizerAgent`. `execute`: legge
  `CLEANED_ARTICLES`, per ogni articolo chiama
  `agent.contextualize(article)` (ritorna `dict[int, str]`, `{}` per articoli
  abrogati) poi `EnrichedArticleMapper.from_article_to_enriched_article(article,
  contexts)`, `put(ENRICHED_ARTICLES, list[EnrichedArticle])`.
  `required={CLEANED_ARTICLES}`, `produced={ENRICHED_ARTICLES}`.
- **`WriteEnrichedStep`** (sink): iniettati `enriched_article_repository`,
  `layer_resolver`, `output_layer`, `source`. `execute`: legge
  `ENRICHED_ARTICLES`, risolve il path e chiama
  `EnrichedArticleRepository.write(articles, path)`.
  `required={ENRICHED_ARTICLES}`, `produced=set()`.

Gli step `Load*`/`Write*` ricevono `layer_resolver`/layer/`source` nel
costruttore e risolvono il path via `layer_resolver.path(layer, source)` —
mai leggono `source` dal `FlowContext`.

### `mappers/knowledge/` — nuovo package, `EnrichedArticleMapper`

- Package nuovo (prima esisteva solo `mappers/quiz/`). Un solo mapper:
  **`EnrichedArticleMapper`** — statico, metodo verboso
  `from_article_to_enriched_article(article: Article, contexts: dict[int, str])
  -> EnrichedArticle`. Copia `number`, `title`, `text`, `paragraphs`, `url`,
  `scraped_at`, `repealed` da `Article` e imposta `contexts`. Sostituisce la
  costruzione inline di `EnrichedArticle` che viveva nella `DataPreparationPipeline`
  rimossa.

### `context_keys.py` — chiavi aggiunte da SP05

Estensione **additiva**: `PARSED_ARTICLES = "parsed_articles"` (input del
flow `clean`), `CLEANED_ARTICLES = "cleaned_articles"` (output `clean` /
input `enrich`). Riusa `ENRICHED_ARTICLES` (già definita da SP02/03, ora
prodotta anche dal flow `enrich`, non solo letta dall'indexing). Nessuna
chiave `SOURCE`: la source non passa mai dal context, è fissata alla factory.
Vedi [flowstep_toolkit.md](flowstep_toolkit.md) per il vocabolario completo.

### Cosa NON è (ancora) cambiato

- Nessun cutover dell'entry point CLI: `prepare_knowledge_main.py` (con la
  vecchia `DataPreparationPipeline`) era già stato rimosso in SP03-bis; un
  nuovo entry point che invoca `build_knowledge_cleaning_flow` +
  `build_knowledge_enrichment_flow` + `run_preparation` **non esiste ancora**
  — atteso in SP07.
- Nessuna rimozione di pipeline legacy residue: fuori scope di SP05.

### Modelli ingestor per il quiz bank (rinominati in SP04-bis)

`QuizBankModel`/`QuizBankItemModel` (layer `cleaned`) ed
`EnrichedQuizModel`/`EnrichedQuizItemModel` (layer `enriched`) vivono in
`guidami_ai_patente_ingestor/models/quiz/` — non in `entities/` (sono DTO non
persistiti, non righe DB). `EnrichedQuizItemModel` aggiunge
`image_description: str | None` rispetto a `QuizBankItemModel`. Dettaglio
completo della catena dei modelli e del `QuizMapper` consolidato in
[quiz_pipelines.md](quiz_pipelines.md).

### `repositories/enriched_article_repository.py` — `EnrichedArticleRepository`

- `load(path: Path) -> list[EnrichedArticle]` e
  `write(articles: list[EnrichedArticle], path: Path) -> None` — stesso pattern
  di `ArticleRepository`, ma opera sul tipo `EnrichedArticle` (da `commons`).
- `write` crea directory mancanti e serializza con `ensure_ascii=False, indent=2`.

### `repositories/json/enriched_quiz_bank_repository.py` — `EnrichedQuizBankRepository`

- `load(path: Path) -> list[EnrichedQuizModel]` e
  `write(questions: list[EnrichedQuizModel], path: Path) -> None`.
- Stesso pattern dei repository JSON esistenti (`JsonRepository[T]` generica).

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

## Quiz preparation (SP06) — un Flow + runner generico (riuso SP05)

> **Greenfield, non un refactor**: prima di SP06 non esisteva alcuna pipeline
> di quiz preparation né un entry point dedicato (`RoadSignDescriberAgent`
> esisteva già ma aveva zero chiamanti). Il flow descritto qui è stato
> costruito da zero su flowstep, non sostituisce codice preesistente.

Catena: `LoadQuizStep` → `EnrichQuizStep` → `WriteEnrichedQuizStep`, chiavi
`CLEANED_QUIZ` → `ENRICHED_QUIZ`. Un solo flow (non due come il knowledge)
perché l'input è già il layer `cleaned` — non esiste un layer `parsed`
separato né uno stadio di "clean" per il quiz bank.

```python
def build_quiz_preparation_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

in `orchestrators/quiz_flows.py` (file additivo, condiviso con
`build_quiz_indexing_flow` di SP04). Riusa **lo stesso runner** di SP05
(`run_preparation(flow, out_path, force)`), invocato dal chiamante con
`out_path = layer_resolver.path(config.quiz_preparation.output_layer, "quiz")`.

Dettaglio completo di step, enrichment Open/Closed
(`QuizEnricher`/`QuizEnrichmentService`/`ImageDescriptionEnricher`) e
decisioni della factory in [quiz_pipelines.md](quiz_pipelines.md).

### Dedup immagini (`ImageDescriptionEnricher`)

Stessa motivazione del precedente componente di enrichment quiz (mai
implementato come pipeline a parte, ma il principio era già nel piano
`ingest--quiz-image-descriptions.md`): raccogliere i `sub.image` **unici**
prima di chiamare la vision LLM riduce drasticamente il numero di chiamate
(da una per sotto-domanda con immagine a una per immagine distinta). Ogni
sotto-domanda con la stessa immagine riceve la stessa descrizione.
Immagine non trovata su disco o `describe()` che lancia → `logger.warning` +
`image_description = None` (non blocca l'enrichment delle altre domande).

### Cosa NON è (ancora) cambiato (SP06)

- Nessun entry point CLI dedicato: il flow non è wired a nessuno script —
  atteso in SP07.
- `agents_dir`/yaml dell'agente (`road_sign_describer.yaml`) non cambiati.

## Test

Per i test del knowledge preparation flow (SP05) e del quiz preparation flow
(SP06): step, mapper, flow factory, runner, service/enricher — vedi
[tests.md](tests.md).

Test rimasti per i componenti condivisi:

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
  round-trip `write`/`load` su `EnrichedQuizModel`.
