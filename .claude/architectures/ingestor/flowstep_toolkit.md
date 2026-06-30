# Ingestor — Step flowstep generici e ApplyStep (SP02, esteso da SP08-bis, refactor enrichment, SP00b/SP04)

Riferimento progettazione: `plans/ingest--orchestrator/02-flowstep-toolkit.md`,
`plans/ingest--orchestrator/08-generic-map-to-step.md` (generificazione
`LoadJsonStep`/`MapStep`/`WriteJsonStep`),
`plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md`.

**`flowstep` è ora un package top-level** (`src/flowstep/`, sibling di `commons/` e
dell'ingestor — spostato da `src/commons/flowstep/` in SP00b). Zero dipendenze su
`commons` o sul dominio. Espone `Flow`, `Step`, `FlowBuilder`, `FlowContext`,
`FlowValidator`, eccezioni + **`ApplyStep`** (nuovo, in `src/flowstep/steps/`).

Gli step **domain-agnostic** in `orchestrators/steps/generic/` sono colla di
orchestrazione tra `flowstep` e i repository/service/mapper concreti. Nessuna logica
di dominio.

## Layout

```
src/flowstep/                    # Package top-level (spostato da commons/flowstep/ in SP00b)
  __init__.py                    # re-esporta Flow, Step, FlowBuilder, FlowContext, ApplyStep,
                                 #   FlowValidator, FlowValidationError, FlowValidationReport,
                                 #   StepValidationResult, ValidationSeverity, FlowExecutionError
  core/                          # Flow, Step, FlowContext — invariati
  builder/                       # FlowBuilder — invariato
  validation/                    # FlowValidator, report, eccezioni — invariato
  steps/
    __init__.py                  # re-esporta ApplyStep
    apply_step.py                # class ApplyStep(Step) — chains N callable list→list su una chiave del context

src/guidami_ai_patente_ingestor/orchestrators/
  context_keys.py                # Costanti chiavi FlowContext (no magic string)
  preparation_runner.py          # run_preparation(flow, out_path, force) — runner generico (SP05)
  steps/
    __init__.py                  # docstring
    generic/
      __init__.py                # re-esporta DbStoreStep, EmbedStep, LoadJsonStep,
                                 #   StoreRepository, WriteJsonStep
      protocols/
        store_repository.py      # Protocol StoreRepository
                                 # enricher_protocol.py RIMOSSO (EnricherProtocol eliminato in SP04)
      embed_step.py              # class EmbedStep
      db_store_step.py           # class DbStoreStep
      load_json_step.py          # class LoadJsonStep
      write_json_step.py         # class WriteJsonStep
                                 # map_step.py RIMOSSO (MapStep sostituito da ApplyStep+ForEach)
                                 # enrich_data_step.py RIMOSSO (EnrichDataStep eliminato)
    knowledge/                   # step domain-specific knowledge (solo indexing)
      __init__.py
      chunk_articles_step.py     # ChunkArticlesStep (indexing)
      embed_chunks_step.py       # EmbedChunksStep (indexing, filtro embed_repealed)
      store_chunks_step.py       # StoreChunksStep (indexing, delete-by-source)
                                 # ContextualizeStep RIMOSSO (preparation usa ApplyStep generici)
    quiz/                        # package vuoto — nessun step domain-specific quiz residuo
      __init__.py                # __all__ = []
                                 # FlattenQuizStep RIMOSSO → logica spostata in services/quiz/flatten_quiz.py
                                 # MapToEmbeddableStep RIMOSSO → logica spostata in services/quiz/to_embeddable_quiz.py
```

**`ApplyStep`** (`src/flowstep/steps/apply_step.py`, re-esportato da `flowstep`):
step generico che applica in catena N callable `list→list` a un valore del
`FlowContext`. Firma costruttore: `ApplyStep(name, *transforms, input_key,
output_key)`. Ogni transform riceve la lista prodotta dal precedente. Sostituisce
`MapStep` (un solo mapper per item, map 1:1) e `EnrichDataStep` (catena di
enricher list-in/list-out): adesso l'intera catena — base-map + enrichment —
vive in un unico `ApplyStep` che accetta sia `ForEach(mapper)` (per il mapping
1:1) sia un enricher callable direttamente (per le operazioni list-in/list-out).

**Decisione — unificazione MapStep+EnrichDataStep in ApplyStep**: step precedenti
rimossi: `map_step.py`, `enrich_data_step.py`, `enricher_protocol.py` (Protocol
generico), `flatten_quiz_step.py`, `map_to_embeddable_step.py`. La logica con
stato (flatten+dedup) è spostata a `services/quiz/` (`FlattenQuiz`,
`ToEmbeddableQuiz`) — vedi [quiz_pipelines.md](quiz_pipelines.md). Trade-off
accettato: `*transforms: Callable[[list[Any]], list[Any]]` usa `Any` per
esprimere catene eterogenee (non esprimibile in Python 3.12 senza perdere
informazione di tipo sulle catene miste). Gli step domain-specific sopravvissuti
sono quelli con logica irriducibile a get→callable→put: `ChunkArticlesStep` (N
output da 1 input) e `EmbedChunksStep` (filtro `embed_repealed`).

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
  `flowstep.Step` (top-level package — colla di orchestrazione) — appartengono
  agli `orchestrators/`, non ai `services/` (SRP + direzione dipendenze).
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
  promosso a `flowstep/steps/`, porterebbero il Protocol con sé — `flowstep` non
  può importare dall'ingestor (zero dipendenze dal dominio).
- **`cast(list[Embedded], context.get(...))` e `cast(list[Any], ...)`**: ai confini
  `FlowContext.get(key)` (che ritorna `Any`) per segnalare esplicitamente il tipo atteso.
- **`zip(strict=True)` in `EmbedStep`**: guardia difensiva — solleva `ValueError` se
  `EmbeddingService` ritornasse un numero di vettori diverso dagli item (contratto
  esplicito, anche se `EmbeddingService` garantisce allineamento 1:1).
- **`LoadJsonStep`/`WriteJsonStep` generici**: step get→delega→put per load e
  write su JSON. Parametrizzati con `model_class`/`layer`/`source`/`output_key` o
  `input_key`. Riusati identicamente da knowledge e quiz. I precedenti step
  domain-specific (`LoadParsedArticlesStep`, `WriteCleanedStep`, ecc.) sono stati
  rimossi perché erano puro get→delega→put senza logica propria.
- **`ApplyStep`** (in `flowstep.steps`, non in `generic/`): vedi sezione sopra.

## Test

- `tests/flowstep/steps/test_apply_step.py` — `ApplyStep` con zero, uno, più
  transform; i transform sono chiamati in sequenza ciascuno sull'output del
  precedente; `get_required_keys() == {input_key}`, `get_produced_keys() ==
  {output_key}`; input_key == output_key (overwrite in place) funziona.

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
- `test_load_json_step.py` / `test_write_json_step.py`:
  - contratto `required`/`produced` per chiave; delega a `layer_resolver.path(...)`
    + repository/model_class iniettati.

**Rimossi** (step eliminati): `test_map_step.py` (MapStep rimosso),
`test_enrich_data_step.py` (EnrichDataStep rimosso).
