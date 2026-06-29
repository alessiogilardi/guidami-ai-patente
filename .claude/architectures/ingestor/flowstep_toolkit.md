# Ingestor — Step flowstep generici (SP02, esteso da SP08-bis e dal refactor enrichment)

Riferimento progettazione: `plans/ingest--orchestrator/02-flowstep-toolkit.md`,
`plans/ingest--orchestrator/08-generic-map-to-step.md` (generificazione
`LoadJsonStep`/`MapStep`/`WriteJsonStep`),
`plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md`.

Adattatori flowstep **domain-agnostic** riusati da entrambe le pipeline (knowledge e
quiz), sia indexing sia preparation. Nessuna logica di dominio qui: sono pura colla
di orchestrazione tra `commons.flowstep` e i repository/service/mapper concreti.

## Layout

```
src/guidami_ai_patente_ingestor/orchestrators/
  context_keys.py          # Costanti chiavi FlowContext (no magic string)
  preparation_runner.py     # run_preparation(flow, out_path, force) — runner generico (SP05)
  steps/
    __init__.py            # Solo docstring — i simboli pubblici sono nei sub-package
    generic/
      __init__.py          # re-esporta DbStoreStep, EmbedStep, LoadJsonStep, MapStep,
                           #   StoreRepository, WriteJsonStep, EnrichDataStep
      protocols/
        store_repository.py    # Protocol StoreRepository
        enricher_protocol.py   # Protocol EnricherProtocol[T_In, T_Out] — generico, domain-agnostic
      embed_step.py        # class EmbedStep
      db_store_step.py     # class DbStoreStep
      load_json_step.py    # class LoadJsonStep — load(layer, source) → put(output_key, list[model_class])
      map_step.py           # class MapStep — get(input_key) → mapper(item) per ogni item → put(output_key)
      write_json_step.py    # class WriteJsonStep — get(input_key) → write(layer, source)
      enrich_data_step.py   # class EnrichDataStep[T] — get(input_key) → catena enricher (list-in/list-out) → put(output_key)
    knowledge/             # step domain-specific knowledge (residui non generificabili)
      __init__.py
      chunk_articles_step.py   # ChunkArticlesStep (indexing)
      embed_chunks_step.py     # EmbedChunksStep (indexing, filtro embed_repealed)
      store_chunks_step.py     # StoreChunksStep (indexing, delete-by-source)
      contextualize_step.py    # ContextualizeStep (preparation, chiama ArticleContextualizerAgent)
                                # Load/Clean/Write knowledge sono oggi i generici
                                # LoadJsonStep/MapStep/WriteJsonStep, non step dedicati
                                # (vedi knowledge_flows.py)
    quiz/                  # step domain-specific quiz (residui non generificabili)
      __init__.py           # re-esporta FlattenQuizStep, MapToEmbeddableStep
      flatten_quiz_step.py        # preparation: parsed → cleaned (flatten+dedup, SP09)
      map_to_embeddable_step.py   # indexing: enriched → embeddable (flatten+dedup legacy)
                                  # LoadQuizStep/EnrichQuizStep/WriteEnrichedQuizStep
                                  # RIMOSSI: sostituiti dai generici LoadJsonStep/MapStep/
                                  # EnrichDataStep/WriteJsonStep (vedi quiz_pipelines.md)
```

**Decisione — generificazione dei load/write/map "sottili"**: gli step di
preparation che si limitavano a get → delega a repository/mapper → put
(`LoadParsedArticlesStep`, `CleanArticlesStep`, `WriteCleanedStep`, ecc. per
il knowledge; `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` per il
quiz) sono stati sostituiti dai building block generici `LoadJsonStep`/
`MapStep`/`WriteJsonStep`/`EnrichDataStep`, parametrizzati per `model_class`/
`layer`/`source`/`mapper`/`enrichers`. Restano `Step` domain-specific solo
quelli con logica di dominio non riconducibile a get→delega→put generico
(es. `ChunkArticlesStep` che produce N output da 1 input, `EmbedChunksStep`
col filtro `embed_repealed`, `FlattenQuizStep`/`MapToEmbeddableStep` col
dedup).

## `context_keys.py` — vocabolario chiavi

Costanti usate da entrambe le pipeline (knowledge, quiz), indexing e preparation:

| Costante | Valore | Usata da |
|---|---|---|
| `ENRICHED_ARTICLES` | `"enriched_articles"` | input indexing + output flow enrich — lista piatta, una source |
| `PARSED_ARTICLES` | `"parsed_articles"` | input flow `clean`: `list[ParsedArticleModel]` dal layer `parsed` |
| `CLEANED_ARTICLES` | `"cleaned_articles"` | output flow `clean` / input flow `enrich`: `list[ParsedArticleModel]` puliti |
| `EMBEDDABLE_CHUNKS` | `"embeddable_chunks"` | output chunker → embed: `list[EmbeddableChunkModel]` |
| `CHUNK_ENTITIES` | `"chunk_entities"` | output map → store: `list[KnowledgeChunk]` |
| `ENRICHED_QUIZ` | `"enriched_quiz"` | input indexing + output flow enrichment — quiz bank enriched (flat dal SP09) |
| `EMBEDDABLE_QUIZ` | `"embeddable_quiz"` | modelli intermedi → embed |
| `QUIZ_ENTITIES` | `"quiz_entities"` | entità finali → store |
| `PARSED_QUIZ` | `"parsed_quiz"` | input flow cleaning: `list[ParsedQuizModel]` (nested) dal layer `parsed` (SP09) |
| `CLEANED_QUIZ` | `"cleaned_quiz"` | output flow cleaning / input flow enrichment: `list[CleanedQuizModel]` flat (SP09) |

`ARTICLES_BY_SOURCE` (proposta come `dict[str, list[EnrichedArticleModel]]` per più
source) **non esiste nel codice**: il design implementato è per-source (una
run per source), quindi `ENRICHED_ARTICLES`/`PARSED_ARTICLES`/`CLEANED_ARTICLES`
sono sempre liste piatte di UNA sola source. Nessuna chiave `SOURCE`: la source
non passa mai dal `FlowContext`, è iniettata negli step `Load*`/`Write*` alla
factory. Stesso principio per il quiz: `IMAGE_DESCRIPTIONS` non è una chiave
di context — resta uno stato interno a `ImageDescriptionEnricher` (dict
costruito e consumato dentro `enrich()`), mai esposto nel `FlowContext`.

I consumatori accedono come `context_keys.EMBEDDABLE_CHUNKS` — import di submodule
(`from guidami_ai_patente_ingestor.orchestrators import context_keys`).
`orchestrators/__init__.py` re-esporta `build_knowledge_indexing_flow`,
`build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow`,
`build_quiz_indexing_flow`, `build_quiz_cleaning_flow`/
`build_quiz_enrichment_flow` (SP09, sostituiscono il precedente
`build_quiz_preparation_flow`) e `run_preparation`.

## Decisioni implementate

- **Collocazione in `orchestrators/steps/generic/`**: gli `Step` importano
  `commons.flowstep.Step` (colla di orchestrazione) — appartengono agli `orchestrators/`,
  non ai `services/` (SRP + direzione dipendenze).
- **`StoreRepository` Protocol con `bulk_insert` positional-only**: il parametro `/`
  disaccoppia il contratto dai nomi concreti (`chunks`/`questions`) di
  `KnowledgeChunkStoreRepository` e `QuizQuestionStoreRepository`, che altrimenti
  avrebbero rotto il match strutturale di pyright. `list[Any]` (gradual typing) è
  soddisfatto sia da `list[KnowledgeChunk]` sia da `list[QuizQuestion]`.
  Conformità **strutturale** — nessuna ereditarietà esplicita nei repo concreti.
- **`EmbedStep`: `required == produced == {items_key}`**: lo step legge e ri-scrive
  la stessa chiave (mutazione in place + `context.put`). Il `FlowValidator` emetterà
  un **WARNING benigno** "Produced key overwrites an already available key" — non è
  un ERROR e non blocca `build(validate=True)` (SP03/04).
- **`DbStoreStep`: `produced == set()`**: sink terminale, non produce nuove chiavi.
  Ordine garantito: `truncate()` → `bulk_insert(items)`.
- **`super().__init__(name)` obbligatorio** in entrambi gli step: `Step.name` legge
  `self._name` inizializzato dal costruttore base (ABC concreto, non mixato).
- **`StoreRepository` accanto a `DbStoreStep`**: in futuro, se `DbStoreStep` venisse
  promosso a `commons/flowstep/steps/`, porterebbero il Protocol con sé — `commons` non
  può importare dall'ingestor.
- **`cast(list[Embedded], context.get(...))` e `cast(list[Any], ...)`**: ai confini
  `FlowContext.get(key)` (che ritorna `Any`) per segnalare esplicitamente il tipo atteso.
- **`zip(strict=True)` in `EmbedStep`**: guardia difensiva — solleva `ValueError` se
  `EmbeddingService` ritornasse un numero di vettori diverso dagli item (contratto
  esplicito, anche se `EmbeddingService` garantisce allineamento 1:1).
- **`EnrichDataStep[T]` generico (refactor enrichment, sostituisce il quiz-specific
  `EnrichQuizStep`/`QuizEnrichmentService`)**: applica una catena di
  `EnricherProtocol[T, T]` all'intera lista letta da `input_key`, scrivendo il
  risultato in `output_key` (`input_key`/`output_key` possono coincidere). Lista
  vuota di enricher → passthrough. `EnricherProtocol[T_In, T_Out]` (Protocol
  generico in `protocols/enricher_protocol.py`) **non è un alias quiz-specific**:
  il vecchio `Protocol QuizEnricher` (1:1 alias di `EnricherProtocol[EnrichedQuizModel,
  EnrichedQuizModel]`) è stato rimosso come duplicazione — qualunque enricher
  futuro, di qualunque dominio, soddisfa il Protocol generico per struttura, senza
  bisogno di un proprio alias.
- **`LoadJsonStep`/`MapStep`/`WriteJsonStep` generici**: sostituiscono gli step
  preparation domain-specific che erano puro get→delega→put (knowledge:
  `LoadParsedArticlesStep`/`CleanArticlesStep`/`WriteCleanedStep`/
  `LoadCleanedArticlesStep`/`WriteEnrichedStep`; quiz: `LoadQuizStep`/
  `EnrichQuizStep`(parziale)/`WriteEnrichedQuizStep`). Parametrizzati con
  `model_class`/`layer`/`source` (`LoadJsonStep`/`WriteJsonStep`) o `mapper`
  (`MapStep`, una funzione pura `item -> item` applicata a ogni elemento della
  lista). Riusati identicamente da knowledge e quiz.

## Test

`tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/` — nessun marker
`integration` (nessuna dipendenza esterna):

- `test_embed_step.py`:
  - `get_required_keys() == get_produced_keys() == {items_key}`.
  - `execute` assegna embedding in place e ri-scrive `items_key` nel context.
  - `ValueError` su mismatch lunghezze vettori/item (`zip strict`).
- `test_db_store_step.py`:
  - `get_required_keys() == {items_key}`, `get_produced_keys() == set()`.
  - `execute` chiama `truncate` poi `bulk_insert` nell'ordine corretto.
- `test_store_repository.py`:
  - Conformità strutturale statica (pyright): funzione `_conforms` con annotazioni
    `StoreRepository` su `KnowledgeChunkStoreRepository` e `QuizQuestionStoreRepository`.
    Nessuna istanza a runtime (nessun Postgres necessario).
- `test_load_json_step.py` / `test_write_json_step.py` / `test_map_step.py`:
  - contratto `required`/`produced` per chiave; delega a `layer_resolver.path(...)`
    + repository/model_class iniettati; `MapStep` applica il `mapper` a ogni
    elemento della lista, preservando l'ordine.
- `test_enrich_data_step.py`:
  - `get_required_keys() == {input_key}`, `get_produced_keys() == {output_key}`.
  - lista enricher vuota → passthrough (`context.get(output_key) == items` originale).
  - un solo enricher → invocato una volta sull'intera lista (non item per item).
  - più enricher → applicati in sequenza, ciascuno sull'output del precedente.
  - `enrich(items)` ha firma list-in/list-out, verificata a parte da `execute`.
