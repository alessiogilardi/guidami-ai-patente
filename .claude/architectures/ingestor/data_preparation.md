# Ingestor — Data preparation

Riferimento progettazione: `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--article-contextual-embedding.md`,
`plans/ingest--quiz-image-descriptions.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md` (knowledge,
ricostruito su flowstep in SP05),
`plans/ingest--orchestrator/06-quiz-preparation-flow.md` (quiz, costruito da
zero su flowstep in SP06, poi sostituito da SP09),
`plans/ingest--orchestrator/08-generic-map-to-step.md` (generificazione
`LoadJsonStep`/`MapStep`/`WriteJsonStep`),
`plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md` (flatten+dedup
quiz spostato a preparation, layer `parsed` introdotto per il quiz).

Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI, [flowstep_toolkit.md](flowstep_toolkit.md)
per `context_keys` condivise e i building block generici (`LoadJsonStep`/
`MapStep`/`WriteJsonStep`/`EnrichDataStep`), [quiz_pipelines.md](quiz_pipelines.md)
per la catena dei modelli quiz e il dettaglio di `QuizMapper`/`services/quiz/`.

Due aree di preparation offline, idempotenti, che precedono le pipeline/flow di
indexing. Producono gli artefatti `enriched` da cui l'indexing legge.

- **corpus normativo (knowledge)**: ricostruito in SP05 come **due Flow
  flowstep lineari per-source** (`clean`, `enrich`) + runner generico
  `run_preparation`. Sostituisce la precedente `DataPreparationPipeline`
  (rimossa).
- **quiz bank**: costruito **da zero** in SP06 come un singolo Flow
  (`cleaned` → `enriched`), poi **ristrutturato in SP09** a specchio della
  topologia knowledge: oggi sono **due Flow flowstep lineari**
  (`build_quiz_cleaning_flow`: `parsed` → `cleaned`, con flatten+dedup;
  `build_quiz_enrichment_flow`: `cleaned` → `enriched`), entrambi via il
  runner generico `run_preparation`. Il flow di enrichment è stato poi
  refattorizzato (vedi sotto) per usare i building block generici `MapStep`/
  `EnrichDataStep` al posto degli step/service quiz-specific.

## Topologia

```
parsed ──[knowledge_cleaning flow: Load→Map(clean)→Write]──▶ cleaned ──[knowledge_enrichment flow: Load→Contextualize→Write]──▶ enriched ──[knowledge_indexing flow]──▶ DB
parsed ──[quiz_cleaning flow: Load→Flatten(dedup)→Write]────▶ cleaned ──[quiz_enrichment flow: Load→Map(base)→Enrich→Write]────▶ enriched ──[quiz_indexing flow]────────▶ DB
```

Dal SP09 il quiz bank ha la **stessa topologia a tre layer** del knowledge
(`parsed` → `cleaned` → `enriched`), non più un solo layer di input: il layer
`parsed` (output diretto del parser PDF, struttura nested) è distinto dal
layer `cleaned` (flat, una riga per sotto-domanda, prodotto dal flatten+dedup
di `FlattenQuizStep`).

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
Catena: `LoadJsonStep("load_parsed_articles", model_class=ParsedArticleModel)` →
`MapStep("clean_articles", mapper=ArticleCleaner().execute)` →
`WriteJsonStep("write_cleaned", model_class=ParsedArticleModel)`. Layer: input =
`config.knowledge_preparation.input_layer` (`"parsed"`), output = costante
privata del modulo `_CLEANED_LAYER = "cleaned"`. **Generificato**: i precedenti
step dedicati `LoadParsedArticlesStep`/`CleanArticlesStep`/`WriteCleanedStep`
sono stati sostituiti dai building block generici `LoadJsonStep`/`MapStep`/
`WriteJsonStep` (vedi [flowstep_toolkit.md](flowstep_toolkit.md)) — non
esistono più come classi dedicate.

```python
def build_knowledge_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow
```
Catena: `LoadJsonStep("load_cleaned_articles", model_class=ParsedArticleModel,
output_key=CLEANED_ARTICLES)` →
`MapStep("map_article_to_enriched", ArticleMapper.from_parsed_to_enriched,
CLEANED_ARTICLES, ENRICHED_ARTICLES)` →
`EnrichDataStep("enrich_articles", [ContextEnricher(agent)], ENRICHED_ARTICLES,
ENRICHED_ARTICLES)` →
`WriteJsonStep("write_enriched", model_class=EnrichedArticleModel)`.
Layer: input = `_CLEANED_LAYER`, output = `config.knowledge_preparation.output_layer`
(`"enriched"`); solleva `ValueError` se `output_layer` non configurato. Istanzia
l'agente via `ArticleContextualizerAgent.from_yaml("article_contextualizer",
config.agents_dir)` e lo inietta in `ContextEnricher`.
`ContextualizeStep` (che combinava mapping + contestualizzazione in un unico step
domain-specific) è stato **rimosso** e sostituito dai building block generici
`MapStep` + `EnrichDataStep` — stesso schema già usato dall'enrichment quiz.

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

### `orchestrators/steps/knowledge/` — step preparation knowledge (aggiornato)

Tutti gli step preparation knowledge sono sostituiti dai generici
`LoadJsonStep`/`MapStep`/`WriteJsonStep`/`EnrichDataStep` (vedi sopra) —
**nessuna classe step dedicata** rimane in `steps/knowledge/` per il preparation
(il package ospita solo i tre step dell'indexing: `ChunkArticlesStep`,
`EmbedChunksStep`, `StoreChunksStep`).

`ContextualizeStep` (precedente step domain-specific preparation che combinava
base-map + chiamata all'agente in un'unica delega per item) è stato **rimosso**.
Sostituito da `MapStep("map_article_to_enriched", ArticleMapper.from_parsed_to_enriched)`
+ `EnrichDataStep("enrich_articles", [ContextEnricher(agent)])`.

### `services/knowledge/enrichers/context_enricher.py` — `ContextEnricher`

- Enricher domain-specific per la contestualizzazione per comma via LLM.
  Soddisfa `EnricherProtocol[EnrichedArticleModel, EnrichedArticleModel]` per
  struttura (nessuna ereditarietà esplicita) — stesso pattern di
  `ImageDescriptionEnricher`.
- `enrich(items: list[EnrichedArticleModel]) -> list[EnrichedArticleModel]`:
  chiama `_contextualize(article)` per ogni item e restituisce nuove istanze
  (immutabilità via `model_copy`).
- `_contextualize(article)`: delega la traduzione dominio↔DTO a
  `ArticleContextualizerMapper`:
  1. `mapper.from_enriched_article_to_request(article)` → `ArticleContextualizerRequest`
  2. `agent.run_sync(request)` → `ArticleContextualizerResponse`
  3. `mapper.from_response_to_enriched_article(article, response)` → nuovo `EnrichedArticleModel`
  In caso di eccezione: `logger.warning` + ritorna l'articolo originale con
  `contexts={}`, senza interrompere il batch (stessa tolleranza ai fallimenti di
  `ImageDescriptionEnricher`).
- Inietta `ArticleContextualizerAgent` e `ArticleContextualizerMapper` nel costruttore.
- Vive in `services/knowledge/enrichers/` — non in `orchestrators/steps/knowledge/`
  (nessuna dipendenza da `commons.flowstep`).

Gli step generici `LoadJsonStep`/`WriteJsonStep` ricevono `layer_resolver`/
layer/`source` nel costruttore e risolvono il path via
`layer_resolver.path(layer, source)` — mai leggono `source` dal `FlowContext`.

### `mappers/` — `ArticleMapper` (flat, non più sub-package `knowledge/`)

- **`ArticleMapper`** vive ora direttamente in `mappers/article_mapper.py`
  (non più in `mappers/knowledge/`). Statico, backbone delle trasformazioni
  1:1 della pipeline knowledge. Re-esportato da `mappers/__init__.py`.
  Tre metodi:
  - `from_parsed_to_enriched(article: ParsedArticleModel) -> EnrichedArticleModel`:
    copia i campi comuni, imposta `contexts={}` (valorizzato da `ContextEnricher`).
    Usato da `MapStep("map_article_to_enriched")` nell'enrichment flow.
  - `from_enriched_to_embeddable_chunk(model: EnrichedArticleModel, source: str,
    comma_index: int, raw_text: str) -> EmbeddableChunkModel`:
    costruisce un `EmbeddableChunkModel` per un singolo comma. Usato da
    `ArticleChunker.execute` al posto della costruzione inline precedente.
  - `from_embeddable_chunk_to_knowledge_chunk(model: EmbeddableChunkModel) -> KnowledgeChunk`:
    copia tutti i campi (incluso `embedding`) in `KnowledgeChunk` (entità
    DB-only). Usato da `MapStep("map_to_chunk_entity")` nell'indexing flow.

### `mappers/agents/` — `ArticleContextualizerMapper` e `RoadSignDescriberMapper`

Principio architetturale: la traduzione dominio↔DTO è responsabilità del mapper,
non dell'enricher né dell'agente. Vivono in `mappers/agents/`, re-esportati
da `mappers/agents/__init__.py`.

- **`ArticleContextualizerMapper`** (`mappers/agents/article_contextualizer_mapper.py`):
  - `from_enriched_article_to_request(article: EnrichedArticleModel) -> ArticleContextualizerRequest`:
    costruisce il DTO di input per l'agente dai campi dell'articolo
    (`title`, `text`, `paragraphs` formattati come stringa `"Comma {i}: ..."`)
  - `from_response_to_enriched_article(article: EnrichedArticleModel,
    response: ArticleContextualizerResponse) -> EnrichedArticleModel`:
    applica `model_copy(update={"contexts": response.contexts})` — immutabile.

- **`RoadSignDescriberMapper`** (`mappers/agents/road_sign_describer_mapper.py`):
  - `from_enriched_quiz_to_request(item: EnrichedQuizModel) -> RoadSignDescriberRequest`:
    costruisce il DTO di input (`topic`, `text`) dal modello quiz.
  - `from_response_to_enriched_quiz(item: EnrichedQuizModel,
    response: RoadSignDescriberResponse) -> EnrichedQuizModel`:
    applica `model_copy(update={"image_description": f"{response.name}. {response.description}"})`.


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

### Modelli ingestor per il quiz bank (un modello per layer, rinominati in SP09)

`ParsedQuizModel`/`ParsedQuizItemModel` (layer `parsed`, nested),
`CleanedQuizModel` (layer `cleaned`, flat) ed `EnrichedQuizModel` (layer
`enriched`, flat) vivono in `guidami_ai_patente_ingestor/models/quiz/` — non
in `entities/` (sono DTO non persistiti, non righe DB). `EnrichedQuizModel`
aggiunge `image_description: str | None` rispetto a `CleanedQuizModel`.
Dettaglio completo della catena dei modelli e del `QuizMapper` consolidato in
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

Sottoclasse di `BaseAgent[ArticleContextualizerRequest, ArticleContextualizerResponse]`
(`commons/agents/`). Sostituisce il precedente service `ArticleContextualizer` (rimosso).

- L'agente **non** ha logica di traduzione dominio↔DTO: riceve e restituisce
  DTO tipizzati (`ArticleContextualizerRequest` / `ArticleContextualizerResponse`).
  La traduzione da/a `EnrichedArticleModel` è responsabilità di
  `ArticleContextualizerMapper` (vedi sezione `mappers/agents/` sopra).
- Prompt YAML (`configs/agents/article_contextualizer.yaml`): variabili
  `$title`, `$text`, `$paragraphs` (corrispondono ai campi del request).
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory che fissa
  `output_type=ArticleContextualizerResponse`.
- L'output strutturato è gestito da PydanticAI via `output_type`; non è
  necessario parsare JSON manualmente né validare la risposta grezza.

### `agents/road_sign_describer_agent.py` — `RoadSignDescriberAgent`

Sottoclasse di `BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]`
(`commons/agents/`). Sostituisce il precedente service `RoadSignDescriber` (rimosso).

- L'agente riceve `RoadSignDescriberRequest(topic, text)` come input tipizzato;
  le immagini rimangono passate separatamente via parametro `images` (non entrano
  nel DTO). La traduzione da/a `EnrichedQuizModel` è responsabilità di
  `RoadSignDescriberMapper`.
- Prompt YAML (`configs/agents/road_sign_describer.yaml`): variabili `$topic`,
  `$text` (corrispondono ai campi del request).
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory che fissa
  `output_type=RoadSignDescriberResponse`.
- `RoadSignDescriberResponse(BaseModel, frozen=True)` — `name: str`, `description: str`
  — vive in `agents/dto/road_sign_describer/`. `ImageDescription` (precedente DTO
  con gli stessi campi in `models/quiz/`) è ora sostituita da questo response DTO;
  i due modelli condividono la stessa struttura ma sono concettualmente distinti
  (response dell'agente vs. modello di dominio).

## Quiz preparation — due Flow (SP09) + runner generico, enrichment refattorizzato sui building block generici

> **Storia**: introdotta da SP06 come un singolo Flow (`cleaned` → `enriched`,
> greenfield — prima di SP06 non esisteva alcuna pipeline di quiz
> preparation). **SP09** l'ha ristrutturata in due Flow a specchio del
> knowledge (`parsed` → `cleaned` → `enriched`), spostando il flatten+dedup
> nel nuovo stadio di cleaning. Il refactor attuale (vedi
> [quiz_pipelines.md](quiz_pipelines.md)) ha poi sostituito gli step/service
> quiz-specific dello stadio di enrichment (`EnrichQuizStep`,
> `QuizEnrichmentService`, `Protocol QuizEnricher` — tutti rimossi) con i
> building block generici `MapStep`/`EnrichDataStep` già usati altrove.

Due flow in `orchestrators/quiz_flows.py`:

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```
Catena: `LoadJsonStep("load_parsed_quiz", model_class=ParsedQuizModel)` →
`FlattenQuizStep("flatten_quiz")` →
`WriteJsonStep("write_cleaned_quiz", model_class=CleanedQuizModel)`. Chiavi
`PARSED_QUIZ` → `CLEANED_QUIZ`.

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```
Catena: `LoadJsonStep("load_cleaned_quiz", model_class=CleanedQuizModel)` →
`MapStep("map_cleaned_to_enriched", QuizMapper.from_cleaned_to_enriched)` →
`EnrichDataStep("enrich_quiz", [ImageDescriptionEnricher(...)], ENRICHED_QUIZ, ENRICHED_QUIZ)`
→ `WriteJsonStep("write_enriched_quiz", model_class=EnrichedQuizModel)`.
Chiavi `CLEANED_QUIZ` → `ENRICHED_QUIZ`.

Entrambi riusano **lo stesso runner** del knowledge
(`run_preparation(flow, out_path, force)`), invocato dal chiamante con
`out_path = layer_resolver.path(<layer>, "quiz")`.

Dettaglio completo di step, enrichment Open/Closed
(`EnrichDataStep`/`EnricherProtocol`/`ImageDescriptionEnricher`) e decisioni
della factory in [quiz_pipelines.md](quiz_pipelines.md).

### Dedup e traduzione dominio↔DTO (`ImageDescriptionEnricher`)

`ImageDescriptionEnricher` usa `RoadSignDescriberMapper` per la traduzione
dominio↔DTO, coerentemente con `ContextEnricher`. Flusso per ogni
sotto-domanda con immagine:
1. `mapper.from_enriched_quiz_to_request(item)` → `RoadSignDescriberRequest`
2. `agent.run_sync(request, images=(image_path,))` → `RoadSignDescriberResponse`
3. `mapper.from_response_to_enriched_quiz(item, response)` → nuovo `EnrichedQuizModel`

**Chiave di dedup**: la cache delle descrizioni è indicizzata su
`(image, topic, text)` (tupla a 3 campi). Rispetto alla versione precedente
(solo `item.image`), la chiave allargata garantisce che la stessa immagine
con topic/testo diversi riceva descrizioni distinte — rispecchiando il fatto
che il prompt dell'agente include sia `$topic` sia `$text`.

Immagine non trovata su disco o errore nell'agente → `logger.warning` +
`image_description = None` (non blocca l'enrichment delle altre domande).
L'enricher soddisfa `EnricherProtocol[EnrichedQuizModel, EnrichedQuizModel]`
per struttura; nessuna ereditarietà esplicita.

### Cosa NON è (ancora) cambiato

- Nessun entry point CLI dedicato per i flow di quiz preparation/indexing:
  non sono ancora wired a nessuno script. `reset_quiz_db.py` resta
  disponibile.
- `agents_dir`/yaml dell'agente (`road_sign_describer.yaml`) non cambiati.

## Test

Per i test del knowledge preparation flow e del quiz preparation flow: step,
mapper, flow factory, runner, enricher — vedi [tests.md](tests.md).

Test rimasti per i componenti condivisi:

- `tests/guidami_ai_patente_ingestor/agents/test_article_contextualizer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: articolo abrogato →
  ritorna `{}` senza chiamare il modello; variabili prompt costruite correttamente;
  output `dict[int, str]` via PydanticAI (no parsing manuale).
- `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: output `ImageDescription`
  via PydanticAI; percorso immagine passato come `BinaryContent`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  round-trip `write`/`load` su `EnrichedArticleModel`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_quiz_bank_repository.py` —
  round-trip `write`/`load` su `EnrichedQuizModel`.
