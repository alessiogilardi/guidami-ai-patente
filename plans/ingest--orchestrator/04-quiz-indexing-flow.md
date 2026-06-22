# SP04 — Flow quiz indexing

## Scopo singolo
Ricostruire l'indicizzazione del quiz bank come **Flow flowstep**: quiz bank `enriched` →
embeddable → embed → entity → `quiz_questions`. Sostituisce `QuizIndexingPipeline` + builder
(**già rimossi** in SP03, vedi nota sotto).

## Dipende da
SP02 (`EmbedStep`, `DbStoreStep`, `context_keys`) ✅ completato. SP03 ✅ completato — è il
**pattern di riferimento** concreto da specchiare (`orchestrators/knowledge_flows.py` +
`orchestrators/steps/knowledge/`).

> ⚠️ **Stato post-SP03 (2026-06-22)**: il commit `🔥 Remove legacy indexing pipelines and orphan
> tests` ha **già rimosso** `orchestrators/quiz_indexing/` (pipeline + builder), `quiz_main.py` e i
> relativi test orfani. Quindi:
> - non c'è più un `QuizIndexingPipeline` da "sostituire": SP04 costruisce il flow **da zero**;
> - la logica da portare **non** è in un pipeline, ma vive interamente nei **mapper** già presenti
>   (`mappers/quiz/quiz_question_mapper.py`, `mappers/quiz/embeddable_quiz_question_mapper.py`);
> - resta `reset_quiz_db.py` (entry point di reset, fuori scope SP04, cutover CLI in SP07).

## Mappatura Flow
`LoadEnrichedQuizStep` → `MapToEmbeddableStep` → `EmbedStep(items_key=EMBEDDABLE_QUIZ)` →
`MapToQuizEntityStep` → `DbStoreStep(items_key=QUIZ_ENTITIES)`

Catena chiavi: `ENRICHED_QUIZ` → `EMBEDDABLE_QUIZ` → (`EmbedStep` muta in place su `EMBEDDABLE_QUIZ`)
→ `QUIZ_ENTITIES`. Tutte e tre le chiavi **esistono già** in `orchestrators/context_keys.py` (SP02):
nessuna modifica a `context_keys.py`.

## Logica da preservare (riferimento: i mapper esistenti)
La logica end-to-end del vecchio pipeline è oggi incapsulata nei mapper statici già testati:
- caricamento: `EnrichedQuizBankRepository.load(path)` → `list[EnrichedQuizMainQuestion]`;
- `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions(main)`
  → appiattisce le sub-question **e deduplica** (8 duplicati esatti → 7098 righe). La dedup è
  **dentro il mapper** e avviene **prima** dell'embed → non si embeddano i duplicati;
- embed in batch (→ `EmbedStep` generico + `EmbeddingService`, SP01/SP02);
- `EmbeddableQuizQuestionMapper.to_entity(eq)` per ogni item → `QuizQuestion`;
- store full-reload (→ `DbStoreStep`).

`EmbeddableQuizQuestion` soddisfa il protocollo `Embedded` (campo scrivibile `embedding` + property
`embedded_text = f"{topic} {text}"`, con descrizione immagine se presente) → l'`EmbedStep` generico
è applicabile senza adattamenti.

## Componenti

### Nuovi (step di dominio sottili) — `orchestrators/steps/quiz/`
> Collocazione coerente con SP03: gli step di dominio vivono in `orchestrators/steps/<dominio>/`,
> mai in `services/` (lo Step importa `commons.flowstep.Step`, è colla di orchestrazione).

- **`LoadEnrichedQuizStep`**: iniettati `EnrichedQuizBankRepository`, `LayerResolver`,
  `input_layer: str`, **`source: str`**. `execute`: `path = layer_resolver.path(input_layer, source)`
  → `repository.load(path)` → `put(ENRICHED_QUIZ, list[EnrichedQuizMainQuestion])`.
  `required=set()`, `produced={ENRICHED_QUIZ}`.
  - ⚠️ **Iniettare `source`, non hardcodare `"quiz"`**: identico a `LoadEnrichedArticlesStep` (SP03),
    che riceve `source` nel costruttore. La factory lo deriva da `config.quiz_indexing.sources[0]`
    (= `"quiz"`). Niente stringa magica nello step.
- **`MapToEmbeddableStep`**: delega `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions`.
  `required={ENRICHED_QUIZ}`, `produced={EMBEDDABLE_QUIZ}`.
- **`MapToQuizEntityStep`**: delega `EmbeddableQuizQuestionMapper.to_entity` (list-comprehension sugli item).
  `required={EMBEDDABLE_QUIZ}`, `produced={QUIZ_ENTITIES}`.

I mapper esistono già (`mappers/quiz/`, re-esportati dall'`__init__.py`) → gli step sono adattatori
puri (`get → chiama mapper statico → put`), nessun service nuovo.

### Store: `DbStoreStep` generico (truncate), **non** uno step delete-by-source
⚠️ **Divergenza voluta da SP03**: il knowledge indexing usa lo step dedicato `StoreChunksStep`
(delete-by-source + insert) perché è **per-source** e un `truncate` cancellerebbe le altre source.
Il **quiz ha una sola source** (`"quiz"`), quindi il `truncate` dell'intera `quiz_questions` è
corretto e SP04 usa il **`DbStoreStep` generico** di SP02 (truncate + bulk_insert), senza creare
alcuno `StoreQuizStep`. `QuizQuestionStoreRepository` soddisfa strutturalmente il `StoreRepository`
Protocol (ha `truncate()` + `bulk_insert(...)`). È l'unico punto in cui SP04 **non** segue SP03, ed
è una scelta deliberata.

### Nuovi (flow factory) — `orchestrators/quiz_flows.py`
Specchio di `knowledge_flows.py`. Firma **esatta** (allineata a `build_knowledge_indexing_flow`,
ma **senza** parametro `source`: la source quiz è unica e derivata da config):

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow:
    ...
```

Corpo:
- `indexing_config = config.quiz_indexing`; `source = indexing_config.sources[0]` (= `"quiz"`);
- `LoadEnrichedQuizStep("load_enriched_quiz", EnrichedQuizBankRepository(), layer_resolver, indexing_config.input_layer, source)`;
- `MapToEmbeddableStep("map_to_embeddable")`;
- `EmbedStep("embed_quiz", EmbeddingService(embedding_client, config.embedding_batch_size), context_keys.EMBEDDABLE_QUIZ)`;
- `MapToQuizEntityStep("map_to_quiz_entity")`;
- `DbStoreStep("store_quiz", QuizQuestionStoreRepository(postgres_client, config.quiz_questions_table), context_keys.QUIZ_ENTITIES)`;
- `FlowBuilder("quiz_indexing").add_step(...)....build(validate=validate)`.

> - **Ogni `Step` richiede `name`** come primo argomento posizionale (firma SP02
>   `Step.__init__(self, name)`): la factory deve passarlo.
> - `EmbedStep` ha `required == produced == {EMBEDDABLE_QUIZ}` → con `validate=True` il
>   `FlowValidator` emette il **WARNING benigno** *"Produced key overwrites an already available
>   key"* su `EMBEDDABLE_QUIZ` (severity WARNING, **non** ERROR → `build` riesce). Atteso, come in SP03.

### Modificati
- `orchestrators/steps/quiz/__init__.py` (NUOVO package — re-export dei tre step di dominio).
- `orchestrators/__init__.py`: aggiungere il re-export di `build_quiz_indexing_flow` accanto a
  `build_knowledge_indexing_flow` (intervento **additivo**; SP03 ha già creato il file).
- **Nessuna** modifica a `context_keys.py` (le 3 chiavi quiz ci sono già) né a `quiz_main.py`
  (non esiste più).

## TDD
- `MapToEmbeddableStep` / `MapToQuizEntityStep`: delega corretta al mapper (fake/spy) e contratto
  chiavi (`{ENRICHED_QUIZ}→{EMBEDDABLE_QUIZ}`, `{EMBEDDABLE_QUIZ}→{QUIZ_ENTITIES}`).
- `LoadEnrichedQuizStep`: carica dal path risolto da `LayerResolver.path(input_layer, source)`
  (fake repo + resolver); `required=set()`, `produced={ENRICHED_QUIZ}`; verifica che usi la `source`
  iniettata (non una costante hardcoded).
- Flow factory: `build(validate=True)` non solleva (solo WARNING benigno "overwrites" su
  `EMBEDDABLE_QUIZ`); `required_input_keys == set()` (il load non richiede input esterni); chiavi
  prodotte/richieste concatenate correttamente lungo la catena.
- Integration (`@pytest.mark.integration`): flow completo su Postgres → `quiz_questions` count ==
  **7098** (costante nota post-dedup; non c'è più un vecchio pipeline con cui confrontare).

## Done criteria
- Flow quiz indexing verde (unit + integration), catena
  `ENRICHED_QUIZ→EMBEDDABLE_QUIZ→QUIZ_ENTITIES`.
- Store via `DbStoreStep` generico (truncate full-reload), **nessuno** step delete-by-source
  (single source) — divergenza voluta da SP03 documentata.
- `build_quiz_indexing_flow` re-esportato da `orchestrators/__init__.py`; step re-esportati da
  `orchestrators/steps/quiz/__init__.py`.
- `EmbedStep`/`DbStoreStep` generici (SP02) riusati senza modifiche; `context_keys.py` non toccato.
- ruff/pyright verdi. Cutover CLI (entry point unico) e rimozione di `reset_quiz_db.py` restano a SP07.
