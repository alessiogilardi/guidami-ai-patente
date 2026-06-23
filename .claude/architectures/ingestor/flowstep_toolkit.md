# Ingestor — Step flowstep generici (SP02)

Riferimento progettazione: `plans/ingest--orchestrator/02-flowstep-toolkit.md`.

Adattatori flowstep **domain-agnostic** riusati dalle slice indexing (SP03–04) e
preparation (SP05–06). Nessuna logica di dominio qui: sono pura colla di orchestrazione
tra `commons.flowstep` e i repository/service concreti.

## Layout

```
src/guidami_ai_patente_ingestor/orchestrators/
  context_keys.py          # Costanti chiavi FlowContext (no magic string)
  preparation_runner.py     # run_preparation(flow, out_path, force) — runner generico (SP05)
  steps/
    __init__.py            # Solo docstring — i simboli pubblici sono nei sub-package
    generic/
      __init__.py          # re-esporta EmbedStep, DbStoreStep, StoreRepository
      store_repository.py  # Protocol StoreRepository
      embed_step.py        # class EmbedStep
      db_store_step.py     # class DbStoreStep
    knowledge/             # step domain-specific knowledge (SP03 indexing + SP05 preparation)
      __init__.py          # re-esporta i 10 step knowledge (4 indexing + 6 preparation)
      ...
    quiz/                  # step domain-specific quiz (SP04)
      __init__.py          # re-esporta LoadEnrichedQuizStep, MapToEmbeddableStep, MapToQuizEntityStep
      load_enriched_quiz_step.py
      map_to_embeddable_step.py
      map_to_quiz_entity_step.py
```

## `context_keys.py` — vocabolario chiavi

Costanti usate dalle slice indexing SP03/04 e dalla preparation knowledge SP05
(la preparation quiz SP06 aggiungerà le proprie in modo **additivo**):

| Costante | Valore | Usata da |
|---|---|---|
| `ENRICHED_ARTICLES` | `"enriched_articles"` | SP03 (input indexing) + SP05 (output flow enrich) — lista piatta, una source |
| `PARSED_ARTICLES` | `"parsed_articles"` | SP05 — input flow `clean`: `list[Article]` dal layer `parsed` |
| `CLEANED_ARTICLES` | `"cleaned_articles"` | SP05 — output flow `clean` / input flow `enrich`: `list[Article]` puliti |
| `CHUNKS` | `"chunks"` | SP03 — output chunker → embed → store |
| `ENRICHED_QUIZ` | `"enriched_quiz"` | SP04 — input: quiz bank enriched da disco |
| `EMBEDDABLE_QUIZ` | `"embeddable_quiz"` | SP04 — modelli intermedi → embed |
| `QUIZ_ENTITIES` | `"quiz_entities"` | SP04 — entità finali → store |

`ARTICLES_BY_SOURCE` (proposta nel piano SP03 come `dict[str, list[EnrichedArticle]]`
per più source) **non esiste nel codice**: il design implementato è per-source
(una run per source), quindi `ENRICHED_ARTICLES`/`PARSED_ARTICLES`/`CLEANED_ARTICLES`
sono sempre liste piatte di UNA sola source. Nessuna chiave `SOURCE`: la source
non passa mai dal `FlowContext`, è iniettata negli step `Load*`/`Write*` alla
factory.

I consumatori accedono come `context_keys.CHUNKS` — import di submodule
(`from guidami_ai_patente_ingestor.orchestrators import context_keys`).
`orchestrators/__init__.py` re-esporta `build_knowledge_indexing_flow` (SP03),
`build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow` (SP05),
`build_quiz_indexing_flow` (SP04) e `run_preparation` (SP05).

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

## Test

`tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/` — 6 test, nessun marker
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
